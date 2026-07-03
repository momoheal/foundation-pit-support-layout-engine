# GUI 参数输入模块任务

模块目标：在 `main_strut.py` 中提供内支撑模块所需的用户输入入口，并把 GUI 参数完整传入 `StrutEngine`。

对应需求：F1、F2、F10、N1、N3、N4。

相关文件：

- 修改：`main_strut.py`
- 关联：`strut_engine.py`
- 验证：`test_strut_minimal.py`

## 最小任务清单

- [ ] 任务 1：梳理 `main_strut.py` 中现有 GUI 参数字段，记录当前字段名、默认值和传入 `StrutEngine` 的参数名。
- [ ] 任务 2：新增“支撑体系”下拉框，选项固定为 `orthogonal`、`brace`、`straight_truss`、`circular`。
- [ ] 任务 3：确保“支撑体系”选择值以 `support_system` 字段传入 `StrutEngine`。
- [ ] 任务 4：将材料字段命名为 `strut_material`，避免继续把材料类型当成支撑体系类型。
- [ ] 任务 5：补齐基础参数输入字段：`spacing_min`、`spacing_max`、`spacing`、`waling_offset`、`safe_dist`、`main_width`、`tie_width`、`waling_width`、`enable_haunch`。
- [ ] 任务 6：补齐桁架参数输入字段：`truss_depth`、`truss_panel_min`、`truss_panel_max`、`truss_web_with_main`、`truss_web_without_main`。
- [ ] 任务 7：补齐内圆型支撑参数输入字段：`core_center`、`core_diameter`、`core_clearance`、`ring_edge_clearance`、`radial_spacing_min`、`radial_spacing_max`、`radial_count`。
- [ ] 任务 8：实现核心筒中心 DXF 选点入口，并把选点结果写入 `core_center`。
- [ ] 任务 9：当 `support_system=circular` 且缺少 `core_center` 或 `core_diameter` 时，在 GUI 层提示缺少参数。
- [ ] 任务 10：统一真实 DXF 输入路径和测试边界路径的参数组装逻辑，确保二者传入同一套参数名。
- [ ] 任务 11：确认 `safe_dist` 不只停留在 GUI 字段，而是确实传入 `StrutEngine`。
- [ ] 任务 12：保留现有 DXF 读取和输出入口，不改变围护桩模块启动逻辑。
- [ ] 任务 13：手动运行 GUI，确认四种支撑体系均可选择且不会阻塞启动。
- [ ] 任务 14：用测试边界运行一次内支撑生成，确认参数字典包含 `support_system`、`safe_dist` 和连接间距范围。
- [ ] 任务 15：更新界面默认值，使默认单位仍按米解释。

## 验收清单

- [ ] GUI 能选择四种支撑体系。
- [ ] `StrutEngine` 收到 `support_system` 参数。
- [ ] `safe_dist`、`spacing_min`、`spacing_max` 能从 GUI 传入算法层。
- [ ] `strut_material` 不再冒充支撑体系。
- [ ] `circular` 模式缺少核心筒参数时有明确提示。
