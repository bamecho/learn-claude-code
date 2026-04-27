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

- 参考README.md，使用uv作为依赖管理
- 使用 OpenCode Agent 平台；当技能可能适用时，**必须先调用 Skill 工具**
- 项目专属的 Agent 指令应放在本文件或各阶段的独立文档中
- 按阶段顺序实现，每阶段完成后再进入下一阶段

# Guidelines
Behavioral guidelines to reduce common LLM coding mistakes. Merge with project-specific instructions as needed.

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

## 1. Think Before Acting
**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First
**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes
**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution
**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

## 5. Approach
- Be concise in output but thorough in reasoning.
- Prefer editing over rewriting whole files.
- Do not re-read files you have already read unless the file may have changed.
- Skip files over 100KB unless explicitly required.
- Recommend starting a new session when switching to an unrelated task.
- Test your code before declaring done.
- No sycophantic openers or closing fluff.
- Keep solutions simple and direct.
- User instructions always override this file.