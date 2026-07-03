# 基坑内支撑模块技术说明

本文档基于当前项目代码整理，目标是帮助后续推进“布置支撑”模块的修复和重构。项目当前由两个图形模块组成：

- 围护桩布置：`main_retaining.py` + `wall_engine.py`
- 内支撑布置：`main_strut.py` + `strut_engine.py`

当前支撑模块已经能从 DXF 边界读取基坑轮廓，并输出腰梁、角撑/八字撑、对撑、连杆、立柱等图元；但其算法仍处在“几何原型”阶段，尚未形成稳定的工程布置模型。因此你观察到的角撑对撑交叉、桁架缺失、连杆异常、立柱桩异常、支撑轮廓缺失、无法选择桁架或内圆型等问题，本质上来自同一类原因：GUI 参数、算法分支、支撑体系类型、拓扑节点和碰撞校核还没有被统一建模。

## 1. 当前代码结构

### 1.1 启动入口

`launcher.py` 是统一启动器：

- `python launcher.py`：打开模块选择窗口。
- `python launcher.py wall`：直接启动围护结构模块。
- `python launcher.py strut`：直接启动内支撑模块。
- `python launcher.py test`：运行命令行测试和可视化输出。

注意：当前目录不是 Git 仓库，也没有 `requirements.txt`、`pyproject.toml` 等依赖声明文件。项目实际依赖至少包括：

- `ezdxf`：读取和写入 DXF。
- `shapely`：多边形偏移、裁剪、相交判断。
- `numpy`：向量和数值计算。
- `tkinter`：桌面 GUI。
- `matplotlib`：仅测试可视化使用。

### 1.2 围护桩模块

围护模块入口是 `main_retaining.py`，核心引擎是 `wall_engine.py`。

`RetainingApp` 负责：

- 从 DXF 提取基坑边界。
- 选择围护形式。
- 调用 `RetainingWallEngine.solve()`。
- 输出 `_围护布置.dxf`。

`RetainingWallEngine` 负责：

- 根据围护类型确定桩径、桩距、帷幕参数。
- 沿基坑边界布置主桩。
- 对需要止水帷幕的类型，用 Shapely `buffer()` 生成外偏移路径，再沿偏移路径布置三轴搅拌桩。
- 对主桩和帷幕桩做去重。

这个模块的接口比较清晰，能作为支撑模块重构时的参考：GUI 收集参数，引擎只做几何计算，输出结构化 layout，再由 GUI 负责绘图。

### 1.3 内支撑模块

支撑模块入口是 `main_strut.py`，核心引擎是 `strut_engine.py`。

`StrutApp` 负责：

- 读取 DXF 边界。
- 暴露支撑材料、支撑间距、边界避让、安全净距等 GUI 参数。
- 调用 `StrutEngine.solve()`。
- 将结果写入 `_内支撑.dxf`。

`StrutEngine` 当前输出结构如下：

```python
{
    "waling": [],   # 腰梁闭合折线
    "corners": [],  # 角撑、八字撑、圆形内环和斜撑网格均混在这里
    "struts": [],   # 对撑或圆形体系径向撑
    "ties": [],     # 连杆
    "pillars": [],  # 立柱点
}
```

这个结构能绘图，但表达能力不足。尤其是 `"corners"` 同时承载角撑、八字撑、圆形内环、圆形斜撑网格，导致后续很难区分构件类型、做碰撞校核、生成构造节点或按支撑体系开关不同构件。

## 2. 内支撑算法现状

### 2.1 主流程

`StrutEngine.solve()` 首先初始化 layout，然后调用 `_is_circular()` 判断基坑是否近似圆形：

- 圆度 `4 * pi * area / perimeter ** 2 > 0.88` 时走 `_solve_circular()`。
- 否则走 `_solve_rectangular()`。

矩形/多边形体系流程：

1. `_offset_poly(waling_offset)`：将基坑边界向内偏移，得到腰梁轮廓。
2. `_place_struts()`：按包围盒中心生成正交网格，并裁剪到腰梁多边形内。
3. `_place_haunches()`：每根对撑端部生成八字撑。
4. `_place_corner_struts()`：在凸角处生成角撑。
5. `_place_ties()`：在相邻平行对撑 1/3、2/3 位置生成连杆。
6. `_place_pillars()`：在对撑交点和连杆端点生成立柱。

