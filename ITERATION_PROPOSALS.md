# SynapseOS 2.0 迭代提案

**提案人**: 苏珊（主设计师）  
**日期**: 2026-03-26  
**迭代轮次**: 第2轮  

---

## 现状分析

经过对代码库的全面审查，SynapseOS 2.0 已完成核心框架搭建：

- ✅ 前端 Svelte + Tailwind 赛博朋克主题
- ✅ 后端 FastAPI + WebSocket 双通道实时推送
- ✅ 四页面路由：使命、任务、待决策、团队
- ✅ 果爸工作台（聊天面板，支持频道切换）
- ✅ 文件监听 + 自动刷新
- ✅ 员工状态上报系统

**现存问题**：
1. 后端存在 Bug：`lifespan` 中 `_broadcast_task` 在 `yield` 之后才创建，意味着启动期间状态变更不会广播
2. 粒子动画无 `prefers-reduced-motion` 适配
3. 前端无移动端适配（导航在小屏溢出）
4. 任务数据全量广播，无增量更新
5. 聊天系统缺少消息持久化，刷新后历史丢失
6. 团队页面逻辑复杂但缺少错误边界

---

## 提案 1：修复后端 lifespan 广播 Bug + 增强 WebSocket 稳定性

**优先级**: 🔴 高（影响核心功能）  
**预计工时**: 2-3 小时  
**负责人建议**: 里德  

### 问题
`main.py` 的 `lifespan` 函数中，`_broadcast_task`（状态广播异步循环）在 `yield` 之后才被创建。根据 FastAPI/Starlette 的生命周期模型，`yield` 之后的代码仅在应用关闭时执行。这导致：
- 启动期间 `_status_changed.set()` 的信号永远不会被消费
- 状态变更无法通过 `/ws/status` 推送到前端

### 改动内容

**文件**: `backend/main.py`

1. 将 `_broadcast_task = asyncio.create_task(_status_broadcast_loop())` 移到 `yield` 之前
2. 同时将 `yield` 之后的重复创建逻辑删除（当前代码在 shutdown 阶段又创建了一次，是无用的）

```python
# 修改前（约第 115 行附近）：
    print("[app] startup complete")
    yield  # ← app is running

    # Start broadcast task after yield（这是错的！）
    _broadcast_task = asyncio.create_task(_status_broadcast_loop())

# 修改后：
    # 启动状态广播循环（在 yield 之前！）
    _broadcast_task = asyncio.create_task(_status_broadcast_loop())
    print("[app] startup complete, broadcast loop running")
    yield  # ← app is running
```

3. 将 `_status_reporter_loop` 的扫描间隔从硬编码 60s 改为环境变量 `STATUS_SCAN_INTERVAL_S`（默认 60）

---

## 提案 2：前端移动端适配 + 响应式布局优化

**优先级**: 🟡 中（影响可用性）  
**预计工时**: 3-4 小时  
**负责人建议**: 里德  

### 问题
当前顶部导航在屏幕宽度 < 768px 时会水平溢出，工作台面板固定 960px 宽度，移动端完全不可用。

### 改动内容

**文件**: `frontend/src/App.svelte`

1. **导航响应式**：小屏时隐藏文字导航，改为汉堡菜单（底部 Tab 栏更适合移动端）
2. **工作台面板**：小屏时改为全屏覆盖（而非侧边栏），添加滑入/滑出动画
3. **添加断点样式**：

```svelte
<!-- 移动端底部 Tab -->
{#if isMobile}
  <nav class="fixed bottom-0 left-0 right-0 z-50 bg-bg-deep/95 backdrop-blur-md border-t border-cyber-cyan/10 flex">
    <a href="#/" class="flex-1 py-3 text-center text-xs">
      <span class="block text-lg">◎</span>使命
    </a>
    <a href="#/tasks" class="flex-1 py-3 text-center text-xs">
      <span class="block text-lg">▤</span>任务
    </a>
    <a href="#/decisions" class="flex-1 py-3 text-center text-xs">
      <span class="block text-lg">◈</span>决策
    </a>
    <a href="#/team" class="flex-1 py-3 text-center text-xs">
      <span class="block text-lg">⬟</span>团队
    </a>
  </nav>
{/if}
```

**文件**: `frontend/src/views/WorkbenchPanel.svelte`

4. 工作台宽度改为响应式：`width: min(960px, 100vw)`
5. 移动端添加全屏覆盖层 + 关闭按钮

**文件**: `frontend/src/app.css`

6. 添加基础响应式工具类

---

## 提案 3：聊天消息持久化 + 历史记录恢复

