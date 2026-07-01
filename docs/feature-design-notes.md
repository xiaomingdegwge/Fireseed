# Fireseed 功能设计记录

本文按近期提交历史记录 Fireseed 主要功能点的设计原理、实现过程和关键代码入口，方便后续回看“为什么这样做”和“从哪里继续改”。

## 提交索引

| 提交 | 功能点 | 主要文件 |
|---|---|---|
| `744d517` | Bash sandbox 底座 | `sandbox/*`、`tools/bash.py`、`permissions.py` |
| `ae8e1ba` | `/sandbox` 管理命令 | `commands.py`、`sandbox/config.py`、`sandbox/manager.py` |
| `20a85f9` | Skills 系统 | `skills.py`、`skills_bundled.py`、`commands.py`、`app.py` |
| `f786156` | 权限提示的终端输入修复 | `_keylistener.py`、`permissions.py` |
| `538bacf` | AskUserQuestion 交互提问工具 | `tools/ask_user.py`、`app.py`、`llm.py` |
| `6e6eb60` | 会话查看器 | `session_viewer.py`、`pyproject.toml` |
| `52b6886` | Plan Mode | `plan.py`、`tools/plan_tools.py`、`permissions.py`、`context.py` |
| `374dbcd` | sandbox 配置和交互注释 | `.fireseed.toml`、`tools/ask_user.py` |
| 当前工作区 | WorkerManager + Agent 最小后台 worker | `worker_manager.py`、`tools/agent.py`、`app.py` |

## Bash Sandbox 底座

### 原理

Bash 是 Fireseed 中风险最高的工具，因为它能读写文件、执行系统命令和访问网络。Sandbox 底座的目标是：在模型调用 `Bash` 时，尽可能把命令包进受限环境执行，并让权限系统能识别“这个 Bash 是否已经被隔离”。

当前实现以 bubblewrap 为底层隔离工具：

- `sandbox/config.py` 负责解析 TOML 配置。
- `sandbox/checker.py` 负责检查系统是否具备 `bwrap` 等依赖。
- `sandbox/command_matcher.py` 负责匹配排除规则。
- `sandbox/wrapper.py` 负责把原始命令包装成 sandbox 命令。
- `sandbox/manager.py` 负责对外提供“是否启用、是否需要 sandbox、如何包装”的统一入口。

### 主要实现过程

启动时，`app.py` 读取配置并创建 `SandboxManager`，再传给 `BashTool` 和 `PermissionChecker`。

`BashTool.execute()` 收到命令后，先询问 `SandboxManager` 当前命令是否应该进入 sandbox。如果应该，就把命令交给 wrapper 包装后再执行；如果命中排除规则或 sandbox 未启用，就按普通 Bash 路径执行。

权限系统里有一个联动点：当 `auto_allow_bash` 开启，并且该命令会被 sandbox 包装时，`PermissionChecker` 可以跳过人工确认。这样“隔离执行”和“权限放行”保持一致，避免裸 Bash 被误认为安全。

### 关键逻辑

- `SandboxManager.is_enabled()`：判断 sandbox 当前是否实际启用。
- `SandboxManager.is_auto_allow()`：判断 sandbox Bash 是否可自动允许。
- `SandboxManager.should_sandbox(command)`：判断某条命令是否应进入 sandbox。
- `BashTool.execute()`：执行前包装命令。
- `PermissionChecker.check()`：根据 sandbox 状态决定 Bash 是否自动允许。

## `/sandbox` 管理命令

### 原理

Sandbox 不能只靠静态配置文件，否则调试成本高。`/sandbox` 命令提供一个 REPL 内的管理入口，让用户能查看状态、检查依赖、切换模式、追加排除规则。

### 主要实现过程

`commands.py` 的 slash command 分发器识别 `/sandbox` 后，将参数交给 `_cmd_sandbox()`。该函数根据子命令调用 `SandboxManager`：

- `/sandbox` 或 `/sandbox status`：展示当前配置和有效状态。
- `/sandbox deps`：检查 bubblewrap 依赖。
- `/sandbox mode <auto-allow|regular|disabled>`：切换 sandbox 模式并写回 TOML。
- `/sandbox exclude <pattern>`：追加排除命令规则并写回 TOML。

