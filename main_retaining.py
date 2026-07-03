"""
基坑围护结构设计模块 — Retaining Wall Design Module
功能：从 DXF 边界自动布置灌注桩 + 三轴搅拌桩帷幕
"""

import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import ezdxf
from shapely.geometry import Polygon
from wall_engine import RetainingWallEngine


class RetainingApp:
    def __init__(self, root):
        self.root = root
        self.root.title("基坑围护结构设计 V1.1")
        self.root.geometry("520x620")
        self.root.resizable(False, False)

        # ── 样式 ──
        style = ttk.Style()
        style.theme_use('clam')
        bg = '#f5f5f5'
        self.root.configure(bg=bg)

        # ── 标题 ──
        header = tk.Label(root, text="🏗️ 基坑围护结构设计",
                          font=("微软雅黑", 14, "bold"), fg="#2E7D32", bg=bg)
        header.pack(pady=(20, 5))
        tk.Label(root, text="灌注桩 + 三轴搅拌桩止水帷幕自动布置",
                 font=("微软雅黑", 9), fg="#666", bg=bg).pack()

        # ── 参数区 ──
        frame = tk.Frame(root, bg=bg, padx=30)
        frame.pack(fill=tk.X, pady=15)

        row = 0
        tk.Label(frame, text="开挖深度 (m):", bg=bg, font=("微软雅黑", 10)).grid(
            row=row, column=0, sticky="w", pady=6)
        self.depth = tk.DoubleVar(value=8.0)
        tk.Entry(frame, textvariable=self.depth, width=12, font=("微软雅黑", 10)).grid(
            row=row, column=1, sticky="w", pady=6)
        tk.Label(frame, text="（用于确定桩长和选型参数）", bg=bg, fg="#999", font=("微软雅黑", 8)).grid(
            row=row, column=2, sticky="w", pady=6, padx=(8, 0))

        row += 1
        tk.Label(frame, text="围护形式:", bg=bg, font=("微软雅黑", 10)).grid(
            row=row, column=0, sticky="w", pady=6)
        self.wall_type = tk.StringVar(value="钻孔灌注桩 (Bored Pile)")
        types = [
            "钻孔灌注桩 (Bored Pile)",
            "拉森钢板桩 (Larssen)",
            "SMW工法桩 (SMW)",
            "地下连续墙 (D-Wall)",
            "重力式挡墙 (Gravity)",
            "土钉墙 (Soil Nailing)",
        ]
        self.combo = ttk.Combobox(frame, textvariable=self.wall_type,
                                  values=types, width=28, state="readonly",
                                  font=("微软雅黑", 9))
        self.combo.grid(row=row, column=1, columnspan=2, sticky="w", pady=6)

        # ── 快捷参数显示 ──
        self.info_text = tk.Text(root, height=7, width=58, font=("Consolas", 9),
                                 bg='#fafafa', relief=tk.GROOVE, borderwidth=1)
        self.info_text.pack(pady=5)
        self._update_info()
        self.combo.bind('<<ComboboxSelected>>', lambda e: self._update_info())

        # ── 按钮区 ──
        btn_frame = tk.Frame(root, bg=bg)
        btn_frame.pack(pady=15)

        tk.Button(btn_frame, text="📁 选择基坑边界 DXF 并生成围护图",
                  bg="#2E7D32", fg="white", font=("微软雅黑", 10, "bold"),
                  command=self.run, height=2, width=40,
                  activebackground="#1B5E20").pack(pady=5)

        tk.Button(btn_frame, text="🧪 生成测试边界 (矩形基坑 60×40m)",
                  bg="#5D4037", fg="white", font=("微软雅黑", 9),
                  command=self._create_test_boundary, height=2, width=40,
                  activebackground="#3E2723").pack(pady=5)

        # ── 状态栏 ──
        self.status = tk.Label(root, text="就绪 — 请选择 DXF 文件或生成测试边界",
                               bg=bg, fg="#999", font=("微软雅黑", 8))
        self.status.pack(side=tk.BOTTOM, pady=10)

    def _update_info(self):
        """根据所选类型更新参数提示"""
        info = {
            "钻孔灌注桩 (Bored Pile)":
                "桩径: 1000mm | 桩间距: 1200mm\n"
                "帷幕: 3-Φ850 @ 1200 三轴搅拌桩\n"
                "净距: 200mm（桩外边线至帷幕）",
            "SMW工法桩 (SMW)":
                "桩径: 850mm | 搭接: 250mm\n"
                "内插 H 型钢 | 水泥土搅拌墙",
            "拉森钢板桩 (Larssen)":
                "U 型钢板桩 | 小企口锁扣连接\n"
                "适用于浅基坑 (<6m) | 可回收",
            "地下连续墙 (D-Wall)":
                "墙厚: 800mm | 槽段: 6m\n"
                "刚度大 | 适用于深大基坑",
            "重力式挡墙 (Gravity)":
                "水泥土重力坝 | 无内支撑\n"
                "适用于浅基坑 | 坝宽≥0.7H",
            "土钉墙 (Soil Nailing)":
                "土钉 + 喷射混凝土面层\n"
                "适用于放坡开挖 | 逐层施工",
        }
        self.info_text.delete(1.0, tk.END)
        self.info_text.insert(1.0, info.get(self.wall_type.get(), ""))

    def _get_polyline_coords(self, doc):
        """从 DXF 文档中获取基坑边界多段线坐标"""
        msp = doc.modelspace()
        polylines = list(msp.query('LWPOLYLINE'))

        if not polylines:
            # 尝试找 POLYLINE
            polylines = list(msp.query('POLYLINE'))

        if not polylines:
            # 最后尝试找闭合的 LINE 或 ARC
            lines = [e for e in msp if e.dxftype() == 'LINE']
            if lines:
                # 从线段提取端点构建近似边界
                pts = set()
                for l in lines:
                    pts.add((l.dxf.start.x, l.dxf.start.y))
                    pts.add((l.dxf.end.x, l.dxf.end.y))
                if len(pts) >= 3:
                    # 简单凸包作为近似
                    from math import atan2
                    cx = sum(p[0] for p in pts) / len(pts)
                    cy = sum(p[1] for p in pts) / len(pts)
                    sorted_pts = sorted(pts, key=lambda p: atan2(p[1] - cy, p[0] - cx))
                    return list(sorted_pts)
            return None

        if len(polylines) > 1:
            # 让用户选择
            result = messagebox.askyesno(
                "选择多段线",
                f"检测到 {len(polylines)} 条多段线。\n"
                f"是否使用第一条？\n（选'否'则按面积最大自动选择）"
            )
            if result:
                poly = polylines[0]
            else:
                poly = max(polylines, key=lambda p: Polygon([
                    (pt[0], pt[1]) for pt in p.get_points(format='xy')
                ]).area if hasattr(p, 'get_points') else 0)
        else:
            poly = polylines[0]

        coords = poly.get_points(format='xy')
        if len(coords) < 3:
            raise ValueError("多段线至少需要3个顶点")

        # 检查是否闭合
        first = coords[0]
        last = coords[-1]
        if (abs(first[0] - last[0]) > 0.01 or abs(first[1] - last[1]) > 0.01):
            coords = list(coords) + [first]

        return coords

    def run(self):
        """主运行流程"""
        f = filedialog.askopenfilename(
            title="选择基坑边界 DXF 文件",
            filetypes=[("DXF 文件", "*.dxf"), ("所有文件", "*.*")]
        )
        if not f:
            return

        self.status.config(text="处理中...", fg="#1565C0")
        self.root.update()

        try:
            # 1. 读取边界
            doc_in = ezdxf.readfile(f)
            coords = self._get_polyline_coords(doc_in)

            if coords is None:
                messagebox.showerror(
                    "错误",
                    "DXF 文件中未找到可用边界！\n\n"
                    "请确保文件包含：\n"
                    "• 闭合多段线 (LWPOLYLINE/POLYLINE)\n"
                    "• 或至少3条 LINE 组成闭合边界"
                )
                self.status.config(text="失败 — 未找到边界", fg="red")
                return

            # 2. 计算围护布置
            engine = RetainingWallEngine(coords, self.depth.get(), self.wall_type.get())
            res = engine.solve()

            # 3. 生成 DXF 图纸
            doc = ezdxf.new('R2010')
            msp = doc.modelspace()

            # ── 添加标准线型（CAD软件必须，否则报错） ──
            doc.linetypes.add('DASHED', pattern=[0.5, -0.25])
            doc.linetypes.add('CENTER', pattern=[1.25, -0.25, 0.25, -0.25])

            # 图层设置
            doc.layers.new('WALL_BOUNDARY', dxfattribs={'color': 1})   # 红色-边界
            doc.layers.new('WALL_MAIN', dxfattribs={'color': 3})       # 绿色-主桩
            doc.layers.new('WALL_CURTAIN', dxfattribs={'color': 4, 'linetype': 'DASHED'})  # 青色-帷幕
            doc.layers.new('WALL_DIM', dxfattribs={'color': 2, 'linetype': 'CENTER'})     # 黄色-标注

            # 绘制原始边界
            msp.add_lwpolyline(coords, close=True,
                               dxfattribs={'layer': 'WALL_BOUNDARY'})

            # 绘制主桩（跳过零半径）
            pile_count = 0
            for item in res["main"]:
                if item["type"] == "circle":
                    if item["r"] > 0.001:
                        msp.add_circle(item["pos"], item["r"],
                                       dxfattribs={'layer': 'WALL_MAIN'})
                        pile_count += 1
                elif item["type"] == "line":
                    msp.add_line(item["start"], item["end"],
                                 dxfattribs={'layer': 'WALL_MAIN'})

            # 绘制帷幕（跳过零半径）
            curtain_count = 0
            for item in res["curtain"]:
                if item["r"] > 0.001:
                    msp.add_circle(item["pos"], item["r"],
                                   dxfattribs={'layer': 'WALL_CURTAIN'})
                    curtain_count += 1

            # 保存
            out_file = f.replace(".dxf", "_围护布置.dxf")
            doc.saveas(out_file)

            self.status.config(
                text=f"✅ 成功 — {out_file}",
                fg="#2E7D32"
            )
            messagebox.showinfo(
                "生成完成",
                f"围护结构已生成！\n\n"
                f"📐 围护类型：{self.wall_type.get()}\n"
                f"🔵 主桩数量：{pile_count}\n"
                f"🔷 帷幕桩数：{curtain_count}\n"
                f"📁 输出文件：{out_file}"
            )

        except Exception as e:
            import traceback
            traceback.print_exc()
            self.status.config(text=f"失败 — {str(e)[:60]}", fg="red")
            messagebox.showerror("运行错误", f"{str(e)}")

    def _create_test_boundary(self):
        """生成一个矩形测试基坑 DXF"""
        f = filedialog.asksaveasfilename(
            title="保存测试边界 DXF",
            defaultextension=".dxf",
            filetypes=[("DXF 文件", "*.dxf")]
        )
        if not f:
            return

        doc = ezdxf.new('R2010')
        msp = doc.modelspace()

        # 60m × 40m 矩形基坑（逆时针）
        w, h_box = 60, 40
        coords = [(0, 0), (w, 0), (w, h_box), (0, h_box)]
        msp.add_lwpolyline(coords, close=True)

        doc.saveas(f)
        self.status.config(text=f"测试边界已保存 → {f}", fg="#5D4037")
        messagebox.showinfo(
            "测试文件已生成",
            f"矩形基坑边界 (60m×40m) 已保存到：\n{f}\n\n"
            "现在可以点击'选择基坑边界 DXF'按钮加载此文件进行测试。"
        )


if __name__ == "__main__":
    root = tk.Tk()
    app = RetainingApp(root)
    root.mainloop()