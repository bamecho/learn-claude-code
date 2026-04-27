# learn-claude-code

参考 [shareAI-lab/learn-claude-code](https://github.com/shareAI-lab/learn-claude-code)，采用 **vibe coding** 方式实现一个类 Claude Code 的编程 Agent 工具。

## 技术栈

- **Python** >= 3.11
- **Anthropic SDK** >= 0.30.0（LLM 交互）
- **python-dotenv** >= 1.0.0（环境变量管理）
- **pytest** >= 8.0.0（测试框架）
- **hatchling**（构建后端）
- **uv**（Python 包管理与虚拟环境）

## 目录结构

```
learn-claude-code/
├── docs/                 # 项目文档
│   └── superpowers/
├── src/                  # 源码
│   ├── agent/            # Agent 核心循环
│   │   └── agent.py
│   ├── planning/         # 规划与待办管理
│   │   └── todo_manager.py
│   ├── provider/         # LLM 提供商封装
│   │   ├── anthropic_provider.py
│   │   └── base.py
│   ├── tools/            # 工具实现
│   │   ├── bash_tool.py
│   │   ├── file_tools.py
│   │   ├── todo_tool.py
│   │   └── base.py
│   ├── cli.py            # 命令行入口
│   └── __init__.py
├── tests/                # 测试
│   ├── agent/
│   ├── planning/
│   ├── provider/
│   └── tools/
├── pyproject.toml        # 项目配置与依赖
├── uv.lock               # uv 依赖锁定文件
├── .env.example          # 环境变量示例
├── .gitignore
└── README.md
```

## 快速开始

1. **安装 uv**（如果尚未安装）：
   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```

2. **同步依赖**：
   ```bash
   uv sync
   ```

3. **配置环境变量**：
   ```bash
   cp .env.example .env
   # 编辑 .env，填入你的 API 密钥和模型信息
   ```

4. **运行测试**：
   ```bash
   uv run pytest
   ```

## 阶段路线图

### 核心基础（s01–s05）
- **s01** Agent 循环
- **s02** 工具使用
- **s03** 待办写入（TodoWrite）
- **s04** 子代理
- **s05** 技能系统

### 系统加固（s06–s11）
- **s06** 上下文压缩
- **s07** 权限系统
- **s08** Hook 系统
- **s09** 记忆系统
- **s10** 系统提示词
- **s11** 错误恢复

### 任务运行时（s12–s14）
- **s12** 任务系统
- **s13** 后台任务
- **s14** 定时调度

### 多 Agent 平台（s15–s19）
- **s15** Agent 团队
- **s16** 团队协议
- **s17** 自主代理
- **s18** Worktree 隔离
- **s19** MCP 与插件

## 开发约定

- 使用 OpenCode Agent 平台；当技能可能适用时，**必须先调用 Skill 工具**
- 项目专属的 Agent 指令放在 `AGENTS.md` 或各阶段的独立文档中
- 按阶段顺序实现，每阶段完成后再进入下一阶段
- 新增构建/测试/部署命令时同步更新 `AGENTS.md`

## 参考

- [shareAI-lab/learn-claude-code](https://github.com/shareAI-lab/learn-claude-code)
