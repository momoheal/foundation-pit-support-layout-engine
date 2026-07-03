# 支撑体系分发模块任务

模块目标：让 `StrutEngine` 根据用户显式选择的 `support_system` 分发到不同支撑生成策略，自动推荐只作为辅助提示。

对应需求：F1、F5、F6、F9、F10、N1、N3。

相关文件：

- 修改：`strut_engine.py`
- 关联：`main_strut.py`
- 验证：`test_strut_minimal.py`

## 最小任务清单

- [ ] 任务 1：定位 `StrutEngine.solve()` 当前入口和圆形/非圆形自动分支逻辑。
- [ ] 任务 2：新增 `solve_orthogonal()` 策略入口，先复用现有矩形/多边形正交对撑主流程。
- [ ] 任务 3：新增 `solve_brace()` 策略入口，先复用正交对撑并启用角撑/八字撑相关流程。
- [ ] 任务 4：新增 `solve_straight_truss()` 策略入口，先保留最小可运行骨架并返回兼容 layout。
- [ ] 任务 5：新增 `solve_circular()` 策略入口，明确只由 `support_system=circular` 触发。
- [ ] 任务 6：移除“只根据基坑形状自动进入圆形支撑体系”的强制行为。
- [ ] 任务 7：如果保留自动推荐函数，将其命名为 `_recommend_system()`，并只返回提示值，不覆盖用户选择。
- [ ] 任务 8：在 `solve()` 中实现 `support_system` 分发。
- [ ] 任务 9：确保每个策略都返回包含 `waling`、`corners`、`struts`、`ties`、`pillars` 的兼容 layout。
- [ ] 任务 10：确保每个策略都预留或返回 `nodes`、`members`、`outlines`、`stats`、`issues` 字段。
- [ ] 任务 11：为 `orthogonal` 写一个最小命令行用例，确认能生成腰梁和主撑。
- [ ] 任务 12：为 `brace` 写一个最小命令行用例，确认不会生成直边桁架。
- [ ] 任务 13：为 `straight_truss` 写一个最小命令行用例，确认策略入口被调用。
- [ ] 任务 14：为 `circular` 写一个最小命令行用例，确认必须显式选择才进入圆环撑逻辑。
- [ ] 任务 15：为非法支撑体系写一个最小用例，确认抛出明确错误。

## 验收清单

- [ ] `StrutEngine.solve()` 根据 `support_system` 分发。
- [ ] 不再由基坑圆度强制替代用户选择。
- [ ] 四种策略入口均可被命令行测试覆盖。
- [ ] 未知体系值有明确错误。
- [ ] 自动推荐不会替代用户确认。