圆形/椭圆形体系流程：

1. 生成腰梁。
2. 根据外半径和间距生成 1~3 道内环。
3. 在腰梁和最外内环之间生成斜撑网格。
4. 生成 8 道中心米字形主撑。
5. 在径向撑与内环交点处布置立柱。

### 2.2 当前可运行结果

用 `StrutEngine([(0,0),(60,0),(60,40),(0,40)], {"spacing": 9.0, "waling_offset": 5.0})` 测试，当前输出为：

- 腰梁节点：5
- 角撑/八字撑：16
- 对撑：8
- 连杆：12
- 立柱：25

但进一步用 Shapely 做线段相交检查，矩形样例中出现：

- 对撑与对撑交点：15 个。这些目前被当作立柱点，是预期内的网格交叉。
- 角撑与对撑非端点相交：12 个。这是异常，说明角撑/八字撑生成没有避让已有对撑。
- 连杆与连杆非端点相交：4 个。这是异常，说明 X 向对撑之间的水平连杆和 Y 向对撑之间的竖向连杆会互相穿越。

这与当前用户反馈的“角撑对撑交叉、连杆无法正常生成、立柱桩无法正常布置”一致。

## 3. 主要问题和根因

### 3.1 角撑和对撑交叉

现状：

- `_place_struts()` 先生成正交对撑。
- `_place_haunches()` 和 `_place_corner_struts()` 后生成斜向构件。
- 斜向构件只裁剪到腰梁多边形内，不检查是否穿越已有对撑、连杆或其他角撑。

根因：

- 当前算法是“逐类追加线段”，不是“基于节点拓扑生成支撑体系”。
- layout 中没有构件 ID、构件类型、端点节点、优先级，也没有碰撞检测结果。
- 角撑不以已有主撑端点、腰梁节点或支撑节点为约束目标，而是按角点臂长直接生成。

建议：

- 在生成斜撑前建立已有构件空间索引。
- 对角撑候选线段执行相交校核。
- 允许角撑端点吸附到最近腰梁节点、主撑端节点或支撑轮廓节点。
- 对非端点相交的候选角撑执行截断、改接节点或丢弃。

### 3.2 无法生成桁架

现状：

- GUI 只有“钢支撑/混凝土支撑”材料选择，没有“支撑体系”选择。
- `StrutEngine._defaults()` 中只有 `strut_type`，但当前计算逻辑并没有按 `strut_type` 分支。
- `_solve_rectangular()` 固定生成“正交对撑 + 八字撑 + 角撑 + 连杆 + 立柱”体系。
- `_solve_circular()` 固定生成“圆弧环撑 + 斜撑网格 + 米字撑”体系。

根因：

- “材料类型”和“支撑平面体系类型”混在了一起，且材料类型未参与构件生成。
- 没有 `support_system` 或 `layout_mode` 这样的控制参数。
- 没有桁架支撑的数据结构，例如上弦杆、下弦杆、腹杆、节点、节间距。

建议新增参数：

```python
{
    "support_system": "orthogonal",  # orthogonal / truss / circular
    "strut_material": "steel",       # steel / concrete
    "truss_depth": 2.0,
    "truss_panel": 3.0,
    "truss_web": "warren",           # warren / pratt / k
}
```

桁架不要作为普通单线对撑绘制，而应作为一组构件：

- 主轴线：用于布置、碰撞和立柱定位。
- 上/下弦杆：与主轴线平行，按 `truss_depth` 偏移。
- 腹杆：按 `truss_panel` 分段生成三角形或 K 形腹杆。
- 节点：每个节间端点和腹杆交点。

### 3.3 无法正常生成连杆

现状：

- `_place_ties()` 会在相邻 X 向对撑之间生成水平连杆。
- 同时也会在相邻 Y 向对撑之间生成竖向连杆。
- 这两组连杆没有互相避让，因此在矩形支撑网格中会产生连杆与连杆交叉。

