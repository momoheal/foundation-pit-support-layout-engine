# VibeCoding 起始 Prompt：基坑内支撑模块工程实现

你是本工程的主 Agent。你的任务是根据 `docs/` 下的需求、概要设计和任务拆分，独立组织多个子 Agent 完成基坑内支撑模块的实现、测试、质量检查和进度更新。整个过程默认没有人工参与；遇到工程细节不明确时，先从文档上下文、现有代码和最小可行工程原则中做保守决策，并把决策记录到进度或实现说明中。

## 0. 必读上下文

开始任何实现前，必须完整阅读以下文档：

- `docs/strut_module_requirements.md`
- `docs/high-level-design.md`
- `docs/strut_module_technical_notes.md`
- `docs/tasks/progress.md`
- `docs/tasks/*.md`

当前工程重点是把内支撑模块从“能生成若干线段”的几何原型，升级为可选择支撑体系、可校核几何合法性、可统计支撑用量、可输出工程可读 DXF 的布置工具。
最新工程几何目标：支撑体系应优先学习真实工程图中的桁架化特征，包括连续边桁架带、内部多跨主桁架、多三角腹杆网络、相邻主桁架之间的共同受力连杆，以及大开口/核心筒周边的环形支撑。不要把支撑继续做成稀疏孤立线段。边桁架采用已确认的 C 口径：腰梁本身作为边桁架外弦，内侧再偏移一条弦杆形成桁架带。

关键代码文件：

- `main_strut.py`：内支撑 GUI、DXF 读取和输出入口。
- `strut_engine.py`：内支撑核心几何生成引擎。
- `strut_validation.py`：几何校核工具，当前已知存在 `is_connection_point()` 缺失问题。
- `test_strut_minimal.py`：必须作为不依赖 GUI 的最小命令行回归测试入口。
- `launcher.py`：统一启动器。
- `wall_engine.py`：围护桩模块，可参考其职责分离方式。

## 1. 总目标

完成 `docs/tasks/` 中全部模块任务，并让工程满足以下最终条件：

- 内支撑参数统一治理，GUI 路径和命令行测试路径使用同一套参数名。
- 用户可显式选择 `support_system`：`orthogonal`、`brace`、`straight_truss`、`circular`。
- `StrutEngine.solve()` 根据 `support_system` 分发，不再由基坑圆度强制替代用户选择。
- 输出 layout 同时保留旧字段 `waling`、`corners`、`struts`、`ties`、`pillars`，并新增 `nodes`、`members`、`outlines`、`stats`、`issues`。
- 几何校核可报告非法非端点交叉、连接点间距问题、核心筒保护区侵入，并允许合法节点连接。
- 统计输出包含主撑、角撑/八字撑、腹杆、连杆、圆环撑、径向撑、总长度和立柱数量。
- `straight_truss` 应生成连续边桁架带和内部多跨三角桁架网络，不应只生成两条对撑之间的局部小桁架。
- 大基坑的角撑应优先生成角部桁架带，而不是单线角撑与桁架叠加。
- 连杆必须服务于相邻主桁架、主撑或支撑节点共同受力，不得随意跨区乱连。
- 立柱不是所有桁架节点的直接映射，应从主撑交点、环撑/径向撑关键点、连杆端点等候选中筛选，并满足最小间距。
- 八边形或切角近圆基坑应可显式选择 `circular` 圆环支撑，并纳入命令行测试。
- DXF 输出包含需求中规定的基础图层，并为调试节点、问题定位、支撑边线预留增强图层。
- `test_strut_minimal.py` 不依赖 GUI，覆盖矩形、L 形、八边形切角、不规则、圆形/椭圆带核心筒等用例。
- 所有新增和修改代码必须有完整的 `pytest` 单元测试覆盖。
- 最终必须通过 `pytest`、`mypy`、`ruff`。

## 2. 主 Agent 工作方式

你不是单个模块的实现者，而是总控编排者。

你的职责：

1. 阅读并理解全部输入文档。
2. 查看当前代码结构，确认现状与文档描述是否一致。
3. 维护 `docs/tasks/progress.md`，每完成一个模块或阶段就更新勾选状态。
4. 按模块生成子 Agent 任务，让每个子 Agent 负责一个边界清晰的模块。
5. 审查每个子 Agent 的输出，确保接口、数据模型、测试和质量标准一致。
6. 在模块之间做集成，解决冲突，不允许子 Agent 各自发明不兼容的数据结构。
7. 最终运行完整验证命令并修复失败。

子 Agent 默认按以下模块拆分：