`sandbox/config.py` 提供配置序列化能力，确保命令修改后能保存到 `.fireseed.toml`。

### 关键逻辑

- `handle_command()`：slash command 总入口。
- `_cmd_sandbox()`：`/sandbox` 子命令分发。
- `SandboxManager.set_mode()`：模式切换。
- `SandboxManager.add_excluded_command()`：追加排除规则。
- `SandboxConfig.to_toml()`：配置写回。

## Skills 系统

### 原理

Skills 是“可复用提示词能力”的轻量系统。它不改变 Engine 的工具循环，而是在用户输入 slash command 时，把某个 skill 展开成一段 prompt，再交回普通模型循环执行。

这让 Fireseed 能用较低复杂度支持 `/review`、`/commit`、`/test`、`/simplify` 等工作流，同时允许项目或用户新增自己的 `SKILL.md`。

### 主要实现过程

启动时，`app.py` 调用：

- `register_bundled_skills()`：注册内置 skills。
- `discover_skills(cwd)`：发现项目和用户目录下的 skills。
- `build_skills_prompt_section()`：把可用 skills 注入 system prompt，让模型知道这些能力存在。

用户输入 `/review` 这类命令时，`commands.py` 会先尝试按普通命令处理；如果不是内置命令，再调用 `_cmd_skill()` 查找同名 skill。找到后，将 skill prompt 填入 `$ARGUMENTS`，返回 `pending_query`，由 `app.py` 继续走普通 `run_query()`。

### 关键逻辑

- `skills.py`：skill 数据结构、发现、注册、prompt 展开。
- `skills_bundled.py`：内置 skills 定义。
- `commands._cmd_skill()`：把 slash command 转换为模型 prompt。
- `CommandResult.pending_query`：让命令处理后继续进入模型循环。

## 权限提示的终端输入修复

### 原理

Fireseed 有 Rich spinner 和 Esc cancel。权限确认也需要读取单键输入，如果不协调终端模式，容易出现按键被 Esc listener 抢走、终端状态没有恢复、输入回显异常等问题。

修复目标是：权限提示期间暂停 Esc listener，读完用户选择后恢复 listener 和终端状态。

### 主要实现过程

`PermissionChecker` 持有可选的 `EscListener`。当进入 `_prompt_user()` 时，如果当前是 TTY 且 listener 存在，就先暂停 listener，再读取单键选择，最后在 `finally` 中恢复。

如果不是 TTY，保留普通 `input()` 路径，方便测试和非交互环境。

### 关键逻辑

- `_keylistener.py`：Esc 监听器的启动、暂停、恢复。
- `PermissionChecker.set_esc_listener()`：注入 listener。
- `PermissionChecker._pause_esc_listener_for_keypress()`：权限确认前暂停监听。
- `PermissionChecker._read_single_key_choice()`：读取 `y/n/a`。

## AskUserQuestion 交互提问工具

### 原理

AskUserQuestion 让模型在信息不足时主动向用户提问。它是一个工具，模型调用后，Fireseed 在终端展示选择 UI，用户回答会作为 `tool_result` 回填给模型，然后模型继续同一轮推理。

这个设计复用现有 `assistant -> tool_use -> tool_result -> assistant` 循环，不需要额外的新会话协议。

### 主要实现过程

`AskUserQuestionTool` 定义工具 schema，支持问题列表、单选、多选、选项描述和 Other 自定义输入。

当模型调用该工具时：

1. Engine 识别到 `tool_use`。
2. 权限系统看到它是只读工具，自动允许。
3. `AskUserQuestionTool.execute()` 在终端渲染问题。
4. 用户选择或输入 Other。
5. 工具把答案格式化为文本返回给模型。

交互 UI 优先使用 `prompt_toolkit`，通过 `FormattedTextControl` 渲染当前光标、勾选状态、选项说明和自定义输入。没有高级输入能力时可退回基础输入。

