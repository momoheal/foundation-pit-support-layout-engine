# 基坑内支撑工程化加固设计

## 已确认目标

在不新增支撑类型、不过度扩功能的前提下，把当前内支撑生成器收敛成一个工程可用的程序。

本次优先目标是现有样例集与当前输出链路：

- 保留旧版 DXF 输出字段
- 保留当前四类支撑体系：`orthogonal`、`brace`、`straight_truss`、`circular`
- 修正几何生成，使构件合法连接并保持在有效支撑区域内
- 保持校核、统计和 DXF 输出与节点/构件模型一致
- 产出一张可直接检查的样例诊断图

## 非目标

- 不新增支撑体系
- 不做大规模 UI 重构
- 不新增新的几何大类
- 不做大范围优化
- 不通过放宽校核来掩盖错误几何

## 工程原则

- 几何正确优先，外观服从正确性。
- 节点/构件模型是校核、统计和 DXF 输出的唯一事实来源。
- 旧字段只保留兼容，不作为主数据源。
- 不能合法连接的构件，不应被输出。
- 用户显式选择的支撑体系，不得被悄悄覆盖。

## 当前修复范围

本次只处理当前实现文件：

- `strut_engine.py`
- `strut_validation.py`
- `strut_diagnostics.py`
- `main_strut.py`
- `test_strut_minimal.py`
- `docs/tasks/progress.md`

## 设计摘要

### 1. 参数治理

把所有支撑参数统一收口到一处，仅保留已有的兼容别名。

规则：

- `support_system` 保持显式且优先
- `margin` 仅在兼容场景下映射到 `waling_offset`
- `strut_type` 仅在兼容场景下映射到 `strut_material`
- 必须强制满足 `spacing_min <= spacing <= spacing_max`
- `pillar_min_spacing` 默认等于 `spacing_min`
- `circular` 必须提供 `core_center` 和 `core_diameter`
- `core_clearance` 不得低于 `2.0`

### 2. 几何生成

保留当前支撑体系分发，但每个分支都要生成工程上合法的构件，而不是装饰线。

各体系要求：

- `orthogonal`：生成 waling、裁剪后的主支撑、连接合理的拉杆和基于有效节点的立柱候选
- `brace`：在正交支撑基础上，仅在合法区域生成角部加固
- `straight_truss`：生成真实的边桁架带和内部桁架腹杆网格，不输出孤立短线
- `circular`：生成完整环向支撑、径向支撑和清晰的核心保护区

通用规则：

- 所有构件都必须被裁剪或拒绝在 waling / 支撑区域之外
- 设计性交点必须写入 `nodes`
- 未经结构节点确认的非端点交叉视为错误
- 立柱只能从真实拓扑节点中筛选，不能把所有节点都变成立柱

### 3. 校核

校核保持严格，属于正确性的一部分，而不是可有可无的提示系统。

必须检查：

- 非端点非法交叉
- 设计性连接点是否合法
- 主支撑连接间距是否合理
- circular 布局中的核心保护区是否被侵入
- `nodes`、`members`、`outlines`、`stats`、`issues` 的结构一致性

### 4. 统计与输出

统计必须只从构件模型派生。

必须输出：

- 旧桶：`waling`、`corners`、`struts`、`ties`、`pillars`
- 新模型：`nodes`、`members`、`outlines`、`stats`、`issues`
- 构件长度统计：主支撑、角部构件、桁架腹杆、拉杆、环向支撑、径向支撑、总支撑长度
- 与当前文档一致的 DXF 图层输出

### 5. 样例调优

现有样例集是回归锚点，不是为了演示而拼出来的图。

重点样例：

- `rect_60x40`
- `l_shape`
- `octagon_cut`
- `irregular`
- `circle_or_ellipse_with_core`
- `octagon_circular_core`
- `straight_truss_rect`
- `large_rect_120x80_straight_truss`
- `large_rect_120x80_brace`

每个样例至少验证其中一项：

- 几何裁剪合法
- 节点合并正确
- 支撑体系分发正确
- 立柱筛选可用
- 圆形核心保护正确
- 桁架拓扑可用

### 6. 样例图片

几何稳定后，使用 `strut_diagnostics.py` 从真实求解结果导出一张诊断 PNG。

图片应显示：

- 基坑边界
- 构件模型
- 立柱位置
- 足够清晰的拓扑密度，便于肉眼核对

## 实现形态

预计会改动的方向：

- 收紧 `strut_engine.py` 中的参数归一化和体系分发
- 修正某些分支里几何含义不清或强度不足的构件生成
- 让 `strut_validation.py` 与真实的节点/构件模型保持一致
- 让 `main_strut.py` 的 DXF 输出与修正后的构件类型同步
- 加强 `test_strut_minimal.py`，让样例回归更快暴露问题

## 验证标准

以下全部通过，才算完成：

- `python -m pytest`
- `python test_strut_minimal.py`
- `python -m mypy .`
- `python -m ruff check .`
- 至少导出一张样例诊断 PNG

## 验收标准

- 样例布局稳定，且具备工程可用性
- 生成、校核、统计、DXF 输出之间保持内部一致
- 不为了让图“更满”而输出不合法几何
- 当前样例图看起来像一个合理的支撑方案，而不是松散草图
