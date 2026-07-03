# 改进进度总表

本文档用于跟踪 `foundation-pit-support-layout-improvement-design.md` 对应的工程化改进进度。主 Agent 在完成模块、验证阶段或风险收敛后更新。

## 状态图例

- `[ ]` 未开始
- `[~]` 进行中
- `[x]` 已完成

## 总体进度

- [x] 现状审计
- [x] P0 - 结构正确性
- [x] P1 - 数据模型基础
- [~] P2 - 材料与加工现实性
- [~] P3 - 环/径向与角部优化
- [x] P4 - 诊断与清理
- [x] 当前样例全量验证通过

## 本轮目标

先面向工程可用，不新增太多功能，优先把当前 test sample 的结果调好，并保证内核正确。

已确认范围：

- 保留当前四类支撑体系：`orthogonal`、`brace`、`straight_truss`、`circular`
- 不新增支撑类型
- 不做大规模 UI 重构
- 不放宽校核来掩盖错误几何
- 以 `nodes` / `members` / `outlines` / `stats` / `issues` 作为工程模型主输出
- 旧字段 `waling` / `corners` / `struts` / `ties` / `pillars` 继续保留兼容

## 阶段清单

### 现状审计

- [x] 阅读设计文档与改进提示
- [x] 阅读现有代码与测试
- [x] 建立本轮保守工程化设计文档
- [x] 建立三 Agent 分工计划

### P0 - 结构正确性

- [x] 保持支撑体系显式分发，不让自动推荐覆盖用户选择
- [x] 保持主支撑、角撑、桁架、环撑、径向撑的成员类型清晰
- [x] `straight_truss` 对撑改为双向主撑布置，且大样例主撑间距均大于 10m
- [x] 对撑中部不再生成桁架网，改为平行主撑配垂直连杆
- [x] 按工程参考图修正对撑为少数组双主撑：大样例为 2 组竖向双主撑 + 1 组横向双主撑
- [x] 修正设计性交点的节点记录，使端点落在其他构件上的连接也写入 `nodes`
- [x] 避免重复节点类型 token，例如 `truss_node|truss_node|strut_cross`
- [x] 修正节点 snap 逻辑，避免 rounded index 越过 `node_snap_tolerance` 合并节点
- [x] 保持立柱由拓扑候选筛选，不把所有桁架节点直接变成立柱
- [x] 增补对应 pytest

### P1 - 数据模型基础

- [x] 输出 `nodes`
- [x] 输出 `members`
- [x] 输出 `outlines`
- [x] 输出 `stats`
- [x] 输出 `issues`
- [x] 统计由 `members` 派生
- [x] 增补对应 pytest

### P2 - 材料与加工现实性

- [x] 保留 `strut_material` 与构件宽度字段
- [x] 保留按构件类型统计长度
- [ ] 标准段 / 非标准段记录
- [ ] jack zone 规则
- [ ] 更细的材料驱动默认参数

### P3 - 环/径向与角部优化

- [x] `circular` 显式选择时生成环向支撑与径向支撑
- [x] 核心保护区输出并参与校核
- [x] 大基坑 `brace` 样例可生成角部桁架带
- [x] 边桁架改为接近 45 度 K 型腹杆形式
- [x] 大基坑角部 brace 改为多个相似 queen 型桁架单元
- [x] 按工程参考图修正边桁架为连续三角斜腹杆体系，取消易形成零力的轴向 post 杆
- [x] 按工程参考图修正角撑为规则 45 度角部斜撑带，避免角部乱线
- [ ] 更完整的角点定向径向布置
- [ ] 凹角 opt-in 细化处理

### P4 - 诊断与清理

- [x] 诊断 PNG 可从真实求解结果导出
- [x] DXF 图层输出与当前构件类型一致
- [x] `mypy` 类型错误清理
- [x] `ruff` lint 错误清理
- [x] 当前样例验证命令全部通过

## 子 Agent 记录

