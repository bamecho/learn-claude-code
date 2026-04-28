- use question tool for clarifying.

## 项目概述

参考 [shareAI-lab/learn-claude-code](https://github.com/shareAI-lab/learn-claude-code)，采用 **vibe coding** 方式实现一个类 Claude Code 的编程 Agent 工具。

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

- must use uv command when using pyhon
- 使用 OpenCode Agent 平台；当技能可能适用时，**必须先调用 Skill 工具**
- 项目专属的 Agent 指令应放在本文件或各阶段的独立文档中
- 按阶段顺序实现，每阶段完成后再进入下一阶段

## Approach
- Be concise in output but thorough in reasoning.
- Prefer editing over rewriting whole files.
- Do not re-read files you have already read unless the file may have changed.
- Skip files over 100KB unless explicitly required.
- Recommend starting a new session when switching to an unrelated task.
- Test your code before declaring done.
- No sycophantic openers or closing fluff.
- Keep solutions simple and direct.
- User instructions always override this file.