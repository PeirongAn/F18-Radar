# AI 准确率区间、任务难度与审计机制

本文记录 `difficulty-group-range-v1` 的计算方法、数学含义和数据审计口径。Radar 传感器任务与 SA 威胁排序任务共用同一套算法。

## 1. 配置矩阵

| AI 等级 | low | medium | high |
| --- | ---: | ---: | ---: |
| L1 | 40%～50% | 35%～45% | 30%～40% |
| L2 | 80%～90% | 75%～85% | 70%～80% |
| L3 | 99%～100% | 97%～99% | 94%～97% |

配置位于 `public/agent_level.json` 和 `dist/agent_level.json` 的
`decision_probability_ranges_by_difficulty`。新配置优先；旧字段
`decision_probabilities` 仅用于兼容：单值数组是固定概率，双值数组是不区分难度的区间。

配置缺失、上下限颠倒、长度不是 1 或 2、数值超出 `[0,1]` 时，正式 AI 任务拒绝启动并返回 `ai_accuracy_config_invalid`。

外部协议映射为：

```text
AIAutonomyLeve: 1 -> L1, 2 -> L2, 3 -> L3
Difficulty:      1 -> high, 2 -> medium, 3 -> low
```

外部字段 `aiprecision` 继续保存，但不覆盖上述矩阵。

## 2. 第一层随机：每个任务组只抽一次准确率

设某个等级和难度对应的区间为 `[a,b]`。先根据任务组上下文得到组级种子：

```text
probability_seed = first64bits(SHA256(
  base_seed | user_id | task_type | task_group_id |
  ai_level | difficulty | algorithm_version
))
```

SQLite 的整数是有符号 64 位，因此实现以二进制补码的有符号形式保存完整的前 64 位；送入伪随机数生成器时再恢复为对应的无符号 64 位模式。

使用该种子生成：

```text
U_g ~ Uniform(0,1)
p_g = round(a + U_g * (b - a), 2)
```

`p_g` 是任务组的抽取概率。它只在任务组首次启动时生成一次，并写入 `task_groups`：

- `ai_probability_min`
- `ai_probability_max`
- `sampled_ai_probability`
- `ai_probability_seed`
- `ai_accuracy_algorithm`

完整上下文同时写入 `task_groups.config_json.ai_accuracy`。后续 20 个子任务、WebSocket 重连、恢复和服务重启均读取已保存值，不重新抽取。

## 3. 第二层随机：每个子任务独立决定正确或错误

每个具体子任务根据组级种子生成独立种子：

```text
decision_seed = first64bits(SHA256(
  probability_seed | task_id | task_seq | task_type
))
```

使用同一个任务级伪随机数生成器，按固定顺序取得：

```text
V_i = decision_random ~ Uniform(0,1)
W_i = pool_random     ~ Uniform(0,1)

intended_correct_i = (V_i < p_g)
pool_index_i = floor(W_i * selected_pool.length)
```

前端不再为准确率调用 `Math.random()`。服务端先按 `intended_correct` 建立目标池，将池内 ID 排序，再按 `pool_random` 算出唯一的 `expected_target_id`。初始化消息中的 `ai_decision` 同时携带 `selection_protocol`、`selected_pool`、`pool_index`、`fallback_reason` 和 `expected_target_id`；前端只执行该目标，不再自行分池或抽取池内元素。

Radar：正确池是敌机池，错误池是友机池。SA：正确池是当前最高优先级项，错误池是其余项。空池或 SA 只有一个威胁时允许回退，但必须保存 `selected_pool` 和 `fallback_reason`。

## 4. 为什么单轮正确概率等于组概率

固定一个任务组的 `p_g=p`。因为 `V_i` 在 `[0,1)` 上均匀分布，事件 `V_i<p` 对应区间 `[0,p)`，区间长度恰好为 `p`，所以：

```text
P(intended_correct_i = true | p_g = p)
= P(V_i < p)
= p
```

例如 `p=0.8`，`[0,0.8)` 占整个单位区间的 80%，因此每一轮进入正确分支的概率是 80%。这不表示 20 轮一定恰好正确 16 次。

## 5. 为什么区间抽样的平均值是区间中点

忽略两位小数舍入的微小离散化影响：

```text
p_g = a + U_g(b-a)
E[U_g] = 1/2

E[p_g]
= a + E[U_g](b-a)
= a + (b-a)/2
= (a+b)/2
```

因此大量任务组的平均抽取概率趋近区间中点。例如 L2/high 的区间是 `[0.70,0.80]`，大量任务组的平均 `p_g` 趋近 0.75。

