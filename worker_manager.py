from __future__ import annotations

import itertools
import queue
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from engine import Engine


@dataclass
class WorkerTask:
    # WorkerTask 是后台任务的运行时快照。
    # 主线程用它展示状态；worker 线程用它记录结果和错误。
    task_id: str
    description: str
    prompt: str
    engine: Engine
    status: str = "queued"
    result: str = ""
    error: str | None = None
    tool_uses: int = 0
    current_activity: str | None = None
    started_at: float = field(default_factory=time.monotonic)
    completed_at: float | None = None
    thread: threading.Thread | None = None


class WorkerManager:
    """Run read-only background worker tasks and publish completion notifications."""

    def __init__(self, build_worker_engine: Callable[[], Engine]) -> None:
        """初始化 worker 管理器，保存用于创建独立 worker Engine 的工厂函数。"""
        # SUBAGENT1: app.py 启动时创建 WorkerManager，并注入 worker Engine 工厂。
        # 这里传入工厂函数，而不是复用主 Engine：
        # 每个 worker 都需要独立 messages/tools/prompt，避免污染主会话。
        self._build_worker_engine = build_worker_engine
        self._counter = itertools.count(1)
        self._tasks: dict[str, WorkerTask] = {}
        # worker 在线程里完成，不能直接调用主 Engine；先把结果放进线程安全队列，
        # 再由 REPL 主循环 drain 后作为用户消息喂回主 Engine。
        self._notifications: queue.Queue[str] = queue.Queue() #与主agent的交互队列
        self._lock = threading.Lock()
    #run
    def spawn(self, *, description: str, prompt: str) -> WorkerTask:
        """创建并启动一个后台 worker 任务，立即返回任务状态对象。"""
        # SUBAGENT3: AgentTool 调用 spawn，登记任务并启动后台线程。
        task_id = f"worker-{next(self._counter)}"
        task = WorkerTask(
            task_id=task_id,
            description=description.strip() or "Background worker",
            prompt=prompt.strip(),
            engine=self._build_worker_engine(),
        )
        thread = threading.Thread(
            target=self._run_task,
            args=(task,),
            name=f"fireseed-{task_id}",
            # daemon=True 表示 Fireseed 退出时不被后台 worker 卡住。
            # 后续如果支持 TaskStop，可以在这里补更完整的生命周期控制。
            daemon=True,
        )
        task.thread = thread
        with self._lock:
            self._tasks[task_id] = task
        thread.start()
        return task

    def continue_task(self, *, task_id: str, message: str) -> WorkerTask | None:
        """继续一个已结束或空闲的 worker，用同一个 Engine 追加一轮任务。"""
        # SUBAGENT9: SendMessageTool 复用 worker Engine 的历史上下文继续追问。
        message = message.strip()
        if not message:
            return None
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None or task.status in {"queued", "running"}:
                return None
            task.prompt = message
            task.result = ""
            task.error = None
            task.current_activity = None
            task.started_at = time.monotonic()
            task.completed_at = None
            task.status = "queued"
            thread = threading.Thread(
                target=self._run_task,
                args=(task,),
                name=f"fireseed-{task.task_id}-continue",
                daemon=True,
            )
            task.thread = thread
        thread.start()
        return task

    def stop_task(self, task_id: str) -> bool:
        """请求停止一个正在运行的 worker，返回是否找到可停止任务。"""
        # SUBAGENT10: TaskStopTool 通过 worker Engine.abort() 请求取消后台任务。
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None or task.status != "running":
                return False
            task.status = "stopping"
            task.error = "Stopped by TaskStop."
            task.engine.abort()
            return True

    def drain_notifications(self) -> list[str]:
        """排空通知队列，返回所有未处理的完成通知。"""
        # SUBAGENT6: app.py 在 REPL 前后 drain 通知，准备回灌主会话。
        # 主循环定期调用 drain，把已完成 worker 结果一次性取走。
        # get_nowait 避免 REPL 因为等待 worker 阻塞。
        notifications: list[str] = []
        while True:
            try:
                notifications.append(self._notifications.get_nowait())
            except queue.Empty:
                break
        return notifications

    def get_running_status(self) -> list[dict[str, Any]]:
        """返回当前运行中的 worker 状态，用于在 REPL 提示前展示进度。"""
        # SUBAGENT6A: 主循环展示后台 worker 进度，不阻塞用户继续输入。
        with self._lock:
            tasks = list(self._tasks.values())
        statuses = []
        for task in tasks:
            if task.status not in {"running", "stopping"}:
                continue
            statuses.append(
                {
                    "task_id": task.task_id,
                    "description": task.description,
                    "tool_uses": task.tool_uses,
                    "activity": task.current_activity,
                }
            )
        return statuses

    def has_running_tasks(self) -> bool:
        """判断当前是否还有排队或运行中的 worker。"""
        with self._lock:
            return any(task.status in {"queued", "running", "stopping"} for task in self._tasks.values())

    def wait_for_all(self, timeout: float | None = None) -> None:
        """等待所有 worker 结束，主要用于 one-shot 调试和测试。"""
        # SUBAGENT6B: --print 模式没有下一次 REPL tick，需要主动等待 worker。
        # 仅用于 --print / 测试场景：one-shot 模式需要等 worker 完成，
        # 交互式 REPL 则保持异步，不调用这个方法阻塞用户输入。
        deadline = time.monotonic() + timeout if timeout is not None else None
        while True:
            with self._lock:
                threads = [
                    task.thread
                    for task in self._tasks.values()
                    if task.thread is not None and task.thread.is_alive()
                ]
            if not threads:
                return
            for thread in threads:
                remaining = None if deadline is None else max(0.0, deadline - time.monotonic())
                if remaining == 0.0:
                    return
                thread.join(timeout=min(0.1, remaining) if remaining is not None else 0.1)

    def _run_task(self, task: WorkerTask) -> None:
        """在线程中运行 worker Engine， subagent并把完成通知放入队列。"""
        # SUBAGENT4: 子线程消费 worker Engine 事件，只收集结果，不直接操作主 Engine。
        task.status = "running"
        text_parts: list[str] = []
        try:
            # worker 自己也是普通 Engine，复用现有 tool loop。
            # 这里消费事件而不打印 UI，只收集最终文本和工具活动状态。
            #运行subagent，消费事件，收集结果和工具调用次数，event 是yield 事件
            for event in task.engine.submit(task.prompt): #一次访问完整的subagent（LLM + 工具调用的最终结果）
                event_type = event[0]
                if event_type == "text":
                    text_parts.append(str(event[1]))
                elif event_type == "tool_call":
                    task.tool_uses += 1
                    task.current_activity = event[3] or str(event[1])
                elif event_type == "tool_result":
                    task.current_activity = None
                elif event_type == "error":
                    task.error = str(event[1])
            task.result = "".join(text_parts).strip()
            task.status = "failed" if task.error else "completed"
        except Exception as exc:
            if task.status != "stopping":
                task.error = str(exc)
                task.status = "failed"
        finally:
            task.completed_at = time.monotonic()
            if task.status == "stopping":
                task.status = "stopped"
            # 不管成功/失败都发通知，让主模型知道 worker 已经结束。
            self._notifications.put(self._render_notification(task))

    def _render_notification(self, task: WorkerTask) -> str:
        """把 worker 任务结果渲染为可回灌主会话的通知文本。"""
        # SUBAGENT5: 将 worker 输出包装成模型易读的通知协议。
        duration_ms = 0
        if task.completed_at is not None:
            duration_ms = int((task.completed_at - task.started_at) * 1000)
        body = task.result or task.error or "No result."
        status = task.status
        # XML 风格文本容易被模型识别，也能直接作为普通 user message
        # 回灌到主会话，不需要扩展 session 消息协议。
        return (
            "<worker_result>\n"
            f"<task_id>{task.task_id}</task_id>\n"
            f"<status>{status}</status>\n"
            f"<description>{task.description}</description>\n"
            f"<tool_uses>{task.tool_uses}</tool_uses>\n"
            f"<duration_ms>{duration_ms}</duration_ms>\n"
            f"<result>\n{body}\n</result>\n"
            "</worker_result>"
        )