- 参数治理模块：`docs/tasks/parameter-governance.md`
- 命令行测试模块：`docs/tasks/cli-testing.md`
- 几何校核模块：`docs/tasks/geometry-validation.md`
- GUI 参数输入模块：`docs/tasks/gui-parameter-input.md`
- 支撑体系分发模块：`docs/tasks/support-system-dispatch.md`
- 节点与构件模型模块：`docs/tasks/node-member-model.md`
- 几何生成策略模块：`docs/tasks/geometry-generation-strategies.md`
- 统计模块：`docs/tasks/statistics-output.md`
- DXF 输出模块：`docs/tasks/dxf-output.md`

## 3. 推荐执行顺序

严格按照 `docs/tasks/progress.md` 的建议顺序推进：

1. P0-1：参数治理模块。
2. P0-2：命令行测试模块基础骨架。
3. P0-3：几何校核模块基础能力。
4. P0-4：GUI 参数输入模块中的 `support_system` 和基础参数传递。
5. P0-5：支撑体系分发模块。
6. P1-1：节点与构件模型模块基础结构。
7. P1-2：几何生成策略模块中的正交对撑、角撑/八字撑和连杆任务。
8. P1-3：统计模块。
9. P1-4：DXF 输出模块基础图层。
10. P2-1：直边桁架相关任务。
11. P2-2：内圆型支撑和核心筒保护区相关任务。
12. P2-3：支撑边线和增强图层相关任务。

每一步都要满足对应任务文件中的“最小任务清单”和“验收清单”。不要跳过 P0 的测试、参数和校核基础直接做复杂几何。

## 4. 全局实现口径

以下口径已经由需求和设计文档确认，所有子 Agent 必须遵守：

- 默认单位为米。
- `support_system` 只允许 `orthogonal`、`brace`、`straight_truss`、`circular`。
- 自动推荐只能作为提示，不得覆盖用户显式选择。
- 对撑作为主撑的主要形式计入 `main_strut_length`，不作为与主撑并列的总类。
- `spacing_min=6.0`、`spacing_max=9.0`、`spacing=9.0` 是连接间距的默认治理口径。
- `safe_dist` 必须传入引擎，并参与生成或校核。
- `margin` 只作为旧测试路径兼容参数，应规范化为 `waling_offset`。
- `circular` 模式必须显式选择，且必须提供 `core_center` 和 `core_diameter`。
- `core_clearance` 不得小于 2.0m。
- 圆环撑当前阶段生成一圈真圆。
- 圆环内部核心筒保护区必须完全空置。
- 角撑/八字撑候选发生非法交叉时，第一阶段采用“跳过候选”的最小策略。
- 默认不生成双向互穿连杆网格。
- 围护支撑的主推荐几何形态是桁架网络：边桁架 + 主桁架 + 三角腹杆 + 合法连杆。
- 边桁架应沿腰梁内侧连续或分段连续生成，不能只在局部两根对撑之间出现。
- 腰梁线应作为边桁架外弦，新增内弦和三角腹杆；不要再生成一条离腰梁很远的“假外弦”。
- 连杆是受力较小但有明确连接语义的共同受力杆件，端点必须落在主桁架、主撑、边桁架或合法节点上。
- `pillar_min_spacing` 控制立柱最小间距，默认采用 `spacing_min`。
- 支撑生成应尽量形成三角单元，避免没有节点语义的矩形网格和随机短线。
- 支撑轮廓当前阶段可先输出边线或预留 `outlines`，完整闭合外包轮廓可作为增强。

## 5. 数据模型统一要求

`StrutEngine.solve()` 最终输出应至少包含：

```python
{
    "waling": [],
    "corners": [],
    "struts": [],
    "ties": [],
    "pillars": [],
    "nodes": [],
    "members": [],
    "outlines": [],
    "stats": {},
    "issues": [],
}
```

节点结构：

```python
{
    "id": "N001",
    "pos": (x, y),
    "kind": "strut_cross",
    "source": ["M001", "M002"],
    "system": "orthogonal",
}
```

构件结构：

```python
{
    "id": "M001",
    "kind": "main_strut",
    "system": "orthogonal",
    "start": "N001",
    "end": "N002",
    "geometry": [(x1, y1), (x2, y2)],
    "width": 0.8,
    "material": "steel",
}
```

统计结构至少包含：

```python
{
    "main_strut_length": 0.0,
    "corner_length": 0.0,
    "truss_web_length": 0.0,
    "tie_length": 0.0,
    "ring_strut_length": 0.0,
    "radial_strut_length": 0.0,
    "total_support_length": 0.0,
    "pillar_count": 0,
}
```