**优先级**: 🟡 中（影响用户体验）  
**预计工时**: 4-5 小时  
**负责人建议**: 里德  

### 问题
当前聊天系统（`/ws/chat`）所有消息仅存在内存中，页面刷新后全部丢失。对于管理工具而言，对话历史是重要的决策记录。

### 改动内容

**文件**: `backend/routers/chat_ws.py`

1. 添加消息持久化逻辑：每条消息写入 `data/chat_history.jsonl`（append-only）
2. 消息格式：
```json
{"channel_id": "infrastructure", "sender_id": "susan", "sender_name": "苏珊", "content": "...", "timestamp": "ISO8601", "type": "assistant"}
```
3. 加入频道时从文件加载历史（限制最近 50 条）

**文件**: `backend/chat_storage.py`（新建）

4. 封装消息存储/查询逻辑：
   - `append_message(channel_id, msg)`
   - `get_history(channel_id, limit=50)`
   - 按天分割文件（`data/chat_history/2026-03-26.jsonl`）便于管理和清理

**文件**: `frontend/src/views/WorkbenchPanel.svelte`

5. 前端无需改动（后端 `channel_joined` 已返回 history 字段）

---

## 提案 4：粒子动画性能优化 + 无障碍适配

**优先级**: 🟢 低（体验优化）  
**预计工时**: 1-2 小时  
**负责人建议**: 里德  

### 问题
- 60 个粒子 + 连线在低端设备可能卡顿
- 不尊重 `prefers-reduced-motion` 系统设置
- Canvas resize 使用 `ResizeObserver` 但未在 cleanup 中正确移除事件

### 改动内容

**文件**: `frontend/src/App.svelte`

1. 检测 `prefers-reduced-motion: reduce`，如果用户开启了减少动画，则禁用粒子效果
2. 将粒子数量从 60 减到 40（视觉效果几乎无差别，性能提升 33%）
3. 添加 `requestAnimationFrame` 的帧率控制，限制在 30fps
4. 修复 cleanup：确保 `resizeObserver.disconnect()` 被正确调用

```typescript
// 在 initParticles 开头添加：
const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
if (prefersReducedMotion) {
  // 静态模式：只画一次静态背景
  drawStaticBackground(ctx, canvas);
  return () => {};
}
```

---

## 提案 5：任务看板视图（Kanban）

**优先级**: 🟢 低（功能增强）  
**预计工时**: 5-6 小时  
**负责人建议**: 里德  

### 问题
当前任务页面只有列表视图，无法直观看到任务流转状态。对于管理团队而言，看板视图是更高效的任务管理方式。

### 改动内容

**文件**: `frontend/src/views/Tasks.svelte`

1. 在现有列表视图上方添加视图切换按钮：`列表 | 看板`
2. 看板视图按状态分列：待分配 → 已分配 → 进行中 → 待验收 → 已完成
3. 每列为一个可滚动列，卡片显示：标题、负责人、优先级、所属使命

**文件**: `frontend/src/components/TaskCard.svelte`（新建）

4. 抽取任务卡片为独立组件，列表和看板复用
5. 卡片支持拖拽（使用原生 HTML5 Drag & Drop API，无需额外依赖）
6. 拖拽到目标列时调用对应 API（如拖到"进行中"→ PATCH 更新状态）

**文件**: `backend/main.py`

7. 添加通用的任务状态更新 API：`PATCH /api/tasks/{task_id}/status`

```python
@app.patch("/api/tasks/{task_id}/status")
async def api_update_task_status(task_id: str, body: dict):
    new_status = body.get("status")
    # 验证合法状态
    valid = {"pending", "assigned", "in-progress", "completed", "accepted", "pending-approval", "pending-acceptance", "rejected"}
    if new_status not in valid:
        return {"success": False, "error": f"invalid status: {new_status}"}
    success, filepath = _update_task_status_in_file(task_id, new_status)
    if not success:
        return {"success": False, "error": "task not found"}
    await on_data_changed()
    return {"success": True, "task_id": task_id, "new_status": new_status}
```

---

## 执行优先级建议

| 顺序 | 提案 | 优先级 | 理由 |
|------|------|--------|------|
| 1 | 提案1: 修复 lifespan Bug | 🔴 高 | 核心功能缺陷，影响状态推送 |
| 2 | 提案3: 聊天消息持久化 | 🟡 中 | 对话历史丢失是体验硬伤 |
| 3 | 提案2: 移动端适配 | 🟡 中 | 扩大使用场景 |
| 4 | 提案4: 粒子动画优化 | 🟢 低 | 性能和无障碍 |
| 5 | 提案5: 看板视图 | 🟢 低 | 功能增强，锦上添花 |
