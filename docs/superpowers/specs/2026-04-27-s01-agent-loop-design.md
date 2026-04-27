# s01 Agent 循环 — 设计文档

**日期**: 2026-04-27
**阶段**: s01（核心基础）
**状态**: 待实现

---

## 1. 背景与目标

本项目参考 [shareAI-lab/learn-claude-code](https://github.com/shareAI-lab/learn-claude-code)，采用 vibe coding 方式实现一个类 Claude Code 的编程 Agent 工具。

**s01 目标**：构建 Agent 的最核心骨架——一个支持 REPL 交互、LLM 对话往返、工具调用占位框架的循环系统。它是后续所有阶段（工具使用、子代理、Hook 系统等）的底座。

---

## 2. 技术栈

- **语言**: Python 3.11+
- **依赖管理**: `uv`（现代 Python 包管理器，替代 pip + venv）
- **LLM SDK**: `anthropic`（官方 Python SDK）
- **模型配置**: 通过 `.env` 文件 + `python-dotenv` 管理（`API_KEY`, `BASE_URL`, `MODEL`）
- **测试框架**: `pytest`
- **类型系统**: 全量类型注解，使用 `typing.Protocol` 定义接口边界

---

## 3. 架构设计

采用**三层边界设计**，通过 `typing.Protocol` 定义接口，确保后续阶段可以独立扩展任何一层而不影响其他层。

### 3.1 三层职责

| 层级 | 模块 | 职责 |
|---|---|---|
| **LLM Provider 层** | `src/provider/` | 封装具体 LLM SDK（Anthropic）。对外暴露统一接口 `chat(messages, tools) → LLMResponse`，屏蔽 API 细节、鉴权、参数格式差异。 |
| **Tool 层** | `src/tools/` | 定义 `Tool` 协议（名称、描述、参数 Schema、执行逻辑）与 `ToolRegistry`（注册表 + 分发器）。s01 只包含 mock 实现，验证调用链路。 |
| **Agent 循环层** | `src/agent/` | 持有 Provider 和 Registry，驱动 REPL 主循环，维护 `messages` 对话状态，处理 `stop_reason` 分支。 |

### 3.2 目录结构

```
src/
  __init__.py
  provider/
    __init__.py
    base.py                 # LLMProvider Protocol, LLMResponse, ContentBlock
    anthropic_provider.py   # AnthropicProvider 实现
  tools/
    __init__.py
    base.py                 # Tool Protocol, ToolResult, ToolRegistry
    mock_tools.py           # s01 占位：MockFileReadTool 等空壳
  agent/
    __init__.py
    agent.py                # Agent 类：核心循环、状态管理、I/O
  cli.py                    # 入口：解析 env、初始化、启动 REPL
```

---

## 4. 组件接口

### 4.1 LLM Provider 层

```python
# src/provider/base.py

from typing import Protocol, runtime_checkable, Literal
from dataclasses import dataclass

@dataclass(frozen=True)
class ContentBlock:
    type: Literal["text", "tool_use"]
    text: str | None = None
    # tool_use 字段
    id: str | None = None
    name: str | None = None
    input: dict | None = None

@dataclass(frozen=True)
class LLMResponse:
    content: list[ContentBlock]       # 文本 + tool_use 块
    stop_reason: Literal["end_turn", "tool_use", "max_tokens", "error"] | None
    usage: dict | None = None

@runtime_checkable
class LLMProvider(Protocol):
    def chat(self, messages: list[dict], tools: list[dict] | None = None) -> LLMResponse:
        """调用 LLM，返回统一格式的响应。"""
        ...
```

**设计要点**:
- `ContentBlock` 同时承载文本块和工具调用块，避免为每种内容类型定义独立类。
- `stop_reason` 使用 `Literal` 明确枚举，便于 Agent 层做分支判断。
- `usage` 预留字段，供后续 token 统计和上下文压缩（s06）使用。

### 4.2 Tool 层

```python
# src/tools/base.py

from typing import Protocol, runtime_checkable
from dataclasses import dataclass

@dataclass(frozen=True)
class ToolResult:
    tool_use_id: str
    content: str
    is_error: bool = False

@runtime_checkable
class Tool(Protocol):
    name: str
    description: str
    input_schema: dict  # JSON Schema

    def execute(self, tool_use_id: str, input: dict) -> ToolResult:
        ...

class ToolRegistry:
    def register(self, tool: Tool) -> None: ...
    def get(self, name: str) -> Tool | None: ...
    def list_tools(self) -> list[Tool]: ...
    def to_anthropic_format(self) -> list[dict]: ...  # 输出给 Provider
```

**设计要点**:
- `ToolResult` 必须携带 `tool_use_id`，以便 LLM API 将结果与调用请求关联。
- `is_error` 标志让 LLM 知道工具执行失败，可据此调整后续行为。
- `ToolRegistry.to_anthropic_format()` 负责将 Tool 元数据序列化为 Anthropic SDK 所需的 `tools` 参数格式。

### 4.3 Agent 循环层

```python
# src/agent/agent.py

class Agent:
    def __init__(self, provider: LLMProvider, registry: ToolRegistry):
        self.provider = provider
        self.registry = registry
        self.messages: list[dict] = []   # 通用 messages 列表

    def run_interactive(self) -> None:
        """REPL 主循环。"""
        ...

    def _run_turn(self, user_input: str) -> None:
        """
        单轮执行：
        1. user_input → append user message to messages
        2. provider.chat(messages, tools)
        3. 遍历 response.content：
           - text → 打印到 stdout
           - tool_use → 收集到待执行列表
        4. 若存在 tool_use 块：
           - 逐个查 registry → execute
           - 将所有 tool_result 合并为一条 user message 追加到 messages
           - 回到 step 2（自动继续，不等待用户输入）
        5. 若 stop_reason == "end_turn"，回合结束，等待下一次用户输入
        6. 若 stop_reason == "max_tokens" / "error"，打印提示并结束回合
        """
```

**设计要点**:
- `messages` 使用 OpenAI/通用风格（`{"role": "user" | "assistant", "content": ...}`），在 `AnthropicProvider` 内部转换为 Anthropic 格式。
- 工具调用是**自动链式**的：当 `stop_reason == "tool_use"` 时，Agent 立即执行工具并将结果回传 LLM，无需用户干预。这与 Claude Code 的行为一致。
- Agent 层不直接依赖任何具体 Provider 或 Tool 实现，仅依赖 Protocol。

---

## 5. 数据流

### 5.1 单次用户交互完整流程

```
┌─────────┐   user_input   ┌──────────┐   messages+tools   ┌─────────────────┐
│  User   │───────────────→│  Agent   │───────────────────→│ AnthropicProvider│
│  (CLI)  │←───────────────│ (Loop)   │←───────────────────│   (LLM API)     │
└─────────┘   print(text)  └──────────┘   LLMResponse       └─────────────────┘
                              │
                              │ tool_use
                              ▼
                         ┌──────────┐
                         │ ToolRegistry │
                         │  get(name)   │
                         └──────────┘
                              │
                              ▼ execute
                         ┌──────────┐
                         │ MockTool │
                         └──────────┘
                              │
                              └─→ tool_result appended to messages
                                  → loop back to provider.chat()
```

### 5.2 Messages 格式映射

Agent 内部维护通用风格的 `messages` 列表，由 `AnthropicProvider` 在调用前转换为 Anthropic SDK 格式：

| 通用格式 | Anthropic 格式 |
|---|---|
| `{"role": "user", "content": "..."}` | `{"role": "user", "content": "..."}` |
| `{"role": "assistant", "content": "..."}` | `{"role": "assistant", "content": [{"type": "text", "text": "..."}]}` |
| `{"role": "assistant", "tool_calls": [...]}` | `{"role": "assistant", "content": [{"type": "tool_use", "id": ..., "name": ..., "input": ...}]}` |
| `{"role": "tool", "tool_call_id": ..., "content": ...}` | `{"role": "user", "content": [{"type": "tool_result", "tool_use_id": ..., "content": ...}]}` |

**设计理由**：未来支持其他模型（OpenAI、Gemini 等）时，只需新增 Provider 实现，Agent 层和 Tool 层无需改动。

---

## 6. 错误处理

| 错误场景 | 行为 |
|---|---|
| **LLM API 异常**（网络、鉴权、限流） | `AnthropicProvider.chat()` 捕获 SDK 异常，包装为 `stop_reason="error"` 的 `LLMResponse`。Agent 打印错误信息，结束当前回合，不退出 REPL。 |
| **Tool 不存在** | Registry 返回 `None`，Agent 构造 `ToolResult(is_error=True, content="Tool 'xxx' not found")`，追加到 messages 让 LLM 自行处理。 |
| **Tool 执行异常** | Tool 内部捕获异常，返回 `ToolResult(is_error=True, content=traceback)`。 |
| **max_tokens** | Agent 打印提示 "Reached token limit"，结束回合。 |
| **用户中断**（Ctrl+C） | 捕获 `KeyboardInterrupt`，优雅退出 REPL。 |
| **消息格式错误** | 在 Provider 层内部转换时校验，异常转为 `error` stop_reason。 |

**核心原则**：任何错误都不应导致 REPL 崩溃，而是将错误信息反馈给 LLM 或用户，让对话继续。

---

## 7. 测试策略

| 层级 | 测试方式 | 说明 |
|---|---|---|
| **Provider 层** | 单元测试 + mock SDK client | 验证 `AnthropicProvider.chat()` 能正确处理正常响应和异常，无需真实 API key。 |
| **Tool 层** | 单元测试 | 验证 `ToolRegistry` 注册/查找/格式化；验证 mock tool 执行返回预期结果。 |
| **Agent 层** | 单元测试 + mock Provider/Registry | 验证循环逻辑：纯文本回复、单次 tool_use、多轮 tool_use、error stop_reason 等路径。 |
| **端到端** | 手动运行 | s01 阶段不引入复杂 E2E 测试框架，通过手动启动 REPL 验证完整链路。 |

测试框架选用 `pytest`。所有单元测试放在 `tests/` 目录下，按模块镜像目录结构：

```
tests/
  provider/
    test_anthropic_provider.py
  tools/
    test_base.py
  agent/
    test_agent.py
```

---

## 8. 运行方式

### 8.1 环境配置

通过项目根目录下的 `.env` 文件管理环境变量（由 `python-dotenv` 自动加载）：

| 变量名 | 必填 | 说明 |
|---|---|---|
| `API_KEY` | 是 | LLM API Key |
| `BASE_URL` | 否 | API 基础地址，默认 Anthropic 官方 |
| `MODEL` | 否 | 模型名称，默认 `claude-3-5-sonnet-20241022` |

**`.env` 示例**:

```bash
API_KEY=sk-ant-...
BASE_URL=https://...
MODEL=claude-3-5-sonnet-20241022
```

### 8.2 启动命令

```bash
# 初始化 uv 虚拟环境并安装依赖（依赖声明在 pyproject.toml 中）
uv sync

# 启动 REPL（自动加载 .env）
python -m src.cli
```

### 8.3 交互示例

```
> 请读取文件 example.txt
Agent: 我将为您读取该文件。
[调用工具: mock_file_read({"path": "example.txt"})]
工具返回: <mock: 这是一个模拟的文件内容>
Agent: 文件内容是：这是一个模拟的文件内容
> /exit
再见！
```

---

## 9. s01 交付边界

### ✅ 包含在 s01

- REPL 交互循环（持续读取用户输入，直到 `/exit`）
- LLM Provider 抽象接口 + Anthropic 具体实现
- Tool 协议定义 + ToolRegistry 注册分发机制
- Mock 工具占位（验证工具调用链路）
- 消息状态管理（对话历史维护）
- 基础错误处理（API 异常、工具不存在、用户中断等）
- 单元测试覆盖核心循环路径

### ❌ 不包含在 s01（后续阶段实现）

- 真实工具实现（文件读写、Bash 执行等）→ **s02 工具使用**
- 待办写入（TodoWrite）→ **s03**
- 子代理（SubAgent）→ **s04**
- 技能系统（Skill）→ **s05**
- 上下文压缩 → **s06**
- 权限系统 → **s07**
- Hook 系统 → **s08**
- 记忆系统 → **s09**
- 系统提示词管理 → **s10**
- 错误恢复/重试策略 → **s11**
- 任务系统、后台任务、定时调度 → **s12–s14**
- Agent 团队、团队协议、自主代理、Worktree 隔离、MCP 插件 → **s15–s19**

---

## 10. 扩展预留

| 扩展点 | 当前设计中的预留 |
|---|---|
| 多模型支持 | `LLMProvider` Protocol 已抽象，新增模型只需实现该 Protocol。 |
| 真实工具 | `Tool` Protocol 已定义，s02 直接实现该 Protocol 即可接入。 |
| 子代理 | Agent 层目前只管理 `messages`，未来子代理可作为独立 Agent 实例运行，通过消息格式嵌入。 |
| Hook 系统 | 循环中的关键节点（用户输入前、LLM 调用前后、工具执行前后）已明确，s08 可在这些位置插入回调。 |
| 上下文压缩 | `LLMResponse.usage` 已预留 token 信息，s06 可在 `provider.chat()` 前后插入压缩逻辑。 |

---

## 11. 风险与假设

| 风险/假设 | 缓解措施 |
|---|---|
| Anthropic SDK 的 `messages` 参数格式可能随版本变化 | Provider 层封装转换逻辑，变更影响范围限制在单一文件。 |
| `tool_use` 与 `tool_result` 的消息格式在后续模型间不统一 | Agent 层使用通用格式，转换逻辑下沉到 Provider 层。 |
| mock 工具无法充分验证真实工具调用的复杂性 | s01 目标仅为验证链路，真实工具逻辑在 s02 覆盖。 |
| 无真实 API 时无法运行 | 单元测试通过 mock Provider 覆盖核心逻辑，无需真实 API key。 |

---

## 12. 附录：接口签名速查

```python
# Provider
class LLMProvider(Protocol):
    def chat(self, messages: list[dict], tools: list[dict] | None = None) -> LLMResponse: ...

# Tool
class Tool(Protocol):
    name: str
    description: str
    input_schema: dict
    def execute(self, tool_use_id: str, input: dict) -> ToolResult: ...

# Agent
class Agent:
    def __init__(self, provider: LLMProvider, registry: ToolRegistry) -> None: ...
    def run_interactive(self) -> None: ...
```
