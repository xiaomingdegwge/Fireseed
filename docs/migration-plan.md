# Fireseed 迁入设计文档

本文记录 Fireseed 从 `cc-mini` 继续迁入能力的优先级、依赖关系和建议批次。后续迁移只在 `/home/qcraft/gitproject/Fireseed` 中进行，不再修改 `cc-mini/docs/CC_DUP`。

## 当前基线

Fireseed 已迁入：

- REPL / one-shot prompt
- Engine 工具循环：`assistant -> tool_use -> tool_result -> assistant`
- Anthropic / OpenAI / mock provider
- 工具：`Read`、`Edit`、`Write`、`Glob`、`Grep`、`Bash`
- 权限确认：只读工具自动允许，写入和 Bash 需要确认
- session 保存和 `--resume`
- slash commands：`/help`、`/sessions`、`/history`、`/resume`、`/clear`
- `/compact`
- `/cost`
- API retry
- 只读工具并发
- Rich spinner + Esc cancel
- MAMBA 主流程备注
- 关键接口中文备注

## 迁入优先级

| 顺序 | 功能 | 迁入原因 | 主要依赖 |
|---|---|---|---|
| 1 | 自动 compact | 已有 `/compact` 和 `/cost`，补自动触发最自然，可解决长会话上下文膨胀 | `compact.py`、`CostTracker.last_input_tokens` |
| 2 | 独立项目工程化 | Fireseed 已是独立仓库，应尽快补 `pyproject.toml`、基础测试和运行规范 | 无 |
| 3 | 配置系统增强 | 支持 TOML、模型 alias、默认 max tokens、provider 配置，让项目更像正式工具 | 工程化后更好 |
| 4 | prompt_toolkit 输入体验 | 命令历史、slash autocomplete、多行输入、边框输入会明显提升日常使用体验 | 命令系统 |
| 5 | Sandbox | Bash 是高风险工具，隔离和安全策略是核心能力 | 配置系统、权限系统 |
| 6 | Skills 基础系统 | `/review`、`/commit`、`/test`、`/simplify` 是高频工作流，比高级 agent 更实用 | 命令系统、Edit/Write/Bash |
| 7 | AskUserQuestion 工具 | 让模型能主动澄清需求，是更接近 Claude Code 的交互能力 | prompt_toolkit 更佳 |
| 8 | Plan Mode | 支持计划/执行分离，适合复杂任务；需要交互式澄清和权限限制配合 | AskUserQuestion、权限系统 |
| 9 | 媒体输入 `@path` | 支持图片/文件块输入，增强模型上下文能力 | LLM content block 支持 |
| 10 | Coordinator / Agent / WorkerManager | 多 worker 并行任务系统能力强，但复杂度高 | Skills、权限、会话更稳定后 |
| 11 | Memory / KAIROS | 跨会话记忆和自动整理，属于长期增强能力 | 配置系统、session |
| 12 | Buddy | 有产品个性，但不是 Fireseed 当前学习主线的核心 | 可独立迁 |

## 推荐分批

### 第一批：自动 compact + 工程化

目标：让 Fireseed 能稳定跑、能测，长会话不容易爆上下文。

包含：

- 从 `cc-mini/src/core/compact.py` 迁入 `should_compact()` 的模型阈值逻辑
- 在 Engine 或 app 主流程里根据 `CostTracker.last_input_tokens` 触发自动 compact
- 增加 `pyproject.toml`
- 增加基础测试，优先覆盖工具、命令、compact、cost

### 第二批：配置系统 + 输入体验

目标：从“能用的脚本”变成“像工具的 CLI”。

包含：

- TOML 配置加载
- 模型别名和默认 max tokens
- prompt_toolkit 历史记录
- slash command autocomplete
- 多行输入

### 第三批：Sandbox + Skills

目标：进入真实 coding assistant 的关键能力区。

包含：

- Bash sandbox 配置和包装
- sandbox 与权限系统联动
- `skills.py`
- `skills_bundled.py`
- `/skills`、`/review`、`/commit`、`/test`、`/simplify`

### 第四批：AskUserQuestion + Plan Mode

目标：支持复杂任务中的澄清、规划和执行边界。

包含：

- `AskUserQuestion` 工具
- `EnterPlanMode` / `ExitPlanMode`
- Plan Mode 下的权限限制
- context 中的 plan mode prompt

### 第五批：Coordinator / Memory / Buddy

目标：迁入高级能力和产品特色。

包含：

- Coordinator mode
- WorkerManager
- Agent / SendMessage / TaskStop
- KAIROS Memory
- Buddy companion

## 下一步建议

下一步优先迁入 **自动 compact**。

原因：

- Fireseed 已有 `/compact`
- Fireseed 已有 `/cost` 和 `CostTracker.last_input_tokens`
- 改动范围小，和当前代码关联度最高
- 能补齐“长会话自动维护上下文”的核心能力

建议提交粒度：

1. 迁入 `should_compact()` 和模型上下文阈值估算。
2. 在一轮 query 结束后检测是否需要自动 compact。
3. 增加 mock/单元测试，确认触发条件和消息替换逻辑。