根因：

- 连杆生成没有全局连杆层级和方向策略。
- 对撑交叉网格已经形成节点，但连杆仍按两个方向独立生成。
- 没有判断连杆是否穿越支撑主节点、立柱、对撑交叉点或其他连杆。

建议：

- 先明确连杆策略：只在主撑之间布置一个方向，还是允许双向连杆但在交点设置节点。
- 对双向连杆，必须把连杆交点纳入节点系统，并决定是否允许该交点成为连接节点。
- 对单向连杆，根据基坑长宽比、主撑方向或用户选项确定主连杆方向。
- 连杆端点应吸附到对撑节点，不能只用坐标比例点直接相连。

### 3.4 无法正常布置立柱桩

现状：

- `_place_pillars()` 将 X 向对撑与 Y 向对撑的所有交点加入立柱。
- 同时将所有连杆端点加入立柱。
- 最后用距离容差去重。

根因：

- 立柱被简化为“交点集合”，没有区分结构节点、构造连接点、临时辅助点。
- 角撑与对撑异常交叉点没有纳入立柱；连杆与连杆交叉点也没有纳入立柱。
- 没有最小间距、边界净距、避让腰梁、避让桩位、立柱网格优化等规则。
- GUI 中的 `safe_dist` 没有传入主流程，实际不参与计算。

建议：

- 先建立统一节点表，再从节点表筛选立柱候选。
- 节点类型至少包括：主撑交点、连杆端点、连杆交点、角撑端点、桁架节点、环撑交点。
- 立柱筛选规则应包含：
  - 到腰梁/边界最小距离。
  - 立柱间最小距离。
  - 是否位于主要受力节点。
  - 是否允许在连杆端点布置。
  - 是否允许在构造辅助点布置。

### 3.5 无法生成支撑轮廓

现状：

- 当前只输出腰梁 `waling`，并没有独立的“支撑轮廓”对象。
- 对撑、角撑、连杆都是线段，没有梁宽、支撑截面宽度或外包轮廓。
- DXF 绘制时用 `lineweight` 表达线宽，但 CAD 几何上仍是中心线。

根因：

- layout 只保存中心线，没有构件截面参数。
- 引擎和绘图层没有分离“结构中心线”和“构件外轮廓”。

建议：

- 每类构件增加宽度参数，如 `strut_width`、`waling_width`、`tie_width`。
- 输出时保留两套数据：
  - `members`：中心线和拓扑，用于计算。
  - `outlines`：按中心线 buffer 后得到的多边形，用于绘图。
- DXF 中用闭合多段线绘制构件外轮廓，而不是只用 `lineweight`。

### 3.6 无法选择支撑是桁架还是内圆型

现状：

- 圆形体系由 `_is_circular()` 自动触发，用户无法强制选择。
- 非圆形基坑无法选择内圆型支撑。
- GUI 没有支撑体系选项。

根因：

- 支撑体系类型被几何形状隐式决定，而不是由用户参数显式决定。
- `_solve_rectangular()` 和 `_solve_circular()` 是硬编码分支，没有统一的策略接口。

建议：

- GUI 增加“支撑体系”下拉框：
  - 正交对撑
  - 桁架支撑
  - 内圆环撑
  - 自动推荐
- 引擎增加分发逻辑：

```python
mode = params.get("support_system", "auto")
if mode == "auto":
    mode = self._recommend_system()

if mode == "orthogonal":
    self._solve_orthogonal(layout)
elif mode == "truss":
    self._solve_truss(layout)
elif mode == "circular":
    self._solve_circular(layout)
else:
    raise ValueError(f"不支持的支撑体系: {mode}")
```

## 4. 建议的数据模型

当前 layout 适合画图，不适合继续扩展。建议把内部计算结果升级为节点 + 构件 + 图层输出三层。

### 4.1 节点

```python
{
    "id": "N001",
    "pos": (x, y),
    "kind": "strut_cross",  # waling / strut_end / strut_cross / tie_end / truss_panel / ring
    "source": ["M001", "M002"],
}
```

