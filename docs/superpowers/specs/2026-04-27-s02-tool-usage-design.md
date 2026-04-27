# s02 工具使用 — 设计文档

**日期**: 2026-04-27
**阶段**: s02（核心基础）
**状态**: 待实现

---

## 1. 背景与目标

s01 已完成 Agent 循环骨架（REPL、Provider 抽象、Tool Protocol、Registry 机制），但仅包含 `BashTool` 和一个 `MockFileReadTool` 占位。

**s02 目标**：为 Agent 提供真实的文件操作工具集——`read_file`、`write_file`、`edit_file`——使 Agent 具备读写源代码、修改配置文件等基础编程能力。所有文件操作必须限制在工作目录内，防止越界访问。

---

## 2. 技术栈

- **语言**: Python 3.11+
- **类型系统**: 全量类型注解，继续使用 `typing.Protocol` 定义 Tool 接口
- **测试框架**: `pytest`，使用 `tmp_path` fixture 做文件系统测试
- **路径处理**: `pathlib.Path`

---

## 3. 架构设计

### 3.1 模块划分

采用**方案 B**：文件操作工具合并为一个模块 `src/tools/file_tools.py`，与进程执行工具 `bash_tool.py` 形成清晰分类边界。

```
src/tools/
  base.py          # 不变：Tool Protocol, ToolResult, ToolRegistry
  bash_tool.py     # 不变：BashTool
  file_tools.py    # 新增：ReadFileTool, WriteFileTool, EditFileTool, safe_path
  mock_tools.py    # s01 遗留，s02 中删除
```

### 3.2 新增组件

| 组件 | 类型 | 职责 |
|---|---|---|
| `WORKDIR` | `pathlib.Path` | 模块级常量，`Path(os.getcwd()).resolve()`，作为安全边界基准。 |
| `safe_path(p: str) → Path` | 函数 | 将传入路径解析为绝对路径，并校验必须位于 `WORKDIR` 之下；否则抛出 `ValueError`。所有文件工具的入口必须先调用此函数。 |
| `ReadFileTool` | 类（实现 Tool Protocol） | 读取文件内容，支持按行范围分段读取。 |
| `WriteFileTool` | 类（实现 Tool Protocol） | 写入文件内容，直接覆盖，自动创建父目录。 |
| `EditFileTool` | 类（实现 Tool Protocol） | 基于精确子串替换修改文件内容，要求 oldText 唯一存在。 |

---

## 4. 组件接口

### 4.1 安全路径函数

```python
# src/tools/file_tools.py

import os
from pathlib import Path

WORKDIR = Path(os.getcwd()).resolve()

def safe_path(p: str) -> Path:
    """Resolve *p* relative to WORKDIR and enforce workspace boundary."""
    path = (WORKDIR / p).resolve()
    if not path.is_relative_to(WORKDIR):
        raise ValueError(f"Path escapes workspace: {p}")
    return path
```

**设计要点**:
- 使用 `pathlib.Path.resolve()` 消除符号链接和 `..` 片段，防止路径遍历攻击。
- 校验使用 `is_relative_to()`，语义清晰且为 Python 3.9+ 标准方法。
- 异常类型选用 `ValueError`，由调用方（Tool 类）统一捕获并包装为 `ToolResult(is_error=True)`。
- **绝对路径处理**：若 `p` 为绝对路径（如 `/etc/passwd`），`WORKDIR / p` 会直接回退为绝对路径；resolve 后若不在 `WORKDIR` 之下则抛出异常，因此绝对路径同样受边界约束。

### 4.2 ReadFileTool

```python
class ReadFileTool:
    name = "read_file"
    description = "Read the contents of a file."
    input_schema = {
        "type": "object",
        "properties": {
            "filePath": {"type": "string"},
            "startLine": {"type": "integer"},
            "endLine": {"type": "integer"},
        },
        "required": ["filePath"],
    }

    def execute(self, tool_use_id: str, input: dict) -> ToolResult:
        ...
```

**行为**:
- 调用 `safe_path(input["filePath"])` 获取目标路径。
- 若文件不存在，返回 `ToolResult(is_error=True, content="Error: File not found")`。
- `startLine` 和 `endLine` 均为 1-based 索引，且均为可选。
  - 若两者均省略，返回完整文件内容。
  - 若仅提供 `startLine`，返回从该行到文件末尾。
  - 若提供 `endLine` 但未提供 `startLine`，视为从第 1 行到 `endLine`。
  - 范围越界时（如 `startLine > 总行数`），返回空内容，不报错。