| 日期 | 模块 | 负责人 | 结果 | 验证 |
| --- | --- | --- | --- | --- |
| 2026-07-03 | 需求核对 | Requirements Agent | 无阻塞问题，可以继续实现 | 输出需求核对清单 |
| 2026-07-03 | 代码编写 | Code Agent | 增加设计性交点显式节点记录，并补充回归测试 | targeted pytest 通过，最终由主 Agent 复测 |
| 2026-07-03 | 验证测试 | Verification Agent | 建立基线，生成 baseline PNG，发现 mypy/ruff 阻塞 | pytest 与 sample 通过；mypy/ruff 初始失败 |
| 2026-07-03 | 集成收口 | Main Agent | 修复 mypy/ruff 阻塞、节点 snap 容差问题，并完成最终验证 | 全部质量门通过 |
| 2026-07-03 | 桁架形式验证 | Verification Agent | 独立验证 45 度 K 型边桁架、queen 型角撑、双向稀疏对撑和中部无桁架 | 全部质量门通过 |
| 2026-07-03 | 工程参考图修正 | Verification Agent | 独立验证规则角撑、稀疏成组对撑、连续三角边桁架、无中部桁架 | 全部质量门通过 |

## 任务追踪

| 编号 | 任务 | 状态 | 备注 |
| --- | --- | --- | --- |
| 0 | 现状审计 | 已完成 | 已阅读输入文档、核心代码和测试 |
| 1 | P0 - 结构正确性 | 已完成 | 显式连接节点与立柱筛选已验证 |
| 2 | P1 - 数据模型基础 | 已完成 | 节点、构件、轮廓、统计、问题输出均保留 |
| 3 | P2 - 材料与加工现实性 | 进行中 | 本轮只保持现有材料字段与统计，不扩展加工规则 |
| 4 | P3 - 环/径向与角部优化 | 进行中 | 已修正边桁架 K 型、角部 queen 型；凹角和更复杂径向布置待后续 |
| 5 | P4 - 诊断与清理 | 已完成 | PNG、DXF 层、类型和 lint 均已验证 |
| 6 | 当前样例全量验证 | 已完成 | 20 个 pytest 用例与 9 个命令行样例通过 |

## 验证记录

- `python -m pytest`：通过，23 passed / 7 warnings
- `python -m pytest test_strut_minimal.py -q`：通过，23 passed / 7 warnings
- `python test_strut_minimal.py`：通过，9 passed / 0 failed
- `python -m mypy .`：通过，Success: no issues found in 9 source files
- `python -m ruff check .`：通过，All checks passed
- 样例诊断图：`engineering_check_outputs/large_rect_120x80_straight_truss.png`
  - 文件大小：128089 bytes
  - 构件数：194
  - 节点数：374
  - 立柱数：58
  - 校核问题数：0
  - 总支撑长度：3056.95
- 验证 Agent 复核图：`engineering_check_outputs/verification_reference_style_large_rect_120x80.png`
  - 文件大小：124655 bytes
  - X 向主撑：2 组双主撑，组距 31.87m
  - Y 向主撑：1 组双主撑
  - 中部 `truss_chord` / `truss_web`：0
  - 边桁架 35-55 度斜腹杆：62 条
  - 边桁架轴向 post 杆：0
  - 大基坑四角角撑：每角 2 条 45 度 `corner`

## 待确认事项

- 是否继续扩展 P2 的标准段、jack zone、材料驱动默认参数。
- 是否继续细化 P3 的凹角和角点定向径向布置。

## 当前结论

本轮保守工程化收口已完成：当前 test sample 结果稳定，内核节点/构件模型、校核、统计、DXF/PNG 输出链路一致，质量门全部通过。

## 2026-07-03 ?????????

??????????????????

- ?????? `brace` ?????? 3 ??????????????????`corner_layers` ?????
- ????????????????????????????????????????????????????????
- ?????`straight_truss` ?????? `tie_interval` ??? 14m ????????????????????????????????
- ??????????????????????????????????????
- ?????`run_engineering_strut_checks.py` ??????????????????????????????????????????????

????????

- `python -m pytest test_strut_minimal.py -q`?23 passed / 7 warnings
- `python test_strut_minimal.py`?9 passed / 0 failed
- `python run_engineering_strut_checks.py`?PASSED: all engineering checks passed
- `python -m mypy .`?Success: no issues found in 9 source files
- `python -m ruff check .`?All checks passed

??????

- `engineering_check_outputs/large_straight_truss_120x80.png`
- `engineering_check_outputs/large_brace_corner_truss_120x80.png`

