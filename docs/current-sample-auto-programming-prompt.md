# 当前样例自动编程 Prompt

> **已废止：不要执行本文件中的角点直连要求。** 当前最高优先级规范为
> `docs/superpowers/specs/2026-07-29-structural-topology-red-lines-design.md`。
> `iteration11` 的 R39/R40/R45/R47 已被现实图纸复核否决。

你是负责把 `large_brace_corner_truss_120x80` 与 `straight_truss_60x40` 调整到工程可用状态的编程 agent。本文件仅保留历史记录，不再是可执行需求。

## 必须阅读

1. `docs/iteration11-corner-brace-as-diagonal-truss-leg.md`
2. `docs/iteration9-crossing-nodes-and-corner-bounding-feedback.md`
3. `docs/strut_module_requirements.md` 第 12.12 节
4. `docs/current-sample-geometry-design.md` 第 8 节
5. `strut_engine.py` 中 `_place_edge_truss()`、`_corner_truss_anchor_model()`、`_place_corner_truss_legs()`、`_place_perimeter_truss_stiffening()`
6. `test_strut_minimal.py` 中 iteration11 相关测试
7. `run_engineering_strut_checks.py` 中角腿、角点连续性、加劲和 assembly 工程检查

## 必须遵守

- 使用 TDD：先写失败测试并确认失败原因正确，再修改生产代码。
- 当前阶段不新增支撑体系、不做 GUI 重构、不引入力学计算。
- 不得通过放宽验证、隐藏构件或恢复已废弃角区模型制造通过结果。
- R42 非均匀主撑间距依赖尚不存在的荷载/洞口输入，本轮不实现。

## 当前样例必须满足

- 不生成 `corner` 构件，且不存在 tier fan、corner-zone box、`bracket_diagonals` 或 `bracket_rungs`。
- 周边桁架使用标准 panel primitive，外弦和内弦分别在每个角点连续共节点。
- 周边 panel 长度使用 `truss_panel_min/spacing/truss_panel_max`，不得使用 `edge_depth` 代替 panel 长度。
- 每个角只有一根对角桁架腿，腿的成员使用 `_truss_panel_member_specs()` 和 `truss_primitive = "panel"`。
- 角腿终点必须是 `corner_leg_terminal`，并落在内弦或主撑网格真实节点。
- 每个主撑与周边桁架交界 panel 具有局部三角加劲。
- 角邻 panel 和角腿共享 `belongs_to_corner_bracket`，并用 `corner_role` 区分。
- `min_node_separation`、主撑/truss 交点分段、pair-scoped tie 和最小平行净距继续有效。

## 建议测试

- `test_edge_truss_chords_meet_at_corner_vertex`
- `test_corner_leg_uses_shared_truss_primitive`
- `test_corner_leg_terminates_on_inner_chord_or_strut_grid`
- `test_strut_truss_crossing_has_local_stiffening`
- `test_corner_assembly_members_share_grouping_tag`
- `test_separate_corner_tier_fan_is_removed`

## 验证命令

```powershell
python -m ruff check strut_engine.py strut_diagnostics.py test_strut_minimal.py run_engineering_strut_checks.py
python -m pytest test_strut_minimal.py -q
python run_engineering_strut_checks.py
```

完成后刷新两个工程样例的 PNG/DXF，人工检查角腿、周边面板和主撑交点加劲，并报告限定到本轮文件的实际 diff。
