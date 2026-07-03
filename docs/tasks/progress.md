# 内支撑模块任务总体进度

本文件汇总 `docs/tasks/` 下各模块任务完成状态。模块完成标准：对应模块文件中的“最小任务清单”和“验收清单”全部勾选。

输入文档：

- `docs/strut_module_requirements.md`
- `docs/high-level-design.md`

## 模块完成状态

- [x] [GUI 参数输入模块](gui-parameter-input.md)
- [x] [参数治理模块](parameter-governance.md)
- [x] [支撑体系分发模块](support-system-dispatch.md)
- [x] [几何生成策略模块](geometry-generation-strategies.md)
- [x] [节点与构件模型模块](node-member-model.md)
- [x] [几何校核模块](geometry-validation.md)
- [x] [统计模块](statistics-output.md)
- [x] [DXF 输出模块](dxf-output.md)
- [x] [命令行测试模块](cli-testing.md)

## 建议执行顺序

- [x] P0-1：完成参数治理模块。
- [x] P0-2：完成命令行测试模块基础骨架。
- [x] P0-3：完成几何校核模块基础能力。
- [x] P0-4：完成 GUI 参数输入模块中的 `support_system` 和基础参数传递。
- [x] P0-5：完成支撑体系分发模块。
- [x] P1-1：完成节点与构件模型模块基础结构。
- [x] P1-2：完成几何生成策略模块中的正交对撑、角撑/八字撑和连杆任务。
- [x] P1-3：完成统计模块。
- [x] P1-4：完成 DXF 输出模块基础图层。
- [x] P2-1：完成直边桁架相关任务。
- [x] P2-2：完成内圆型支撑和核心筒保护区相关任务。
- [x] P2-3：完成支撑边线和增强图层相关任务。

## 当前默认状态

- [x] 已开始实现。
- [x] 已运行 `python test_strut_minimal.py`。
- [x] 已完成当前文档范围内的模块验收。

## 当前验证证据

- `python -m pytest`：通过，8 passed。
- `python test_strut_minimal.py`：通过，9 passed / 0 failed。
- `python -m mypy .`：通过，no issues found。
- `python -m ruff check .`：通过，All checks passed。
- `python launcher.py test`：通过，33 passed / 0 failed。

## 说明

- `circular` 模式在 GUI 中提供核心筒中心数值输入；如果 DXF 中存在 `POINT` 实体，则优先作为核心筒中心。
- 直边桁架已采用腰梁作为边桁架外弦，并生成内部主桁架、三角腹杆和连接相邻主桁架/主撑节点的合法连杆。
- 八边形/切角近圆基坑已加入显式 `circular` 圆环撑命令行测试。
- 大基坑已加入 `large_rect_120x80_straight_truss` 和 `large_rect_120x80_brace` 回归测试；角部支撑可生成局部桁架带，立柱按候选评分和最小间距筛选。