### 4.2 构件

```python
{
    "id": "M001",
    "kind": "main_strut",   # waling / main_strut / corner / haunch / tie / truss_chord / truss_web / ring
    "system": "orthogonal", # orthogonal / truss / circular
    "start": "N001",
    "end": "N002",
    "centerline": [(x1, y1), (x2, y2)],
    "width": 0.8,
    "material": "concrete",
    "level": 1,
}
```

### 4.3 输出图元

```python
{
    "layer": "STRUT_MAIN",
    "type": "polyline",
    "points": [(x1, y1), (x2, y2), ...],
    "closed": False,
}
```

这样做的好处：

- 交叉检查可以作用于 `members`。
- 立柱可以从 `nodes` 中筛选。
- 桁架可以表达为多根构件，而不是一条线。
- 支撑轮廓可以由 `members.centerline + width` 统一生成。
- DXF 输出不再依赖业务字段名。

## 5. 推荐重构路线

### 阶段 1：整理参数和 GUI

目标：先让用户选得到支撑体系。

建议修改：

- `main_strut.py` 增加支撑体系下拉框。
- 将 `safe_dist` 真正传给 `StrutEngine`。
- 统一参数名：当前 `run()` 传 `waling_offset`，测试方法 `_use_test_boundary()` 传 `margin`，导致测试路径和真实路径行为不一致。
- 明确材料参数只控制构件宽度、图层、截面默认值，不控制平面体系选择。

建议默认参数：

```python
{
    "support_system": "auto",
    "spacing": 9.0,
    "waling_offset": 5.0,
    "safe_dist": 2.5,
    "strut_material": "steel",
    "main_width": 0.8,
    "tie_width": 0.3,
    "waling_width": 0.8,
}
```

### 阶段 2：增加碰撞校核

目标：先止住角撑、连杆、对撑乱交叉的问题。

建议新增工具函数：

- `segment_intersections(members)`
- `is_endpoint_touch(intersection, member_a, member_b, tol)`
- `validate_member(candidate, existing_members, allowed_touch_kinds)`
- `split_member_at_nodes(member, nodes)`

对新增构件执行：

1. 裁剪到腰梁内部。
2. 检查与既有构件是否非端点相交。
3. 如果相交点允许成为节点，则拆分构件。
4. 如果不允许，则尝试改接、缩短或放弃。

### 阶段 3：修正连杆策略

目标：让连杆可控、可解释。

建议先做简单版本：

- 默认只生成一个方向的连杆。
- 当主撑为双向正交网格时，优先沿短跨方向生成连杆。
- 对需要双向连杆的模式，先把交点写入节点表，再绘图。

### 阶段 4：重做立柱生成

目标：立柱从节点筛选，而不是从裸线段交点临时推导。

建议流程：

1. 主撑生成节点。
2. 连杆生成节点。
3. 角撑/八字撑生成节点。
4. 合并近距离节点。
5. 给节点打标签和权重。
6. 过滤安全距离、最小间距。
7. 输出立柱点或立柱桩图元。

### 阶段 5：实现支撑轮廓

目标：让 DXF 输出具备构件真实宽度。

实现方式：

- 对每条中心线用 `LineString(centerline).buffer(width / 2, cap_style=2, join_style=2)` 生成外轮廓。
- 将轮廓坐标输出到 `STRUT_OUTLINE`、`WALING_OUTLINE`、`TRUSS_OUTLINE` 等图层。
- 保留中心线图层作为辅助或可选调试层。

### 阶段 6：实现桁架支撑

目标：支持用户选择“桁架支撑”。

推荐先实现矩形/近矩形基坑的桁架：

1. 复用 `_place_struts()` 得到主轴线。
2. 对每条主轴线按法向偏移生成两根弦杆。
3. 沿主轴线按 `truss_panel` 分段。
4. 交替连接上下弦节点生成 Warren 式腹杆。
5. 把弦杆端点和腹杆端点加入节点表。
6. 对整体桁架做碰撞校核和轮廓生成。

### 阶段 7：内圆型支撑显式化

目标：圆形/非圆形基坑都可选择内圆型支撑。

