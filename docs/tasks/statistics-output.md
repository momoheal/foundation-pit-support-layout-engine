# 统计模块任务

模块目标：从构件模型中输出分类支撑长度、总长度和立柱数量；其中对撑作为主撑的主要形式处理。

对应需求：F3、F12、N3、N5。

相关文件：

- 修改：`strut_engine.py`
- 关联：`strut_validation.py`
- 验证：`test_strut_minimal.py`

## 最小任务清单

- [ ] 任务 1：定义 `stats` 输出字段：`main_strut_length`、`corner_length`、`truss_web_length`、`tie_length`、`ring_strut_length`、`radial_strut_length`、`total_support_length`、`pillar_count`。
- [ ] 任务 2：定义可选明细字段 `main_strut_breakdown`，用于记录对撑形式、方向或支撑体系。
- [ ] 任务 3：实现直线构件长度计算。
- [ ] 任务 4：实现圆环撑长度计算，按真圆周长或圆弧几何长度统计。
- [ ] 任务 5：实现主撑长度统计，将对撑计入 `main_strut_length`。
- [ ] 任务 6：实现角撑/八字撑长度统计，计入 `corner_length`。
- [ ] 任务 7：实现腹杆长度统计，计入 `truss_web_length`。
- [ ] 任务 8：实现连杆长度统计，计入 `tie_length`。
- [ ] 任务 9：实现圆环撑长度统计，计入 `ring_strut_length`。
- [ ] 任务 10：实现径向撑长度统计，计入 `radial_strut_length`。
- [ ] 任务 11：实现 `total_support_length`，汇总所有支撑构件长度，不包含腰梁参考线。
- [ ] 任务 12：实现 `pillar_count`，来自最终立柱列表。
- [ ] 任务 13：将统计模块接入 `StrutEngine.solve()` 输出。
- [ ] 任务 14：将统计模块接入几何校核输出，方便命令行测试显示。
- [ ] 任务 15：为纯正交对撑用例验证 `main_strut_length > 0`。
- [ ] 任务 16：为带角撑用例验证 `corner_length > 0`。
- [ ] 任务 17：为直边桁架用例验证 `truss_web_length > 0`。
- [ ] 任务 18：为内圆型支撑用例验证 `ring_strut_length > 0` 和 `radial_strut_length > 0`。
- [ ] 任务 19：确认输出中不再把“对撑”作为与“主撑”并列的总类。
- [ ] 任务 20：运行 `python test_strut_minimal.py`，确认每个用例都输出统计字段。

## 验收清单

- [ ] `stats` 包含全部必需字段。
- [ ] 对撑计入主撑长度。
- [ ] 支撑总长度能正确汇总分类长度。
- [ ] 立柱数量能从最终立柱结果统计。
- [ ] 命令行测试能显示分类长度统计。