- 返回内容不做额外截断（与 `BashTool` 的 50KB 限制区分，因为文件读取通常需要完整内容）。

### 4.3 WriteFileTool

```python
class WriteFileTool:
    name = "write_file"
    description = "Write content to a file, overwriting if it exists."
    input_schema = {
        "type": "object",
        "properties": {
            "filePath": {"type": "string"},
            "content": {"type": "string"},
        },
        "required": ["filePath", "content"],
    }

    def execute(self, tool_use_id: str, input: dict) -> ToolResult:
        ...
```

**行为**:
- 调用 `safe_path(input["filePath"])` 获取目标路径。
- 若父目录不存在，使用 `path.parent.mkdir(parents=True, exist_ok=True)` 自动创建。
- 直接覆盖已有文件，不报错、不提示。
- 写入成功后返回 `ToolResult(content=f"Wrote {len(content)} bytes to {filePath}")`。
- 若写入过程中发生 I/O 异常（磁盘满、权限不足等），捕获后返回 `ToolResult(is_error=True, content=f"Error: {e}")`。

### 4.4 EditFileTool

```python
class EditFileTool:
    name = "edit_file"
    description = "Replace a unique occurrence of oldText with newText in a file."
    input_schema = {
        "type": "object",
        "properties": {
            "filePath": {"type": "string"},
            "oldText": {"type": "string"},
            "newText": {"type": "string"},
        },
        "required": ["filePath", "oldText", "newText"],
    }

    def execute(self, tool_use_id: str, input: dict) -> ToolResult:
        ...
```

**行为**:
- 调用 `safe_path(input["filePath"])` 获取目标路径。
- 读取完整文件内容。
- 使用 `str.count(oldText)` 统计匹配次数：
  - 次数为 0 → 返回 `is_error=True`，content 为 `"Error: text to replace not found"`。
  - 次数大于 1 → 返回 `is_error=True`，content 为 `"Error: text to replace found {count} times, expected exactly one"`。
  - 次数为 1 → 执行 `content.replace(oldText, newText, 1)`，写回文件。
- 写入成功后返回 `ToolResult(content=f"Replaced 1 occurrence in {filePath}")`。
- 所有 I/O 异常均捕获并包装为 `is_error=True`。

---

## 5. 数据流

数据流与 s01 完全一致，仅 Registry 中的工具从 mock 替换为真实实现：

```
User Input → Agent._run_turn → provider.chat(messages, tools)
     ↑                                              |
     └──────── print(text) ←────────────────────────┘
                              tool_use
                                 |
                                 ▼
                         ToolRegistry.get(name)
                                 |
                                 ▼ execute
                      ReadFileTool / WriteFileTool / EditFileTool
                                 |
                                 └─→ tool_result appended to messages
                                     → loop back to provider.chat()
```

**CLI 注册变更**（`src/cli.py`）:
- 移除 `MockFileReadTool` 的注册。
- 新增注册 `ReadFileTool`、`WriteFileTool`、`EditFileTool`。
- System prompt 更新为告知 Agent 可使用 bash 和文件工具进行操作。

---

## 6. 错误处理

| 错误场景 | 行为 |
|---|---|
| **路径越界** | `safe_path()` 抛出 `ValueError`，Tool 捕获后返回 `is_error=True, content="Error: Path escapes workspace: ..."`。 |
| **read_file 文件不存在** | 返回 `is_error=True, content="Error: File not found"`。 |
| **write_file 无法创建目录** | 返回 `is_error=True`，content 包含具体 OSError 信息。 |
| **write_file 写入 I/O 异常** | 返回 `is_error=True`，content 包含异常信息。 |
| **edit_file 找不到 oldText** | 返回 `is_error=True, content="Error: text to replace not found"`。 |
| **edit_file oldText 多处匹配** | 返回 `is_error=True, content="Error: text to replace found N times, expected exactly one"`。 |
| **edit_file 写入 I/O 异常** | 返回 `is_error=True`，content 包含异常信息。 |

**核心原则**：所有文件 I/O 异常和边界校验都在 Tool 内部消化，绝不抛到 Agent 循环层，确保 REPL 不会因文件操作问题而崩溃。

---

## 7. 测试策略

