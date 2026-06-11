# 信任校准 Phase 罗盘

更新时间：2026-06-11

## 总览

本计划用于把“信任状态为什么变化、如何验证、如何调规则”拆成可逐步验收的工程阶段。核心原则是：

- 先记录事件，再计算状态。
- 先区分 AI 自动行为和人工行为，再谈信任状态。
- 历史数据只辅助校准规则，不自动给用户贴过信任/欠信任标签。
- 所有阈值调整先写入草稿，必须人工确认后才保存生效。

| Phase | 目标 | 当前状态 | 验证方式 |
|---|---|---|---|
| Phase 1 | 记录信任交互事件 | 已实现 | console 看到 `[TrustEvent]`；数据库有 `trust_events` |
| Phase 2 | 区分 AI 自动选择和人工选择 | 已实现 | AI 自动选择不增加人工接受/拒绝计数 |
| Phase 3 | 基于事件历史计算信任状态 | 已实现 | 连续拒绝 -> 欠信任；无证据接受 -> 过信任 |
| Phase 4 | 规则 UI 可调整并保存 | 已实现 | 点击“应用并保存”后当前任务生效，下一轮仍读取新规则 |
| Phase 5 | 历史行为数据可查看 | 已实现 | `/api/trust-history` 能聚合人工样本、AI 事件和证据查看 |
| Phase 6 | 历史数据生成阈值校准建议 | 已实现 | 样本不足不给建议；样本足够时建议只写入草稿 |
| Phase 7 | 运行态解释展示 | 待做 | 任务界面显示状态、触发规则、证据和推荐动作 |
| Phase 8 | 验证脚本与实验报告导出 | 待做 | 一键模拟事件并导出用户/任务信任统计 |
| Phase 9 | 隐式证据查看推断 | 待做 | 不点按钮也能基于停留、展开、眼动等行为推断证据查看 |

## Phase 1：事件记录打底

目标：把信任相关行为先完整记录下来，不急着改变状态。

已实现：

- 定义统一 `TrustInteractionEvent`。
- 记录 AI 推荐、AI 自动选择、人工接受、人工拒绝、查看证据、人工复核。
- 操作日志中携带 `trust_events`。

关键文件：

- `src/types/trustCalibration.ts`
- `src/utils/trustCalibration.ts`
- `src/hooks/useSensorTrustCalibration.ts`
- `src/hooks/useThreatTrustCalibration.ts`

验证方式：

- 前端 console 出现 `[TrustEvent]`。
- `server/data/radar_operations.db` 的 `user_operations.parameters` 中能看到 `trust_events`。

## Phase 2：区分 AI 自动选择和人工选择

目标：解决“AI 自动选择不应该增加 directAcceptCount”的问题。

已实现：

- `event_owner === "AI"` 只记录 `ai_auto_action`。
- 人工点击才记录 `human_accept` 或 `human_reject`。
- “查看结果”单独记录 `human_result_confirmed`，避免重复污染接受/拒绝计数。

关键文件：

- `src/components/Radar.tsx`
- `src/components/SAPage.tsx`
- `src/hooks/useThreatTrustCalibration.ts`
- `server/core/message_handler.py`

验证方式：

- AI 自动选择不会增加 `directAcceptCount`。
- 人工选择才进入人工行为统计。

## Phase 3：基于事件历史计算信任状态

目标：让信任状态真正随着近期人工行为变化。

已实现：

- 使用 `trustEventHistory` 作为统一输入。
- 从 `TrustInteractionEvent[]` 计算：
  - 人工拒绝次数
  - 无证据直接接受次数
  - 查看证据次数
  - 平均确认时延
- 输出：
  - `normal`
  - `under_trust`
  - `over_trust`

关键文件：

- `src/utils/trustCalibration.ts`
- `src/hooks/useSensorTrustCalibration.ts`
- `src/hooks/useThreatTrustCalibration.ts`

验证方式：

- 连续人工拒绝 -> `under_trust`。
- 连续无证据人工接受 -> `over_trust`。
- 查看证据后的接受不算 direct accept。
- AI 自动事件不触发状态变化。

## Phase 4：规则 UI 可调整并保存

目标：所有规则阈值可以通过 UI 调整，并保存到配置文件。

已实现：

