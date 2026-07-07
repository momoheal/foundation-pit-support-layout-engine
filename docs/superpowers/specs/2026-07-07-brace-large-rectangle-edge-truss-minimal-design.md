# Brace 大矩形边桁架最小重排设计

## 目标

只修正 `support_system="brace"` 且触发 `_uses_large_corner_truss(waling_poly)` 的大矩形边桁架场景。第一版目标是让生成顺序更接近人工工程逻辑，并解决边桁架先生成导致的节点分裂、腹杆穿越主对撑和角区几何含义不清的问题。

本设计不改 `straight_truss`，不新增支撑体系，不改变公开 layout 合同，不把大矩形角区重新输出成 `corner` kind。

## 当前问题

当前 `solve_brace()` 的大矩形分支是：

```text
waling
-> main_struts_avoiding_corner_coverage
-> edge_truss
-> truss_coupling_ties
-> secondary_perimeter_supports
-> structural_cross_nodes
-> pillars
```

主要风险：

- 边桁架弦杆节点先生成，后续主撑/连杆可能在相近位置生成独立节点。
- 腹杆只按边桁架面板交替生成，缺少对主撑、角撑语义线、连杆的预检查。
- 角区目前通过边桁架 chord/web 覆盖，但没有显式表达“两侧腰梁取点形成三角形线”的工程约束。
- 现有测试要求大矩形 `brace` 不输出 `corner` 成员，因此第一版不能直接恢复 `corner` kind，否则会扩大 DXF、统计和测试改动面。

## 设计原则

1. 最小改动：只改 `_uses_large_corner_truss` 的 `brace` 分支。
2. 外部合同稳定：`layout` 仍包含原有 buckets、`nodes`、`members`、`outlines`、`stats`、`issues`。
3. 内部锚点优先：先计算角区与主撑锚点，再让边桁架吸附这些锚点。
4. 角撑语义正确：角区锚线按相邻两侧腰梁取点形成三角形线，不使用径向线。
5. 腹杆保守生成：不能解释为结构节点的交叉，宁可跳过，不输出错误构件。

## 最小生成顺序

新的大矩形 `brace` 分支顺序：

```text
waling
-> main_struts_avoiding_corner_coverage
-> corner_triangle_anchors
-> edge_truss(snapped_to_main_and_corner_anchors)
-> truss_coupling_ties
-> secondary_perimeter_supports
-> structural_cross_nodes
-> pillars
```

`corner_triangle_anchors` 是内部数据，不新增公开 layout 字段。它包含：

- 每个凸角相邻两条腰梁边上的多道取点：`left_i`、`right_i`。
- 每道角撑语义线：`left_i -> right_i`。
- 层间连杆语义线：`left_i -> left_{i+1}`、`right_i -> right_{i+1}`。
- 可吸附点集合：所有 `left_i/right_i`。

第一版这些语义线默认只用于吸附与避让，不作为 `corner` 成员输出。

## 组件设计

### `_large_brace_corner_anchor_model(layout, waling_poly)`

新增私有 helper，返回内部 dict：

```python
{
    "anchors": list[Point2D],
    "semantic_lines": list[Geometry],
}
```

生成规则：

- 只处理凸角。
- 每个凸角沿前后两条 waling 边取点。
- 取点距离沿用当前角区覆盖尺度，第一版可使用 `spacing`、`spacing_min`、`truss_panel_max` 和 `corner_layers` 的既有组合，不新增参数。
- 候选线必须被 `waling_poly.buffer(tol).covers(LineString(...))` 覆盖。
- 端点必须位于 `waling_poly.exterior` 附近。

### `_place_edge_truss(..., extra_anchor_points=None, avoid_lines=None)`

扩展现有 helper 的内部参数，但保持调用方兼容：

- `extra_anchor_points`：边桁架外弦杆节点额外吸附点。
- `avoid_lines`：腹杆生成时必须避让的语义线。

大矩形 `brace` 调用传入角区 anchors 与 semantic lines。其它调用路径不传，行为保持不变。

边桁架节点合并顺序：

1. 现有面板节点；
2. 主撑端点 anchors；
3. 角区 anchors；
4. 排序、去重、按边投影合并近点。

腹杆加入前检查：

- 不得与 `avoid_lines` 发生非端点交叉。
- 不得与 `main_strut`、`tie` 发生非端点交叉。
- 仍保留现有 waling 覆盖、角点起点、近距平行检查。

### `solve_brace()`

只调整大矩形分支：

```python
struts = _place_main_struts_avoiding_corner_coverage(...)
corner_model = _large_brace_corner_anchor_model(...)
_place_edge_truss(..., extra_anchor_points=corner_model["anchors"], avoid_lines=corner_model["semantic_lines"])
_place_truss_coupling_ties(...)
```

非大矩形 `brace` 分支不变。

## 测试设计

只新增或调整 `large_rect_120x80_brace` 相关断言：

- 角区 anchor 几何测试：语义角撑端点分别落在相邻两条 waling 边上，不是径向点。
- 边桁架吸附测试：top/bottom/left/right 边的边桁架节点包含主撑端点和角区 anchor 投影点。
- 腹杆避让测试：`truss_web` 不得无节点穿越 `main_strut`；不穿越角区语义线。
- 保留既有外部行为测试：`corner_members == []`，`layout["corners"] == []`，`corner_length == 0.0`。

如果内部 helper 不适合直接测试，可通过 `StrutEngine` 实例调用私有 helper，沿用当前测试文件已有直接实例化 `StrutEngine` 的风格。

## 验证命令

完成实现后必须运行：

```bash
python -m pytest test_strut_minimal.py -v
python run_engineering_strut_checks.py
```

并重新查看 `engineering_check_outputs/large_brace_corner_truss_120x80.png`，确认角区不再呈现径向误导、腹杆没有明显穿越主对撑。

## 非目标

- 不修改 `straight_truss`。
- 不新增公开参数。
- 不新增 `support_system`。
- 不把大矩形角区改成公开 `corner` 成员。
- 不放宽 `strut_validation.py` 来掩盖生成错误。
- 不做截面、承载力、稳定或施工阶段验算。

## 风险与后续

- 第一版仍用 `truss_chord/truss_web` 表达大矩形角区，工程语义比当前清晰，但还不是最终的数据模型。
- 后续可在测试稳定后，把角区语义线升级为显式 `corner` 或 `corner_truss` 成员，并同步 DXF 图层、统计和校核。
- 八字斜撑、腰梁支撑点材料阈值、主体结构避让保留为后续工作，不进入本次最小实现。