| 测试目标 | 方式 | 说明 |
|---|---|---|
| `safe_path` | 单元测试 | 覆盖相对路径、绝对路径、路径遍历攻击（`../etc/passwd`）、符号链接跳出工作区。 |
| `ReadFileTool` | pytest + `tmp_path` | 正常读取、范围读取（startLine/endLine 组合）、读取不存在的文件、路径越界。 |
| `WriteFileTool` | pytest + `tmp_path` | 正常写入、覆盖已有文件、自动创建嵌套目录、路径越界。 |
| `EditFileTool` | pytest + `tmp_path` | 正常替换、找不到 oldText、多处匹配、路径越界。 |
| CLI 注册 | import 检查 | 验证 `cli.py` 中 registry 正确注册了三个新工具且未注册 `MockFileReadTool`。 |

---

## 8. 运行方式

### 8.1 环境变量

与 s01 一致：

| 变量名 | 必填 | 说明 |
|---|---|---|
| `API_KEY` | 是 | LLM API Key |
| `BASE_URL` | 否 | API 基础地址 |
| `MODEL` | 否 | 模型名称 |

### 8.2 启动命令

```bash
python -m src.cli
```

### 8.3 交互示例

```
> 请帮我创建 src/utils.py，写入一个 hello 函数
Agent: 我将为您创建该文件。
[调用工具: write_file({"filePath": "src/utils.py", "content": "def hello():\n    print('hello')\n"})]
工具返回: Wrote 29 bytes to src/utils.py
Agent: 文件已创建完成。
> 把 print('hello') 改成 print('world')
Agent: 好的，我来修改。
[调用工具: edit_file({"filePath": "src/utils.py", "oldText": "print('hello')", "newText": "print('world')"})]
工具返回: Replaced 1 occurrence in src/utils.py
Agent: 修改完成。
> /exit
再见！
```

---

## 9. s02 交付边界

### ✅ 包含在 s02

- `safe_path` 统一路径安全校验函数。
- `ReadFileTool`、`WriteFileTool`、`EditFileTool` 完整实现。
- `MockFileReadTool` 从 CLI 注册中移除（`mock_tools.py` 模块删除）。
- `cli.py` 注册新工具并更新 system prompt。
- 单元测试覆盖所有文件工具及路径安全检查。

### ❌ 不包含在 s02（后续阶段实现）

- 文件搜索/列表工具（`glob`、`find`）。
- 文件 diff 预览或变更确认。
- 权限控制（只读模式、确认覆盖）→ s07。
- Hook 系统（工具执行前后回调）→ s08。
- 多文件批量操作或事务性回滚。

---

## 10. 扩展预留

| 扩展点 | 当前设计中的预留 |
|---|---|
| 新增文件工具 | 直接在 `file_tools.py` 中新增类实现 `Tool` Protocol 即可接入 Registry。 |
| 路径安全增强 | `safe_path` 可作为所有文件/路径相关工具的统一入口；未来若支持可配置工作区，只需修改 `WORKDIR` 常量的初始化方式。 |
| 权限系统 | 当前 Tool 均为无状态类，未来可在构造函数中注入权限配置（如 `readonly=True`），不影响 `execute` 接口签名。 |
| 符号链接处理 | `resolve()` 已消除符号链接，未来如需保留符号链接语义，可改为 `absolute()` + 手动校验。 |

---

## 11. 风险与假设

| 风险/假设 | 缓解措施 |
|---|---|
| `is_relative_to` 为 Python 3.9+ 方法，旧版本不兼容 | 项目已要求 Python 3.11+，无需担心。 |
| LLM 可能传入绝对路径试图跳出工作区 | `safe_path` 使用 `WORKDIR / p` 再 resolve；若 `p` 为绝对路径则直接 resolve 为该绝对路径，随后通过 `is_relative_to(WORKDIR)` 校验，越界即报错。 |
| 大文件读取导致内存或 token 爆炸 | s02 暂不做大小限制，由后续 s06 上下文压缩处理；`ReadFileTool` 保留范围读取能力作为缓解。 |
| 编辑大文件时 `str.replace` 性能不足 | s02 场景下文件规模可控；若后续出现性能瓶颈，可改用内存映射或 diff 算法。 |

---

## 12. 附录：接口签名速查

```python
# 安全路径
WORKDIR: Path = Path(os.getcwd()).resolve()
def safe_path(p: str) -> Path: ...

# ReadFileTool
class ReadFileTool(Tool):
    name = "read_file"
    def execute(self, tool_use_id: str, input: dict) -> ToolResult: ...

# WriteFileTool
class WriteFileTool(Tool):
    name = "write_file"
    def execute(self, tool_use_id: str, input: dict) -> ToolResult: ...

# EditFileTool
class EditFileTool(Tool):
    name = "edit_file"
    def execute(self, tool_use_id: str, input: dict) -> ToolResult: ...
```