### 关键逻辑

- `tools/ask_user.py`：工具实现和选择 UI。
- `_select_one()`：单选交互。
- `_select_multi()`：多选交互。
- `AskUserQuestionTool.execute()`：解析 schema、收集答案、返回 tool result。
- `llm.py` mock provider：`/tool ask` 调试入口。

## 会话查看器

### 原理

Fireseed 的 session 是 JSONL：每行一个 message。对话内容里混合了纯文本、`tool_use` 和 `tool_result`，长工具输出会让直接阅读 JSONL 很痛苦。

会话查看器的目标是把 JSONL 转成更适合调试的时间线：

- 终端视图用于快速扫一眼。
- HTML 视图用于浏览器里搜索、筛选和折叠长结果。

它是独立脚本，不影响主 REPL、Engine、SessionStore。

### 主要实现过程

`session_viewer.py` 读取 `.jsonl` 文件，逐行 `json.loads()` 成 message 列表。渲染时统一把 `content` 标准化为 block 列表：

- 字符串 content 视为 text block。
- list content 逐项识别 `text`、`tool_use`、`tool_result`。

终端视图把消息按编号输出，`tool_use` 用 `->` 标记，`tool_result` 用 `<-` 标记，并按 `--max-tool-chars` 截断长内容。

HTML 视图生成单文件页面，不需要 dev server。页面内置搜索、角色筛选、左侧索引、展开/折叠按钮，所有功能都在浏览器本地运行。

### 关键逻辑

- `load_messages()`：读取 JSONL。
- `iter_blocks()`：标准化 message content。
- `render_terminal()`：终端时间线。
- `render_html()`：HTML 页面框架、搜索和筛选脚本。
- `render_html_message()`：单条消息渲染。
- `pyproject.toml`：注册 `fireseed-session-viewer` 命令。

## Plan Mode

### 原理

Plan Mode 用来把复杂任务拆成“先规划、再执行”。模型进入计划模式后，只能读代码、问问题、把计划写到指定计划文件；不能直接修改项目代码，也不能运行 Bash。退出计划模式时，Fireseed 恢复普通工具集，并把计划内容返回给模型展示给用户确认。

核心设计是一个共享状态对象 `PlanModeManager`：

- 工具通过它进入/退出计划模式。
- 权限系统通过它判断当前是否处于计划模式。
- Engine 通过它切换工具集和 system prompt。

### 主要实现过程

启动时，`app.py` 创建一个 `PlanModeManager`，并把同一个实例传给：

- `EnterPlanModeTool(plan_manager)`
- `ExitPlanModeTool(plan_manager)`
- `PermissionChecker.set_plan_manager(plan_manager)`

Engine 创建完成后，再调用 `plan_manager.bind_engine(engine)`，让 manager 可以操作 Engine 的工具列表和 system prompt。

进入计划模式时，`PlanModeManager.enter()` 执行以下步骤：

1. 在 `~/.fireseed/plans/` 下创建随机命名的计划文件。
2. 保存当前工具列表和当前 system prompt。
3. 将 Engine 工具集替换为计划模式工具：`Read`、`Glob`、`Grep`、`Edit`、`Write`、`AskUserQuestion`、`EnterPlanMode`、`ExitPlanMode`。
4. 向 system prompt 追加 `get_plan_mode_section(plan_file)`。
5. 设置 `_active = True`。

这里仍保留 `Edit` 和 `Write`，是为了让模型能写计划文件；是否能写项目文件由权限系统二次拦截。

退出计划模式时，`PlanModeManager.exit()` 执行以下步骤：

1. 读取计划文件内容。
2. 恢复进入前保存的工具列表。
3. 恢复进入前保存的 system prompt。
4. 设置 `_active = False`。
5. 返回计划内容，提示模型展示给用户确认。

### 权限限制

`PermissionChecker.check()` 会优先判断 `plan_manager.is_active`。如果当前处于计划模式，就进入 `_check_plan_mode()`：

