# 参数治理模块任务

模块目标：统一内支撑参数默认值、兼容旧参数、校验支撑体系和必填参数，确保 GUI 路径和命令行测试路径使用同一套参数。

对应需求：F1、F2、F3、F4、N3、N4。

相关文件：

- 修改：`strut_engine.py`
- 修改：`main_strut.py`
- 验证：`test_strut_minimal.py`

## 最小任务清单

- [ ] 任务 1：在 `StrutEngine` 中定位当前默认参数入口，例如 `_defaults()`。
- [ ] 任务 2：将默认参数整理为单一入口，包含基础参数、桁架参数和圆环撑参数。
- [ ] 任务 3：新增 `spacing_min` 默认值 `6.0`。
- [ ] 任务 4：新增 `spacing_max` 默认值 `9.0`。
- [ ] 任务 5：保留 `spacing` 默认值 `9.0`，作为旧参数兼容目标间距。
- [ ] 任务 6：新增或修正 `waling_offset`，并兼容旧测试路径中可能出现的 `margin`。
- [ ] 任务 7：新增或修正 `safe_dist`，默认按米解释，并保留给几何生成或校核使用。
- [ ] 任务 8：新增 `support_system` 默认值，默认使用 `orthogonal`，除非调用方显式传入其他值。
- [ ] 任务 9：实现 `support_system` 白名单校验，只允许 `orthogonal`、`brace`、`straight_truss`、`circular`。
- [ ] 任务 10：未知 `support_system` 抛出明确 `ValueError`，错误信息包含非法值。
- [ ] 任务 11：实现 `spacing_min <= spacing <= spacing_max` 的基础校验或修正策略。
- [ ] 任务 12：当 `spacing_min > spacing_max` 时抛出明确错误。
- [ ] 任务 13：当 `support_system=circular` 时校验 `core_center` 和 `core_diameter` 是否存在。
- [ ] 任务 14：当 `core_clearance < 2.0` 时修正到 2.0 或抛出明确错误，并在实现中保持一种一致策略。
- [ ] 任务 15：当 `support_system=straight_truss` 时确保 `truss_depth`、`truss_panel_min`、`truss_panel_max` 有默认值。
- [ ] 任务 16：把参数规范化后的结果保存为 `self.params`，后续模块只读取规范化参数。
- [ ] 任务 17：在 `test_strut_minimal.py` 中增加参数治理最小用例：合法体系、非法体系、`margin` 兼容、圆环缺参。
- [ ] 任务 18：运行 `python test_strut_minimal.py`，确认参数治理用例能输出清晰失败原因。

## 验收清单

- [ ] GUI 路径和命令行测试路径使用同一套参数名。
- [ ] 未知支撑体系抛出明确错误。
- [ ] `margin` 不再导致测试路径和真实路径行为分叉。
- [ ] 圆环撑缺少核心筒参数时不会静默生成错误结果。
- [ ] 默认单位均按米解释。
