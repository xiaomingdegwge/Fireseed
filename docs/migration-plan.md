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
- 自动 compact：根据最新 usage 或估算 token 接近上下文窗口时触发
- 基础 pytest 覆盖：tools、commands、compact、cost、config
- 配置系统增强：TOML、模型 alias、模型默认 max tokens、provider 分节
- prompt_toolkit 输入体验：历史记录、slash 补全、Alt+Enter 多行输入
- Sandbox 底座：配置解析、bwrap 包装、依赖检测、BashTool 接入、auto_allow 权限联动
- Skills 基础系统：`/skills`、`/review`、`/commit`、`/test`、`/simplify`、项目/用户 SKILL.md
- API retry
- 只读工具并发
- Rich spinner + Esc cancel
- MAMBA 主流程备注
- 关键接口中文备注

## 迁入优先级

| 顺序 | 功能 | 迁入原因 | 主要依赖 |
|---|---|---|---|
| 1 | `/sandbox` 管理命令 | Sandbox 底座已迁入，命令可提升可发现性和调试体验 | SandboxManager |
| 2 | AskUserQuestion 工具 | 让模型能主动澄清需求，是更接近 Claude Code 的交互能力 | prompt_toolkit 更佳 |
| 3 | Plan Mode | 支持计划/执行分离，适合复杂任务；需要交互式澄清和权限限制配合 | AskUserQuestion、权限系统 |
| 4 | 媒体输入 `@path` | 支持图片/文件块输入，增强模型上下文能力 | LLM content block 支持 |
| 5 | Coordinator / Agent / WorkerManager | 多 worker 并行任务系统能力强，但复杂度高 | Skills、权限、会话更稳定后 |
| 6 | Memory / KAIROS | 跨会话记忆和自动整理，属于长期增强能力 | 配置系统、session |
| 7 | Buddy | 有产品个性，但不是 Fireseed 当前学习主线的核心 | 可独立迁 |

## 推荐分批

### 第一批：自动 compact + 工程化

目标：让 Fireseed 能稳定跑、能测，长会话不容易爆上下文。

包含：

- [x] 从 `cc-mini/src/core/compact.py` 迁入 `should_compact()` 的模型阈值逻辑
- [x] 在 app 主流程里根据 `CostTracker.last_input_tokens` 触发自动 compact
- [x] 增加 `pyproject.toml`
- [x] 增加基础测试，优先覆盖工具、命令、compact、cost

### 第二批：配置系统 + 输入体验

目标：从“能用的脚本”变成“像工具的 CLI”。

包含：

- [x] TOML 配置加载
- [x] 模型别名和默认 max tokens
- [x] provider 分节配置和 `--config`
- [x] prompt_toolkit 历史记录
- [x] slash command autocomplete
- [x] 多行输入

### 第三批：Sandbox + Skills

目标：进入真实 coding assistant 的关键能力区。

包含：

- [x] Bash sandbox 配置和包装
- [x] sandbox 与权限系统联动
- [ ] `/sandbox` 管理命令
- [x] `skills.py`
- [x] `skills_bundled.py`
- [x] `/skills`、`/review`、`/commit`、`/test`、`/simplify`

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

下一步优先迁入 **`/sandbox` 管理命令**。

原因：

- Sandbox 底座已经可用，但只能通过 TOML 查看/调整
- `/sandbox` 命令能展示依赖检测、当前模式和排除规则
- 这一步能让安全能力更容易学习和调试

建议提交粒度：

1. 增加 `/sandbox` 状态展示。
2. 支持 `/sandbox mode <auto-allow|regular|disabled>`。
3. 支持 `/sandbox exclude <pattern>`。
