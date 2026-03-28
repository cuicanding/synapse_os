# SynapseOS 2.0 — 第2轮迭代提案

**提案人**: 苏珊  
**日期**: 2026-03-26  
**提案编号**: R2-001

---

## 1. 问题定位

**文件**: `backend/main.py`  
**函数**: `lifespan()`（约第 95-135 行）

**Bug**: `_status_broadcast_loop()` 在 `yield` **之后**才被 `create_task`，而 FastAPI 的 `@asynccontextmanager` lifespan 中，`yield` 之后的代码只在应用**关闭**时执行。这意味着：

- 整个应用运行期间，`/ws/status` 的广播循环**从未启动**
- 员工状态面板的实时推送**完全失效**
- 后端线程 `_status_reporter_loop` 虽然在写数据并 `_status_changed.set()`，但没有任何消费者在监听这个信号

**当前代码**（第 127-137 行）：

```python
    print("[app] startup complete")
    yield  # ← app is running

    # Start broadcast task after yield (event loop is fully running)
    _broadcast_task = asyncio.create_task(_status_broadcast_loop())
    # ↑ 这行在 shutdown 阶段才执行，broadcast loop 永远不会在运行期间工作

    # Shutdown
    _stop_reporter.set()
    if _broadcast_task:       # _broadcast_task 此时才被创建
        _broadcast_task.cancel()
```

**后果**: broadcast task 刚创建就被 `cancel()`，状态推送系统形同虚设。

---

## 2. 解决方案

将 `_broadcast_task` 的创建移到 `yield` **之前**，同时移除 `yield` 之后的重复创建逻辑。

**修改 `backend/main.py`，lifespan 函数**：

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    global watcher, _status_reporter_task

    # Start task file watcher
    watcher = DataWatcher(CYBER_TEAM_DIR)
    watcher.on_change(on_data_changed)
    await watcher.start()

    # Run first report immediately
    try:
        run_status_report()
        print("[status_reporter] initial report done")
    except Exception as e:
        print(f"[status_reporter] initial report failed: {e}")

    # Start background reporter thread
    _stop_reporter.clear()
    _status_reporter_task = threading.Thread(target=_status_reporter_loop, daemon=True)
    _status_reporter_task.start()
    print("[status_reporter] started")

    # ✅ 修复：在 yield 之前启动 broadcast loop
    async def _status_broadcast_loop():
        while True:
            await asyncio.sleep(0.5)
            if _stop_reporter.is_set():
                break
            if _status_changed.is_set():
                _status_changed.clear()
                try:
                    panel = get_panel()
                    await broadcast_status({
                        "type": "status_updated",
                        "payload": {"panel": panel},
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    })
                except Exception as e:
                    print(f"[status_broadcast] error: {e}")

    _broadcast_task = asyncio.create_task(_status_broadcast_loop())
    print("[app] startup complete, broadcast loop running")
    yield  # ← app is running

    # ✅ shutdown：只做清理，不再创建 task
    _stop_reporter.set()
    if _broadcast_task:
        _broadcast_task.cancel()
        try:
            await _broadcast_task
        except asyncio.CancelledError:
            pass
    if _status_reporter_task:
        _status_reporter_task.join(timeout=5)
    if watcher:
        await watcher.stop()
    print("[app] shutdown complete")
```

**改动总结**（2 处）：
1. `_broadcast_task = asyncio.create_task(...)` 从第 133 行移到第 122 行（`yield` 之前）
2. 删除 `yield` 之后原来的 `_broadcast_task = asyncio.create_task(...)`（第 133 行）

---

## 3. 价值说明

**解决的具体痛点**：
- `/ws/status` WebSocket 推送从"完全失效"变为"正常工作"
- 员工状态面板能实时反映变化，不再需要手动刷新
- 难度上报、决策请求等事件能即时推送到前端

**不做的后果**：
- 状态推送系统是死代码，整条 `/ws/status` → `status_clients` → `broadcast_status()` 链路从未被触发
- 员工通过 `POST /api/status/report` 提交的状态更新无法实时送达已连接的前端
- 这是后端的一个**核心功能缺陷**，不是锦上添花

---

## 4. 优先级理由

这是所有现存问题中**唯一的阻断性 Bug**：

| 对比项 | 此 Bug | 其他提案 |
|--------|--------|----------|
| 严重性 | 核心功能完全失效 | 体验/功能增强 |
| 影响面 | 所有使用 `/ws/status` 的前端页面 | 局部 |
| 修复成本 | 移动 1 行，删除 1 行 | 数小时 |
| 验证难度 | 可立即验证 | 需要多场景测试 |

移动端适配、消息持久化、看板视图都是增量改进，可以之后做。但 broadcast loop 不工作 = 状态系统是废的，这是地基问题。

---

## 5. 验证方式

1. **启动后端**，观察日志输出：
   - ✅ 应看到 `[app] startup complete, broadcast loop running`（而非之前的 `[app] startup complete`）
   - ✅ 60 秒后应看到 `[status_reporter] updated N agents`

2. **前端连接 `/ws/status`**，观察是否收到 `status_updated` 消息：
   ```bash
   # 用 wscat 测试
   wscat -c ws://localhost:8001/ws/status
   # 等待 60 秒（status reporter 扫描周期），应收到 status_updated 消息
   ```

3. **手动触发状态上报**，验证即时推送：
   ```bash
   curl -X POST http://localhost:8001/api/status/report \
     -H "Content-Type: application/json" \
     -d '{"agent_id":"susan","agent_name":"苏珊","status":"working","task_id":"task-001","progress":50}'
   # wscat 窗口应立即收到 status_updated 消息
   ```

4. **检查 shutdown 日志**，确认不再出现"创建即取消"的问题：
   - ✅ `[app] shutdown complete`（只出现一次，不再重复）
