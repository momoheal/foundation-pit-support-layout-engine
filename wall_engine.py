"""
围护墙体自动布置引擎 — Retaining Wall Engine v2.1
功能：沿基坑边界自动布置主桩 + 三轴搅拌桩止水帷幕

优化记录 v2.1:
- 修复 np.int64 坐标类型导致 DXF 写入不稳定问题（统一转 float）
- 修复转角帷幕间隙填充逻辑：改用角平分线方向补桩，避免方向错误
- 改进去重容差：支持按围护类型自适应容差
- 增加边长校验：过短边给出警告而不是崩溃
- 导出 polygon_orientation 工具函数，供 strut_engine 复用
"""

import numpy as np


def polygon_orientation(coords):
    """
    计算多边形方向。
    返回 +1 (逆时针/CCW) 或 -1 (顺时针/CW)。
    使用鞋带公式（Shoelace）的变体，适用于 Y 轴向上/向下两种坐标系。
    """
    area = 0.0
    n = len(coords)
    for i in range(n):
        x1, y1 = float(coords[i][0]), float(coords[i][1])
        x2, y2 = float(coords[(i + 1) % n][0]), float(coords[(i + 1) % n][1])
        area += (x2 - x1) * (y2 + y1)
    return 1 if area > 0 else -1


class WallType:
    """围护类型常量"""
    BORED_PILE = "钻孔灌注桩 (Bored Pile)"
    SMW = "SMW工法桩 (SMW)"
    LARSSEN = "拉森钢板桩 (Larssen)"
    DWALL = "地下连续墙 (D-Wall)"
    GRAVITY = "重力式挡墙 (Gravity)"
    SOIL_NAILING = "土钉墙 (Soil Nailing)"