## 6. 组内共享概率下的实际准确率

设一组有 `n` 个有效 AI 决策，最终真值为：

```text
Y_i = 1  本轮最终选择正确
Y_i = 0  本轮最终选择错误

A_n = (Y_1 + ... + Y_n) / n
```

在正确池、错误池都非空，且分池规则与服务端真值一致时：

```text
Y_i = intended_correct_i
E[Y_i | p_g] = p_g
E[A_n | p_g] = p_g
```

随着组内轮数增加，根据大数定律，`A_n` 通常会靠近该组实际抽到的 `p_g`。但 20 轮仍是小样本，70%、80%、90% 等结果都可能正常出现。

注意这是“条件于本组 `p_g`”的结论，不是说每个组都靠近区间中点。不同任务组先抽到不同的 `p_g`，然后各自在该概率附近波动，这就是两层随机：

```text
任务组之间：p_g 随机，反映同一等级/难度下的能力波动
任务组之内：Y_i 随机，反映逐轮决策波动
```

## 7. 回退为什么会造成计划分支与最终真值不同

如果正确池为空，计划进入正确分支也只能从错误池回退选择；如果 SA 只有一个威胁，计划错误也只能选择唯一且最高优先级的威胁。因此一般情况下：

```text
intended_correct_i 不一定等于 final_is_correct_i
```

实验准确率必须使用服务端依据实际目标真值记录的 `is_correct`，不能使用 `intended_correct` 代替。`intended_correct` 用于解释算法计划，`fallback_reason` 用于解释计划为何未实现。

## 8. 持久化与统计口径

正式任务的 `target_selected`/`threat_clicked` 在
`user_operations.parameters.ai_decision` 中保存：任务组和子任务 ID、等级、难度、区间、抽取概率、两级种子、两个随机数、计划分支、实际选择、选择池、回退原因和最终 `is_correct`。

写入数据库成功后才确认 AI 选择；失败时返回记录失败消息，未保存的选择不进入准确率。

查询接口：

```text
GET /api/ai-accuracy?task_group_id=<id>&include_decisions=0|1
```

统计关联路径：

```text
task_groups -> task_runs -> user_operations
```

只统计 Radar/SA、`event_owner=AI`、`is_correct` 为真或假的有效选择；每个具体子任务最多取一条幂等记录：

```text
N = valid_decision_count
C = correct_count
E = incorrect_count

actual_accuracy = C / N,  N > 0
actual_accuracy = null,   N = 0

deviation = actual_accuracy - sampled_probability
```

接口同时返回缺失任务、重复任务和 `audit_complete`。历史任务没有组级抽样上下文时仍可统计已有真值，但返回：

```text
sampled_probability = null
algorithm_version = legacy_untracked
audit_complete = false
```

系统不会补造历史概率。

## 9. 如何验证实现与公式一致

测试分为三层：

1. 确定性测试：覆盖 9 个等级×难度区间、非法配置、种子复现、Radar/SA 两个池及回退。
2. 大样本测试：固定条件模拟 10 万个任务组，平均 `p_g` 应接近区间中点；固定一个 `p_g` 模拟 10 万轮，正确分支频率与 `p_g` 偏差不超过 0.5 个百分点。
3. 数据库测试：验证组概率只保存一次、逐轮审计字段完整、正确/错误聚合、历史组和缺失记录口径。

数学证明回答“算法为什么应当成立”，自动化测试回答“当前代码是否真的按算法运行”。两者必须同时满足。

## 10. 服务端权威目标与旧前端隔离

当前选择协议为 `server-authoritative-target-v1`。AI 提交 `target_selected` 或 `threat_clicked` 时必须回传协议标记和服务端下发的 `expected_target_id`。服务端按当前 `task_id` 进行三重校验：

```text
selection_protocol == server-authoritative-target-v1
client_expected_target_id == server_expected_target_id
actual_selection == server_expected_target_id
```

任一条件不满足时返回 `ai_decision_protocol_mismatch` 或 `ai_decision_target_mismatch`，不写入数据库，也不发送记录成功确认。这样旧页面仍在运行旧版 `Math.random()` 逻辑时，即使随机碰巧选中正确分支，也不能混入新算法实验。

`audit_complete` 除了检查任务、字段和幂等记录是否齐全，还检查 `actual_selection` 是否属于 `selected_pool`，以及存在 `expected_target_id` 时是否与其完全一致。接口同时返回 `semantic_mismatch_task_ids` 和 `semantic_mismatch_count`。历史记录不补造 `expected_target_id`；已有 `selected_pool` 的历史记录仍可通过池成员关系进行语义审计。