- `Read`、`Glob`、`Grep`、`AskUserQuestion`、`EnterPlanMode`、`ExitPlanMode`：允许。
- `Edit`、`Write`：只允许目标路径等于当前计划文件。
- 其它工具，包括 `Bash`：拒绝。

这就是 Plan Mode 的安全边界：模型可以充分探索和写计划，但不能在计划确认前改项目或执行命令。

### 关键逻辑

- `tools/plan_tools.py`：两个工具的薄包装。
- `PlanModeManager.enter()`：创建计划文件、保存旧状态、切换工具和 prompt。
- `PlanModeManager.exit()`：读取计划、恢复旧状态。
- `context.get_plan_mode_section()`：计划模式提示词。
- `PermissionChecker._check_plan_mode()`：计划模式权限边界。
- `llm.py` mock provider：`/tool plan` 和 `/tool exit-plan` 调试入口。

## Sandbox 配置和 AskUserQuestion 注释整理

### 原理

该提交不是新增核心能力，而是把本地 sandbox 配置项显式化，并补充 AskUserQuestion 交互渲染的中文注释，降低后续维护成本。

### 主要实现过程

`.fireseed.toml` 中显式写出：

- `auto_allow_bash`
- `allow_unsandboxed`
- `excluded_commands`
- `allow_read`

这些字段让配置文件更接近完整结构，后续查看时不用去源码里猜默认值。

`tools/ask_user.py` 中的注释主要解释：

- `FormattedTextControl` token 格式。
- `cursor[0]` 如何表示当前选项。
- `checked` 如何表示多选状态。
- Other 输入如何渲染。
- 灰色下划线如何模拟输入光标。

### 关键逻辑

- `.fireseed.toml`：本地 sandbox 默认配置。
- `_select_one()`：单选 UI 渲染注释。
- `_select_multi()`：多选 UI 渲染注释。

## WorkerManager + Agent 最小后台 worker

### 原理

这是 Coordinator / Sub-agent 的第一块基础能力：主模型可以调用 `Agent` 工具，把一段只读探索任务交给后台 worker 并继续主流程。worker 完成后，不直接改主会话历史，而是生成一个 `<worker_result>` 通知，再由 `app.py` 把该通知作为新的用户消息喂回主 Engine。

这个设计保持了 Fireseed 原有工具循环不变：

- 主 agent 仍然通过 `tool_use -> tool_result` 启动任务。
- worker 自己也是一个普通 `Engine`，只是工具集限制为只读。
- worker 结果通过普通用户消息回流，主模型不需要新协议就能看到结果。

### 主要实现过程

`app.py` 启动时创建 `WorkerManager`，并传入 `build_worker_engine()` 回调。这个回调每次创建一个新的 worker Engine，工具只包含 `Read`、`Glob`、`Grep`，权限使用 `auto_approve=True`。

主工具列表新增 `AgentTool(worker_manager)`。模型调用 `Agent` 时，需要提供：

- `description`：后台任务短说明。
- `prompt`：worker 的详细任务。

`AgentTool.execute()` 调用 `worker_manager.spawn()`，立即返回“已启动 worker”的 tool result。`WorkerManager` 在 daemon thread 中执行 worker Engine，收集 worker 文本输出、工具调用次数和错误状态。任务结束后，`WorkerManager` 把 XML 风格的 `<worker_result>` 放入通知队列。

worker 完成后会保留自己的 Engine 历史。主模型可以继续调用 `SendMessage`，由 `WorkerManager.continue_task()` 复用同一个 worker Engine 追加一轮消息。这样 worker 可以带着前一次探索上下文继续深入，而不是每次都从空白上下文重新开始。

如果 worker 仍在运行，主模型可以调用 `TaskStop`。`WorkerManager.stop_task()` 会把任务标记为 `stopping` 并调用 worker Engine 的 `abort()`，worker 线程退出后会发送 `stopped` 状态的 `<worker_result>` 通知。

REPL 主循环在每次读用户输入前和每轮 `run_query()` 后调用 `_drain_worker_notifications()`。该函数取出已完成通知，并再次调用 `run_query(engine, notification, ...)`，让主模型能读取 worker 结果并继续总结或行动。