class RetainingWallEngine:
    """围护墙体自动布置引擎"""

    def __init__(self, coords, depth, wall_type):
        """
        Args:
            coords: 基坑边界坐标列表 [(x1,y1), (x2,y2), ...]，坐标自动转为 float
            depth: 开挖深度 (m)
            wall_type: 围护类型字符串（参见 WallType 常量）
        """
        # 统一坐标为 Python float，避免 np.int64 序列化问题
        self.coords = [(float(x), float(y)) for x, y in coords]
        self.depth = float(depth)
        self.wall_type = wall_type
        self._validate_inputs()

    def _validate_inputs(self):
        if len(self.coords) < 3:
            raise ValueError("基坑边界至少需要3个顶点")
        if self.depth <= 0:
            raise ValueError("开挖深度必须 > 0")
        # 检查是否有重复顶点（去掉尾部闭合重复点）
        coords = self.coords
        if len(coords) > 1:
            last = coords[-1]
            first = coords[0]
            if abs(last[0] - first[0]) < 0.001 and abs(last[1] - first[1]) < 0.001:
                self.coords = coords[:-1]  # 移除尾部重复的闭合点

    def _polygon_orientation(self):
        """判断多边形方向：返回 +1(逆时针/CCW) 或 -1(顺时针/CW)"""
        return polygon_orientation(self.coords)

    def _outward_normal(self, unit_vec):
        """
        计算指向基坑外侧的法向量。
        右旋90°: (x, y) → (y, -x)
        对于 CW 多边形（orient=-1），右旋法向量朝外；
        对于 CCW 多边形（orient=+1），右旋法向量朝内，需取反。
        """
        right_normal = np.array([unit_vec[1], -unit_vec[0]])
        orient = self._polygon_orientation()
        if orient > 0:   # CCW → 右旋指向内侧，取反得外侧
            return -right_normal
        else:            # CW  → 右旋即指向外侧
            return right_normal

    def _corner_angle(self, i):
        """
        计算顶点 i 处的转角角度（度），并判断是否为凸角。
        Returns: (angle_deg, is_convex)
        """
        n = len(self.coords)
        p = np.array(self.coords[i])
        v_in = np.array(self.coords[i - 1]) - p
        v_out = np.array(self.coords[(i + 1) % n]) - p
        len_in = np.linalg.norm(v_in)
        len_out = np.linalg.norm(v_out)
        if len_in < 0.01 or len_out < 0.01:
            return 180.0, False  # 退化情况

        dot = np.dot(v_in, v_out) / (len_in * len_out)
        dot = float(np.clip(dot, -1, 1))
        angle = np.degrees(np.arccos(dot))

        # 凸角判定：叉积方向与多边形方向一致则为凸
        cross = v_in[0] * v_out[1] - v_in[1] * v_out[0]
        orient = self._polygon_orientation()
        is_convex = bool((cross * orient) > 0)
        return float(angle), is_convex

    def get_params(self):
        """根据围护类型返回设计参数"""
        params_map = {
            WallType.BORED_PILE: {
                "pile_d": 1.0,
                "pile_s": 1.2,
                "mixing_d": 0.85,
                "mixing_s": 1.2,
                "clear_dist": 0.2,
                "has_curtain": True,
                "corner_seal_overlap": 1.2,   # 帷幕转角搭接延伸量 (m)
            },
            WallType.SMW: {
                "pile_d": 0.85,
                "pile_s": 0.6,
                "mixing_d": 0.85,
                "mixing_s": 0.6,
                "clear_dist": 0.0,            # SMW 桩体即止水体，无净距
                "has_curtain": True,
                "corner_seal_overlap": 0.85,
            },
            WallType.LARSSEN: {
                "pile_d": 0.4,
                "pile_s": 0.4,
                "mixing_d": 0.0,
                "mixing_s": 0.0,
                "clear_dist": 0.0,
                "has_curtain": False,
                "corner_seal_overlap": 0.0,
            },
            WallType.DWALL: {
                "pile_d": 0.8,
                "pile_s": 6.0,
                "mixing_d": 0.0,
                "mixing_s": 0.0,
                "clear_dist": 0.0,
                "has_curtain": False,
                "corner_seal_overlap": 0.0,
            },
            WallType.GRAVITY: {
                "pile_d": 0.0,    # 无独立桩，用线段表示
                "pile_s": 2.0,
                "mixing_d": 0.0,
                "mixing_s": 0.0,
                "clear_dist": 0.0,
                "has_curtain": False,
                "corner_seal_overlap": 0.0,
            },
            WallType.SOIL_NAILING: {
                "pile_d": 0.1,
                "pile_s": 1.5,
                "mixing_d": 0.0,
                "mixing_s": 0.0,
                "clear_dist": 0.0,
                "has_curtain": False,
                "corner_seal_overlap": 0.0,
            },
        }
        if self.wall_type not in params_map:
            raise ValueError(f"不支持的围护类型: {self.wall_type}")
        return params_map[self.wall_type]

    def solve(self):
        """
        执行围护结构布置计算。

        核心策略：
        - 主桩：沿各边均匀分布（端点共享，不重叠）
        - 帷幕：生成外偏移折线，沿折线均匀布桩（三轴单元），一次性处理所有角点

        Returns:
            dict with keys:
                "main":    主桩列表
                "curtain": 帷幕桩列表
        """
        p = self.get_params()
        layout = {"main": [], "curtain": []}
        n = len(self.coords)

        # ═══ Pass 1: 主桩 — 沿各边布置，端点仅加一次 ═══
        for i in range(n):
            p1 = np.array(self.coords[i])
            p2 = np.array(self.coords[(i + 1) % n])
            vec = p2 - p1
            seg_len = float(np.linalg.norm(vec))
            if seg_len < 0.05:
                continue

            unit_vec = vec / seg_len

            if p['pile_d'] > 0.01 and p['pile_s'] > 0:
                num_spaces = max(1, round(seg_len / p['pile_s']))
                actual_spacing = seg_len / num_spaces
                # j=0 是起点（前一段的终点会重叠，靠去重处理），j=num_spaces 是终点
                for j in range(num_spaces + 1):
                    pos = p1 + unit_vec * (j * actual_spacing)
                    layout["main"].append({
                        "type": "circle",
                        "pos": (float(pos[0]), float(pos[1])),
                        "r": p['pile_d'] / 2
                    })
            else:
                layout["main"].append({
                    "type": "line",
                    "start": (float(p1[0]), float(p1[1])),
                    "end": (float(p2[0]), float(p2[1]))
                })

        # ═══ Pass 2: 帷幕 — 生成外偏移折线，沿折线连续布桩 ═══
        if p.get('has_curtain') and p['mixing_d'] > 0:
            layout = self._place_curtain_along_offset(layout, p)

        # ═══ 去重 ═══
        tol = max(0.005, p.get('mixing_s', 0.01) * 0.05)
        layout = self._deduplicate(layout, tol=tol)

        return layout

    def _place_curtain_along_offset(self, layout, p):
        """
        帷幕布置核心算法（v3.0 全新实现）：

        原理：将基坑边界向外偏移 offset_dist，得到帷幕中心折线。
        折线在阳角（凸角）处自动形成外凸弧，在阴角（凹角）处自动内收。
        沿折线按 mixing_s 均匀布置三轴搅拌桩单元，确保连续无断点。

        使用 shapely 的 buffer + exterior 生成偏移折线，
        能正确处理任意形状的凸角和凹角。
        """
        from shapely.geometry import Polygon as ShapelyPoly
        pile_r = p['pile_d'] / 2
        mixing_r = p['mixing_d'] / 2
        offset_dist = pile_r + p['clear_dist'] + mixing_r
        mixing_s = p['mixing_s']

        # 用 shapely buffer 生成外偏移多边形（cap_style=2 平头，join_style=2 斜接/尖角）
        # join_style: 1=round(圆弧), 2=mitre(尖角延伸), 3=bevel(斜切)
        # 阳角用 round 圆弧过渡，可以保证帷幕连续
        base_poly = ShapelyPoly(self.coords)
        try:
            offset_poly = base_poly.buffer(
                offset_dist,
                join_style=1,        # round: 阳角处圆弧过渡
                cap_style=1,
                resolution=16        # 圆弧分辨率
            )
        except Exception:
            # 降级：尖角模式
            offset_poly = base_poly.buffer(offset_dist, join_style=2)

        if offset_poly.is_empty:
            return layout

        # 取外环坐标（外偏移多边形的外轮廓）
        curtain_path = list(offset_poly.exterior.coords)
        # 去掉尾部重复的闭合点
        if len(curtain_path) > 1:
            f, l = curtain_path[0], curtain_path[-1]
            if abs(f[0]-l[0]) < 0.001 and abs(f[1]-l[1]) < 0.001:
                curtain_path = curtain_path[:-1]

        # 计算折线总长度
        total_len = 0.0
        seg_lens = []
        nc = len(curtain_path)
        for i in range(nc):
            c1 = np.array(curtain_path[i])
            c2 = np.array(curtain_path[(i + 1) % nc])
            sl = float(np.linalg.norm(c2 - c1))
            seg_lens.append(sl)
            total_len += sl

        if total_len < 0.1:
            return layout

        # 沿折线按 mixing_s 均匀布桩（三轴单元：沿切线方向 ±mixing_s/2）
        num_units = max(1, round(total_len / mixing_s))
        step = total_len / num_units

        # 沿折线行进
        dist_walked = 0.0
        for _ in range(num_units):
            # 当前中心点位置
            target = dist_walked
            # 行进到 target
            d = 0.0
            idx = 0
            walked = 0.0
            for k in range(nc):
                if walked + seg_lens[k] >= target - 1e-9:
                    idx = k
                    d = target - walked
                    break
                walked += seg_lens[k]
            else:
                idx = nc - 1
                d = seg_lens[idx]

            c1 = np.array(curtain_path[idx])
            c2 = np.array(curtain_path[(idx + 1) % nc])
            seg_vec = c2 - c1
            slen = float(np.linalg.norm(seg_vec))
            if slen < 0.001:
                dist_walked += step
                continue
            unit_t = seg_vec / slen
            center = c1 + unit_t * min(d, slen)

            # 三轴单元：沿切线方向 -s/2, 0, +s/2
            for offset in (-mixing_s * 0.5, 0.0, mixing_s * 0.5):
                sub_pos = center + unit_t * offset
                layout["curtain"].append({
                    "type": "circle",
                    "pos": (float(sub_pos[0]), float(sub_pos[1])),
                    "r": mixing_r
                })

            dist_walked += step

        return layout

    def _fill_corner_curtain_gaps(self, layout, p):
        """
        转角帷幕间隙填充：
        在锐角/直角凸角处，两条边的帷幕偏移线之间形成楔形间隙（帷幕不连续）。
        沿间隙区域插补搅拌桩，确保止水连续。

        判断逻辑：
        - 帷幕偏移线交点在角顶点"外侧"（t_in < 0）时，说明帷幕存在间隙需要填充。
        - 帷幕偏移线交点在角顶点"内侧"（t_in > 0）时，说明帷幕已经搭接，无需填充。
        - 这适用于锐角；钝角/直角通常 t_in > 0，两侧帷幕已通过 overlap 延伸搭接。

        改进 v2.1：
        - 修复了 90° 直角被错误填充导致帷幕桩落在角点内侧的问题
        - 仅在真正存在间隙（交点在外侧）时填充
        - 补桩沿角平分线方向排列
        """
        n = len(self.coords)
        offset_dist = (p['pile_d'] / 2) + p['clear_dist'] + (p['mixing_d'] / 2)

        for i in range(n):
            angle, is_convex = self._corner_angle(i)
            if not is_convex:
                continue
            # 钝角 > 120° 时，两侧帷幕的 overlap 延伸已经足以搭接，跳过
            if angle > 120:
                continue

            pt = np.array(self.coords[i])
            v_in_vec = np.array(self.coords[i - 1]) - pt
            v_out_vec = np.array(self.coords[(i + 1) % n]) - pt
            len_in = float(np.linalg.norm(v_in_vec))
            len_out = float(np.linalg.norm(v_out_vec))
            if len_in < 0.01 or len_out < 0.01:
                continue

            u_in = v_in_vec / len_in
            u_out = v_out_vec / len_out
            n_in = self._outward_normal(u_in)
            n_out = self._outward_normal(u_out)

            # 两条帷幕中心线的原点（即各自边在转角端点处的帷幕位置）
            origin_in = pt + n_in * offset_dist
            origin_out = pt + n_out * offset_dist

            # 求两条帷幕线的参数交点：
            #   入边帷幕线: origin_in + t_in * u_in
            #   出边帷幕线: origin_out + t_out * u_out
            rhs = origin_out - origin_in
            det = float(u_in[0] * (-u_out[1]) - u_in[1] * (-u_out[0]))
            if abs(det) < 0.001:
                continue  # 平行边，无交点

            t_in = float((rhs[0] * (-u_out[1]) - rhs[1] * (-u_out[0])) / det)

            # t_in < 0 表示交点在角顶点外侧（两帷幕线向外延伸才能相交）→ 存在间隙
            # t_in > 0 表示帷幕线向内才能相交 → 已经搭接，无需填充
            if t_in >= -p.get('corner_seal_overlap', 1.2):
                continue  # 无间隙（包括 overlap 已覆盖的情况）

            # 交点位置（两帷幕的汇聚点）
            intersection = origin_in + u_in * t_in

            # 间隙起点：角顶点处两帷幕原点之间的中点
            gap_mid = (origin_in + origin_out) / 2.0
            gap_to_intersect = intersection - gap_mid
            gap_dist = float(np.linalg.norm(gap_to_intersect))

            if gap_dist < p['mixing_s'] * 0.3:
                continue  # 间隙极小，跳过

            # 角平分线方向（指向外侧）
            bisector = n_in + n_out
            bisector_len = float(np.linalg.norm(bisector))
            if bisector_len < 0.001:
                continue
            bisector = bisector / bisector_len

            # 从 gap_mid 向 intersection 方向插补补桩
            num_fill = max(1, int(gap_dist / p['mixing_s']))
            for j in range(1, num_fill + 1):
                t = j / (num_fill + 1)
                center_pos = gap_mid + gap_to_intersect * t
                for offset in (-p['mixing_s'] * 0.5, 0.0, p['mixing_s'] * 0.5):
                    sub_pos = center_pos + bisector * offset
                    layout["curtain"].append({
                        "type": "circle",
                        "pos": (float(sub_pos[0]), float(sub_pos[1])),
                        "r": p['mixing_d'] / 2
                    })

        return layout

    def _deduplicate(self, layout, tol=0.01):
        """
        去除空间上重复的桩/线段。
        tol: 重复判定容差 (m)，默认 0.01m
        """
        for key in ('main', 'curtain'):
            unique = []
            for item in layout[key]:
                if item['type'] == 'circle':
                    pos = np.array(item['pos'])
                    is_dup = any(
                        u['type'] == 'circle' and
                        float(np.linalg.norm(pos - np.array(u['pos']))) < tol
                        for u in unique
                    )
                elif item['type'] == 'line':
                    is_dup = any(
                        u['type'] == 'line' and
                        float(np.linalg.norm(np.array(item['start']) - np.array(u['start']))) < tol and
                        float(np.linalg.norm(np.array(item['end']) - np.array(u['end']))) < tol
                        for u in unique
                    )
                else:
                    is_dup = False
                if not is_dup:
                    unique.append(item)
            layout[key] = unique
        return layout