建议：

- 将 `_solve_circular()` 改名为 `_solve_ring()` 或 `_solve_inner_ring()`。
- 不再只依赖 `_is_circular()` 自动触发。
- 对矩形或不规则基坑，用内切圆/最大内接近似圆作为环撑中心和半径。
- 支持参数：
  - `ring_count`
  - `ring_spacing`
  - `radial_count`
  - `diagonal_grid`

## 6. 测试建议

当前测试集中在 `launcher.py run_cli_test()`，建议把核心测试拆到单独测试文件，避免 GUI、DXF、可视化和算法验证耦合。

建议建立这些用例：

### 6.1 几何基础用例

- 矩形 60m x 40m。
- L 形基坑。
- 八边形切角基坑。
- 不规则多边形。
- 椭圆/圆形边界。

### 6.2 断言项

每个用例至少断言：

- 腰梁闭合且位于基坑内部。
- 对撑端点落在腰梁或支撑节点上。
- 不存在非允许的构件交叉。
- 连杆端点落在主撑节点上。
- 立柱点在基坑内部且满足最小间距。
- 输出 DXF 文件可保存。
- 支撑轮廓图层存在且闭合。

### 6.3 当前已发现的失败点

矩形 60m x 40m、`spacing=9.0`、`waling_offset=5.0`：

- 角撑与对撑存在非端点相交。
- 连杆与连杆存在非端点相交。

这些可以作为后续回归测试的第一批红灯用例。

## 7. 优先级建议

建议按以下顺序推进：

1. 参数治理：新增 `support_system`，统一 `waling_offset` / `margin`，让 `safe_dist` 生效。
2. 数据模型：引入节点和构件，至少先在引擎内部使用。
3. 碰撞校核：阻断角撑、连杆、支撑之间的非法交叉。
4. 立柱逻辑：从节点系统生成立柱。
5. 支撑轮廓：从中心线 buffer 生成真实构件边界。
6. 桁架模式：先实现沿主撑轴线生成弦杆和腹杆。
7. 内圆型模式：把当前圆形自动分支升级为用户可选体系。

## 8. 关键代码位置速查

- `main_strut.py`
  - `StrutApp.__init__()`：GUI 参数区，目前缺少支撑体系选择。
  - `StrutApp._load_coords()`：DXF 边界读取。
  - `StrutApp.run()`：真实 DXF 输入路径，传入 `waling_offset`。
  - `StrutApp._use_test_boundary()`：测试路径，当前传入 `margin` 而不是 `waling_offset`。

- `strut_engine.py`
  - `StrutEngine._defaults()`：支撑默认参数。
  - `StrutEngine.solve()`：圆形/非圆形分支入口。
  - `StrutEngine._solve_rectangular()`：正交支撑主流程。
  - `StrutEngine._place_struts()`：对撑网格。
  - `StrutEngine._place_haunches()`：八字撑。
  - `StrutEngine._place_corner_struts()`：角撑。
  - `StrutEngine._place_ties()`：连杆。
  - `StrutEngine._place_pillars()`：立柱。
  - `StrutEngine._solve_circular()`：当前圆形/椭圆体系。

- `wall_engine.py`
  - `polygon_orientation()`：被支撑模块复用。
  - `RetainingWallEngine.solve()`：可参考其“参数 -> layout -> GUI 绘图”的职责分离方式。

## 9. 结论

当前支撑模块已经具备可运行的基础：能读取边界、生成腰梁、主撑、斜撑、连杆、立柱并输出 DXF。但它还不是一个稳定的工程布置器，因为缺少三件核心能力：

1. 显式的支撑体系选择。
2. 节点/构件拓扑模型。
3. 全局碰撞校核和构件轮廓生成。

下一步不建议继续在现有 list 字段里追加更多线段。更稳妥的路径是先建立 `nodes + members + drawing entities` 三层模型，再把正交支撑、桁架支撑、内圆型支撑都做成不同策略。这样可以把“是否交叉、哪里立柱、怎么生成连杆、是否画轮廓”这些问题统一到同一套几何和拓扑规则中解决。