`--print` one-shot 模式下，为了方便 mock 调试，主查询结束后会 `wait_for_all(timeout=30)`，再 drain worker 通知。

### 关键逻辑

- `WorkerManager.spawn()`：创建 task、启动后台线程。
- `WorkerManager._run_task()`：执行 worker Engine 并收集事件。
- `WorkerManager._render_notification()`：把结果渲染成 `<worker_result>`。
- `WorkerManager.drain_notifications()`：主循环拉取完成通知。
- `AgentTool.execute()`：主模型启动后台 worker 的工具入口。
- `SendMessageTool.execute()`：主模型继续已有 idle worker 的工具入口。
- `TaskStopTool.execute()`：主模型请求停止运行中 worker 的工具入口。
- `app.build_worker_engine()`：定义 worker 的只读工具集和 worker system prompt。
- `app._drain_worker_notifications()`：把 worker 结果回灌主会话。
- `context.get_worker_system_prompt()`：worker 专用提示词。
- `llm.py` mock provider：`/tool agent <description> :: <prompt>`、`/tool send <task-id> :: <message>`、`/tool stop <task-id>` 调试入口。

### 调用栈标识

代码中用 `SUBAGENT*` 注释标记主要调用链：

1. `SUBAGENT0`：mock provider 把 `/tool agent ...` 转成 `Agent` tool_use。
2. `SUBAGENT1`：`app.py` 创建 `WorkerManager`。
3. `SUBAGENT1A`：为每个后台任务构造只读 worker Engine。
4. `SUBAGENT1B`：主 Engine 注册 `AgentTool`。
5. `SUBAGENT2`：`AgentTool.execute()` 解析参数并派发任务。
6. `SUBAGENT3`：`WorkerManager.spawn()` 登记任务并启动后台线程。
7. `SUBAGENT4`：worker 线程执行自己的 Engine，收集输出和工具状态。
8. `SUBAGENT5`：worker 完成后渲染 `<worker_result>` 通知。
9. `SUBAGENT6`：主循环 drain 通知队列。
10. `SUBAGENT6A`：主循环展示运行中 worker 状态。
11. `SUBAGENT6B`：one-shot / 测试场景等待 worker 完成。
12. `SUBAGENT7`：主线程把 `<worker_result>` 通过 `run_query()` 回灌主模型。
13. `SUBAGENT7A`：提示用户输入前显示后台进度。
14. `SUBAGENT7B`：每次提示用户前处理已完成 worker。
15. `SUBAGENT7C`：主轮次结束后再次处理刚完成的 worker。
16. `SUBAGENT8`：`--print` 模式等待并回灌 worker 结果。
17. `SUBAGENT9`：`WorkerManager.continue_task()` 复用 worker Engine 继续任务。
18. `SUBAGENT9A`：`SendMessageTool.execute()` 解析参数并继续 worker。
19. `SUBAGENT9B`：mock provider 把 `/tool send ...` 转成 `SendMessage` tool_use。
20. `SUBAGENT10`：`WorkerManager.stop_task()` 请求停止运行中 worker。
21. `SUBAGENT10A`：`TaskStopTool.execute()` 解析参数并请求停止 worker。
22. `SUBAGENT10B`：mock provider 把 `/tool stop ...` 转成 `TaskStop` tool_use。

### 当前边界

当前版本已实现“派发任务、后台执行、完成通知、继续 worker、停止 worker”的基础闭环，还没有实现：

- coordinator mode 开关和 session mode 记录。
- 更完整的任务面板和 worker 生命周期管理。

这些应作为下一批 Coordinator / Sub-agent 能力继续迁入。

## 后续维护建议

1. 新增较大功能时，继续按“原理、主要实现过程、关键逻辑”补到本文。
2. 如果某个功能已经稳定，可在本文保留设计摘要，把使用说明放到 `README.md`。
3. 如果某次提交只是临时调试文件，不建议进入本文，也不建议提交进仓库。
4. Coordinator / Sub-agent 迁入时，建议新增独立章节，并明确主 agent、worker、消息通知和权限边界之间的关系。