## 6. 测试要求

必须使用 `pytest` 建立单元测试和回归测试。优先把核心算法测试放在不依赖 GUI 的测试文件中。

最低测试覆盖：

- 参数治理：合法体系、非法体系、`margin` 兼容、圆环缺参、`spacing_min > spacing_max`。
- 支撑体系分发：四种 `support_system` 均能进入对应策略；圆形基坑不会强制覆盖用户选择。
- 节点/构件模型：旧字段和新字段并存；节点和构件 ID 唯一；主撑交点可形成 `strut_cross`。
- 几何校核：非法角撑/主撑交叉、连杆互穿、核心筒保护区侵入、主撑与主撑合法交点。
- 几何生成：`rect_60x40`、`l_shape`、`octagon_cut`、`irregular`、`circle_or_ellipse_with_core`、`octagon_circular_core`、`straight_truss_network`、`large_rect_120x80_straight_truss`、`large_rect_120x80_brace`。
- 统计：对撑计入主撑；角撑、腹杆、连杆、圆环撑、径向撑均能统计。
- DXF：基础图层存在；`circular` 有 `RING_STRUT`、`RADIAL_STRUT`、`CORE_PROTECTION`；`straight_truss` 有 `TRUSS_WEB`、`TRUSS_CHORD`。

`test_strut_minimal.py` 必须保留为命令行烟雾测试入口：

```bash
python test_strut_minimal.py
```

脚本必须：

- 不依赖 Tkinter 或人工打开 GUI。
- 输出每个用例的构件数量。
- 输出分类长度统计。
- 输出校核结果摘要。
- 失败时输出构件类型、索引或 ID、坐标和违规原因。
- 任一用例失败时返回非零退出码。

## 7. 质量闸门

最终完成前必须运行并通过：

```bash
python -m pytest
python test_strut_minimal.py
python -m mypy .
python -m ruff check .
```

如果仓库缺少 `pyproject.toml`、`requirements.txt` 或工具配置文件，先补齐最小可用配置，使 `pytest`、`mypy`、`ruff` 可以稳定运行。配置应尽量保守，不要用忽略规则掩盖真实类型错误或 lint 问题。

如依赖缺失，优先在项目依赖声明中补充：

- `ezdxf`
- `shapely`
- `numpy`
- `pytest`
- `mypy`
- `ruff`

`tkinter` 属于标准库 GUI 组件，不应作为 pip 依赖处理。

## 8. 子 Agent 交付格式

每个子 Agent 完成后必须提交以下信息给主 Agent：

- 修改文件列表。
- 完成的任务清单编号。
- 新增或修改的测试。
- 本模块运行过的验证命令及结果。
- 对其他模块的接口影响。
- 未完成事项或技术债。

主 Agent 必须在合并每个子 Agent 结果后：

- 更新 `docs/tasks/progress.md` 中对应模块和执行顺序勾选。
- 检查是否破坏已有测试。
- 如果接口变化影响其他模块，立即派发后续修复任务。

## 9. 防偏航规则

- 不要把材料类型当成支撑体系。
- 不要继续在 `corners` 里混放所有新构件类型而不写入 `members`。
- 不要让 GUI 承担核心算法逻辑。
- 不要让 `StrutEngine` 依赖 Tkinter。
- 不要只修 GUI 而不补命令行测试。
- 不要只让 `test_strut_minimal.py` 打印结果而不返回失败码。
- 不要用宽松 mypy/ruff 配置绕过问题。
- 不要在没有节点/构件模型的情况下继续堆叠复杂线段。
- 不要生成穿过核心筒保护区的任何支撑、径向撑、斜撑、腹杆、连杆或调试线。
- 不要把直边桁架实现成只有一两跨的局部小构件；应优先生成边桁架和多跨三角网络。
- 不要把连杆当作“哪里空就连哪里”的填充线；连杆必须有共同受力语义和合法节点连接。
- 不要把所有桁架节点都生成成立柱；立柱应经过候选评分和最小间距筛选。

## 10. 最终完成定义

只有同时满足以下条件，才可以声明完成：

- `docs/tasks/progress.md` 的模块完成状态全部勾选。
- 每个模块任务文档中的“最小任务清单”和“验收清单”全部完成。
- `python -m pytest` 通过。
- `python test_strut_minimal.py` 通过。
- `python -m mypy .` 通过。
- `python -m ruff check .` 通过。
- 输出 DXF 的基础图层检查通过。
- 主 Agent 已给出最终实现摘要、测试摘要和剩余风险说明。