- “信任设置”页可调整传感器任务和威胁排序任务规则。
- 点击“应用并保存”后：
  - 当前任务立即使用新规则。
  - 后端写入 `public/agent_level.json`。
  - 后端刷新内存配置。

关键文件：

- `src/components/TrustCalibrationSettings.tsx`
- `src/App.tsx`
- `server/network/external_ws_receiver.py`

验证方式：

- 改阈值后当前任务立即生效。
- 刷新或下一轮任务仍读取新配置。

## Phase 5：历史行为数据可查看

目标：把历史 `trust_events` 聚合成实验数据面板。

已实现：

- 后端新增 `GET /api/trust-history`。
- 从 `user_operations.parameters.extra.trust_events` 或顶层 `trust_events` 提取历史事件。
- UI 显示：
  - 人工决策样本数
  - 人工接受/拒绝
  - 无证据直接接受
  - 查看证据次数
  - AI 事件数
  - 平均确认时延
  - 最近信任事件
- 支持按当前被试 `user_id` 筛选。

关键文件：

- `server/managers/database_manager.py`
- `server/network/http_server.py`
- `src/components/TrustCalibrationSettings.tsx`
- `vite.config.ts`

验证方式：

- AI 事件展示但不计入人工决策样本。
- 当前用户筛选生效。
- 样本不足时显示“未评估”。

## Phase 6：历史数据生成阈值校准建议

目标：历史数据不只是展示，还能辅助调整规则。

已实现：

- “实验数据”页新增：
  - 传感器阈值校准建议
  - 威胁排序阈值校准建议
- 根据历史数据建议调整：
  - `direct_accept_threshold`
  - `consecutive_reject_threshold`
  - `latency_threshold_ms`
- 样本不足时不提供调整建议。
- 点击“写入草稿”只修改设置页草稿。
- 必须再点击“应用并保存”，才会写入当前任务和配置文件。

关键文件：

- `src/components/TrustCalibrationSettings.tsx`
- `server/network/http_server.py`

验证方式：

- 样本不足不给建议。
- 样本足够时显示建议。
- 建议不会自动覆盖配置。

## Phase 7：运行态解释展示

目标：当系统判定过信任或欠信任时，任务界面清楚说明“为什么”。

待做：

- 在雷达任务和威胁排序任务界面显示：
  - 当前信任状态
  - 触发规则
  - 行为证据
  - 推荐动作
- 示例文案：
  - “近期无证据直接接受达到 2 次，当前建议低置信，已进入复核模式。”
  - “近期连续拒绝 AI 推荐，已展开 AI 推荐依据。”

建议验证：

- 构造连续拒绝，界面显示欠信任解释。
- 构造无证据接受，界面显示过信任复核。
- AI 自动事件不触发人工信任解释。

## Phase 8：验证脚本与实验报告导出

目标：让整套机制可以稳定检查，并能导出实验摘要。

待做：

- 增加验证脚本：
  - 插入模拟 trust events。
  - 检查状态输出。
  - 检查历史聚合。
- 导出实验摘要：
  - 每个用户
  - 每个任务
  - 信任事件统计
  - 状态变化轨迹
  - 阈值命中情况

建议验证：

- 一键跑模拟事件集。
- 生成 CSV 或 JSON 报告。
- 报告统计与数据库原始记录一致。

## Phase 9：隐式证据查看推断

目标：把“查看证据”从按钮行为扩展到隐式行为。

待做：

- 基于以下行为推断证据查看：
  - 候选详情展开
  - 解释面板停留时长
  - 证据区域鼠标停留
  - 眼动落在证据区域
  - 对比候选后再确认
  - 人工复核按钮
- 形成一个 `evidence_viewed` 推断规则：
  - 显式查看优先。
  - 隐式行为达到阈值时补充记录。
  - 所有推断事件带 `metadata.inferred = true`。

建议验证：

- 不点“查看证据”，但停留/展开足够长时记录 inferred evidence event。
- 普通快速点击不会误判为查看证据。
- 显式查看和隐式查看不会重复计数。

## 当前建议下一步

下一步建议做 Phase 7：运行态解释展示。

理由：

- Phase 1-6 已经完成数据记录、状态计算、规则配置、历史聚合和校准建议。
- 用户现在最需要在任务过程中看懂：为什么系统要求查看证据、为什么进入复核、为什么展开解释。
- Phase 7 完成后，信任调控从“后台机制”变成“可理解的任务体验”。
