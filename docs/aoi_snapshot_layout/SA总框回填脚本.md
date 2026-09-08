# SA 目标总区回填

脚本：`server/statistics/backfill_sa_target_area.py`。统一区域 ID 为 `left_target_area`。

脚本以只读方式打开原库，默认预览。`--apply` 使用 SQLite backup 生成数据库副本，只在副本中增加 SA 总框、更新布局签名及选中 SA 任务的原始帧路径。原库和原始眼动文件保持不变。输出目录必须不存在。

## 使用方法

在项目根目录执行预览：

```powershell
python server/statistics/backfill_sa_target_area.py --infer-current-layout
```

生成回填副本：

```powershell
python server/statistics/backfill_sa_target_area.py --infer-current-layout --apply --output-dir server/data/gaze/derived/sa_target_area_run2
```

可用 `--gaze-db 数据库路径` 指定源库，`--task-id 4` 限定任务，重复提供 `--task-id` 可选择多个任务。脚本仅处理 `SA_THREAT_RESPONSE`，拒绝未结束任务和未闭合快照。

## 坐标来源

`--infer-current-layout` 显式选择当前代码布局推算：SA 画布为 800×600 CSS px，下方列表同宽居中，画布与列表间有 8px 间距和 1px 上边框。

```text
总框 left/right = 下方列表 left/right
总框 bottom = 列表 top - 9 / viewport_height
总框 top = 总框 bottom - 600 / viewport_height
```

该方式要求历史界面布局与上述代码一致、列表未被裁剪。脚本检查对齐、视口尺度、列表宽度和边缘、总框范围及可见 AI 小框包含关系；这些检查不能证明历史 DOM 完全一致。推算结果在 `binding.geometry_source` 和审计记录中标为 `inferred_current_layout_800x600_gap8_border1`，不是直接采集坐标。

有实测边界时使用 `--bounds-json bounds.json` 替代布局推算。JSON 以数据库快照数值 `id` 为键，每条包含归一化 `left/top/right/bottom`、可选布尔 `visible` 和必填来源文字 `evidence`。所选缺失总框的快照必须逐条提供边界，不能将示意图坐标当作实测值。已有同名总框不重复添加；发现拼错的 `left_tartet_area` 时停止并报告。

## 输出与眼动命中

- `gaze_records.db`：包含 SA 总框的离线副本，保留任务 ID、revision、有效区间及其他 AOI。
- `raw/<任务散列>/raw_gaze.jsonl`：对应 SA 任务的眼动副本；仅更新有效、对齐且处于匹配版本有效区间内的 `aoi_hits`，保留原有 `hit/hits`。
- `backfill_report.json` 与库内 `sa_aoi_backfill_audit`：源库、快照、区域来源及处理数量。

原始帧文件缺失且数据库帧数非零时停止。帧数为零且文件缺失时输出空眼动文件，并在报告中标明缺失；不会生成虚构采样。无效眼动、未知 revision、区间外帧保留原样。

数据库中非选中任务的 `data_dir` 仍引用原数据目录，因此输出是离线修正副本，不是包含所有任务原始文件的独立归档。分析回填后的 SA 数据应指定副本数据库。

## 已生成数据

路径：`server/data/gaze/derived/sa_target_area_backfill_20260907/gaze_records.db`。

| 任务 | 快照 | revision | 总框归一化范围 | 来源 |
| --- | --- | --- | --- | --- |
| 4 | 5 | 1 | (0.1104, 0.1208) → (0.5288, 0.6784) | 当前布局推算 |
| 4 | 6 | 2 | (0.1104, 0.1208) → (0.5288, 0.6784) | 当前布局推算 |

这组数据无原始眼动帧，已补齐 2 条快照，实际重算眼动帧数为 0。前端与后端在线采集协议仍未增加总框；本脚本用于历史记录的离线回填。
