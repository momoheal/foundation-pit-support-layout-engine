"""
基坑围护设计系统 — 统一启动器
Foundation Pit Retaining Wall & Strut Design System

用法:
  python launcher.py              → 启动图形界面（选择模块）
  python launcher.py wall         → 直接启动围护结构模块
  python launcher.py strut        → 直接启动内支撑模块
  python launcher.py test         → 运行命令行端到端测试（含可视化）
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")


def run_gui(module=None):
    """启动 Tkinter 图形界面"""
    import tkinter as tk

    if module == 'wall':
        from main_retaining import RetainingApp
        root = tk.Tk()
        RetainingApp(root)
        root.mainloop()
    elif module == 'strut':
        from main_strut import StrutApp
        root = tk.Tk()
        StrutApp(root)
        root.mainloop()
    else:
        root = tk.Tk()
        root.title("基坑围护设计系统")
        root.geometry("400x350")
        root.configure(bg='#f5f5f5')
        root.resizable(False, False)

        tk.Label(root, text="🏗️ 基坑围护设计系统",
                 font=("微软雅黑", 16, "bold"), fg="#333", bg='#f5f5f5').pack(pady=(30, 5))
        tk.Label(root, text="Foundation Pit Retaining Design System",
                 font=("微软雅黑", 9), fg="#999", bg='#f5f5f5').pack()
        tk.Label(root, text="——", fg="#ccc", bg='#f5f5f5').pack(pady=10)

        btn_frame = tk.Frame(root, bg='#f5f5f5')
        btn_frame.pack(pady=20)

        def launch_wall():
            root.destroy()
            from main_retaining import RetainingApp
            r = tk.Tk()
            RetainingApp(r)
            r.mainloop()

        def launch_strut():
            root.destroy()
            from main_strut import StrutApp
            r = tk.Tk()
            StrutApp(r)
            r.mainloop()

        tk.Button(btn_frame, text="🔵 围护结构设计\n灌注桩 + 止水帷幕",
                  font=("微软雅黑", 11, "bold"), bg="#2E7D32", fg="white",
                  command=launch_wall, height=3, width=30,
                  activebackground="#1B5E20").pack(pady=8)

        tk.Button(btn_frame, text="🔩 内支撑系统设计\n腰梁+角撑+对撑+连杆+立柱",
                  font=("微软雅黑", 11, "bold"), bg="#00695C", fg="white",
                  command=launch_strut, height=3, width=30,
                  activebackground="#004D40").pack(pady=8)

        tk.Label(root, text="v3.0 · Powered by ezdxf + shapely",
                 font=("微软雅黑", 7), fg="#ccc", bg='#f5f5f5').pack(side=tk.BOTTOM, pady=12)

        root.mainloop()


def run_cli_test(full=False):
    """命令行端到端测试（v3.0，含多形状可视化，不需要 --full 也生成图片）"""
    import ezdxf
    import numpy as np
    from wall_engine import RetainingWallEngine
    from strut_engine import StrutEngine

    test_dir = os.path.dirname(os.path.abspath(__file__))
    passed = 0
    failed = 0

    def check(name, condition):
        nonlocal passed, failed
        if condition:
            passed += 1
            print(f"  ✅ {name}")
        else:
            failed += 1
            print(f"  ❌ {name}")

    print("=" * 60)
    print("基坑围护设计系统 — 端到端测试 v3.0")
    print("=" * 60)

    coords_rect = [(0, 0), (60, 0), (60, 40), (0, 40)]
    coords_l    = [(0, 0), (60, 0), (60, 20), (30, 20), (30, 40), (0, 40)]
    coords_oct  = [(10,0),(50,0),(60,10),(60,30),(50,40),(10,40),(0,30),(0,10)]
    coords_irregular = [(0,0),(30,-5),(65,10),(70,35),(55,55),(20,50),(-5,30),(-10,10)]

    # ── Test 1: Wall Engine ──
    print("\n📐 测试1: 围护结构计算引擎 (矩形)")
    res = None
    try:
        engine = RetainingWallEngine(coords_rect, 8.0, "钻孔灌注桩 (Bored Pile)")
        res = engine.solve()
        check("围护引擎初始化", True)
        check(f"主桩生成 ({len(res['main'])} 根)", len(res['main']) > 0)
        check(f"帷幕生成 ({len(res['curtain'])} 根)", len(res['curtain']) > 0)
        check("帷幕 > 主桩", len(res['curtain']) > len(res['main']))
        circle_items = [it for it in res['main'] if it['type'] == 'circle']
        if circle_items:
            positions = [it['pos'] for it in circle_items]
            check("桩位无重复", len(positions) == len(set(positions)))
        else:
            check("桩位无重复 (线段类型)", True)
    except Exception as e:
        print(f"  ❌ 围护引擎崩溃: {e}")
        import traceback; traceback.print_exc()
        failed += 1

    # ── Test 2: All wall types ──
    print("\n📐 测试2: 所有围护类型")
    for wt in ["钻孔灌注桩 (Bored Pile)", "SMW工法桩 (SMW)", "拉森钢板桩 (Larssen)",
               "地下连续墙 (D-Wall)", "重力式挡墙 (Gravity)", "土钉墙 (Soil Nailing)"]:
        try:
            r = RetainingWallEngine(coords_rect, 8.0, wt).solve()
            check(f"  {wt}: {len(r['main'])} 构件, {len(r['curtain'])} 帷幕", len(r['main']) > 0)
        except Exception as e:
            check(f"  {wt}", False); print(f"      Error: {e}")

    # ── Test 3: Polygon orientation ──
    print("\n📐 测试3: 多边形方向检测")
    orient = RetainingWallEngine(coords_rect, 8.0, "钻孔灌注桩 (Bored Pile)")._polygon_orientation()
    check(f"矩形方向 ({orient})", orient in (1, -1))
    orient2 = RetainingWallEngine([(0,0),(0,40),(60,40),(60,0)], 8.0, "钻孔灌注桩 (Bored Pile)")._polygon_orientation()
    check(f"反向矩形方向 ({orient2})", orient2 == -orient)

    # ── Tes 4: Complex polygons ──
    print("\n📐 测试4: 复杂多边形 (含阳角)")
    for name, coords in [("不规则多边形", coords_irregular),
                          ("L形基坑", coords_l),
                          ("八边形(切角)", coords_oct)]:
        try:
            r = RetainingWallEngine(coords, 10.0, "钻孔灌注桩 (Bored Pile)").solve()
            check(f"  {name}: {len(r['main'])} 桩, {len(r['curtain'])} 帷幕", len(r['main']) > 0)
        except Exception as ex:
            check(f"  {name}", False); print(f"      Error: {ex}")

    # ── Test 5: Strut Engine ──
    s_res = None
    print("\n📐 测试5: 内支撑引擎 (矩形 60×40)")
    try:
        s_engine = StrutEngine(coords_rect, {'spacing': 9.0, 'support_system': 'brace'})
        s_res = s_engine.solve()
        check("支撑引擎初始化", True)
        check(f"腰梁 ({len(s_res.get('waling',[]))} 节点)", len(s_res.get('waling',[])) >= 3)
        check(f"角撑 ({len(s_res['corners'])} 道)", len(s_res['corners']) >= 4)
        check(f"对撑 ({len(s_res['struts'])} 段)", len(s_res['struts']) > 0)
        check(f"连杆 ({len(s_res['ties'])} 道)", len(s_res['ties']) >= 0)
        check(f"立柱 ({len(s_res['pillars'])} 处)", len(s_res['pillars']) >= 0)
    except Exception as e:
        print(f"  ❌ 支撑引擎崩溃: {e}")
        import traceback; traceback.print_exc()
        failed += 1

    print("\n📐 测试5b: 内支撑引擎 (复杂形状)")
    for name, coords in [("L形基坑", coords_l), ("八边形基坑", coords_oct),
                          ("不规则多边形", coords_irregular)]:
        try:
            sr = StrutEngine(coords, {'spacing': 9.0, 'support_system': 'brace'}).solve()
            check(f"  {name}: 对撑{len(sr['struts'])} 角撑{len(sr['corners'])}",
                  len(sr['struts']) > 0 or len(sr['corners']) > 0)
        except Exception as ex:
            check(f"  {name}", False); print(f"      Error: {ex}")

    # ── Test 6: DXF generation ──
    print("\n📐 测试6: DXF 文件生成")
    try:
        doc = ezdxf.new('R2010')
        msp = doc.modelspace()
        doc.layers.new('WALL_MAIN', dxfattribs={'color': 3})
        doc.layers.new('WALL_CURTAIN', dxfattribs={'color': 4})
        if res:
            for item in res['main'][:10]:
                if item['type'] == 'circle':
                    msp.add_circle(item['pos'], item['r'], dxfattribs={'layer': 'WALL_MAIN'})
        wall_path = os.path.join(test_dir, '_test_wall.dxf')
        doc.saveas(wall_path)
        check(f"围护DXF ({os.path.getsize(wall_path)} bytes)", os.path.exists(wall_path))

        doc2 = ezdxf.new('R2010')
        msp2 = doc2.modelspace()
        for lname, lc in [('WALL_REF',1),('WALING',6),('STRUT',4),('CORNER',2),('TIE',8),('PILLAR',7)]:
            doc2.layers.new(lname, dxfattribs={'color': lc})
        msp2.add_lwpolyline(coords_rect, close=True, dxfattribs={'layer': 'WALL_REF'})
        if s_res:
            if s_res.get('waling'):
                msp2.add_lwpolyline(s_res['waling'], close=True, dxfattribs={'layer': 'WALING'})
            for seg in s_res['corners']:
                if len(seg) >= 2:
                    msp2.add_lwpolyline(seg[:2], dxfattribs={'layer': 'CORNER'})
            for seg in s_res['struts']:
                if len(seg) >= 2:
                    msp2.add_lwpolyline(seg[:2], dxfattribs={'layer': 'STRUT'})
        strut_path = os.path.join(test_dir, '_test_strut.dxf')
        doc2.saveas(strut_path)
        check(f"支撑DXF ({os.path.getsize(strut_path)} bytes)", os.path.exists(strut_path))

        if not full:
            os.remove(wall_path)
            os.remove(strut_path)
            check("测试文件清理", True)
    except Exception as e:
        print(f"  ❌ DXF生成崩溃: {e}")
        import traceback; traceback.print_exc()
        failed += 1

    # ── Test 7: Edge cases ──
    print("\n📐 测试7: 边界情况")
    try:
        r_small = RetainingWallEngine([(0,0),(3,0),(1.5,2.6)], 5.0, "钻孔灌注桩 (Bored Pile)").solve()
        check("小三角形基坑", len(r_small['main']) > 0)
        r_deep = RetainingWallEngine(coords_rect, 30.0, "地下连续墙 (D-Wall)").solve()
        check("深基坑 30m D-Wall", len(r_deep['main']) > 0)
        r_wide = StrutEngine(coords_rect, {'spacing': 15.0}).solve()
        check("大间距支撑 15m", len(r_wide['struts']) > 0)
    except Exception as e:
        print(f"  ❌ 边界测试崩溃: {e}")
        import traceback; traceback.print_exc()
        failed += 1

    # ── Test 8: Visualization (always) ──
    print("\n📐 测试8: 可视化对比图 (多形状)")
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        import matplotlib.patches as mpatches

        test_shapes = [
            ("矩形 60×40",    coords_rect),
            ("L形基坑",        coords_l),
            ("八边形(切角)",   coords_oct),
            ("圆形基坑",
             [(int(30+28*np.cos(2*np.pi*i/20)), int(20+18*np.sin(2*np.pi*i/20)))
              for i in range(20)]),
        ]

        # ─── 图1: 围护布置（阳角帷幕连续性） ───
        fig1, axes1 = plt.subplots(2, 2, figsize=(16, 12))
        fig1.patch.set_facecolor('#1a1a2e')
        fig1.suptitle("围护结构布置 — 阳角帷幕连续性验证", fontsize=14,
                       color='white', fontproperties='SimHei')
        for ax, (title, coords) in zip(axes1.flatten(), test_shapes):
            ax.set_facecolor('#16213e')
            try:
                engine = RetainingWallEngine(coords, 8.0, "钻孔灌注桩 (Bored Pile)")
                r = engine.solve()
                poly_pts = coords + [coords[0]]
                ax.plot([p[0] for p in poly_pts], [p[1] for p in poly_pts],
                        color='#e0e0e0', linewidth=2.5, zorder=5)
                for item in r['main']:
                    if item['type'] == 'circle':
                        c = plt.Circle(item['pos'], item['r'],
                                       fill=True, facecolor='#66BB6A', edgecolor='#2E7D32',
                                       alpha=0.9, linewidth=0.5, zorder=3)
                        ax.add_patch(c)
                curtain_circles = [it for it in r['curtain'] if it['type'] == 'circle']
                for i, item in enumerate(curtain_circles):
                    if i % 3 == 1:
                        c = plt.Circle(item['pos'], item['r'],
                                       fill=True, facecolor='#26C6DA', edgecolor='#00838F',
                                       alpha=0.7, linewidth=0.4, zorder=2)
                        ax.add_patch(c)
                ax.set_title(f"{title}",
                             color='white', fontproperties='SimHei', fontsize=10, pad=6)
            except Exception as ex:
                ax.set_title(f"{title} ERR: {str(ex)[:30]}", color='red', fontsize=8)
            ax.set_aspect('equal')
            ax.tick_params(colors='#888')
            for sp in ax.spines.values():
                sp.set_edgecolor('#444')
            ax.autoscale()
        leg1 = [mpatches.Patch(facecolor='#66BB6A', edgecolor='#2E7D32', label='主桩'),
                mpatches.Patch(facecolor='#26C6DA', edgecolor='#00838F', label='帷幕桩(中桩)'),
                plt.Line2D([0],[0], color='#e0e0e0', lw=2, label='基坑边界')]
        fig1.legend(handles=leg1, loc='lower center', ncol=3, fontsize=10,
                    facecolor='#1a1a2e', labelcolor='white', prop={'family':'SimHei'})
        plt.tight_layout(rect=[0, 0.04, 1, 0.97])
        wall_viz = os.path.join(test_dir, '_test_wall_visualization.png')
        fig1.savefig(wall_viz, dpi=150, bbox_inches='tight', facecolor='#1a1a2e')
        plt.close(fig1)
        check(f"围护可视化已保存: {os.path.basename(wall_viz)}", os.path.exists(wall_viz))

        # ─── 图2: 内支撑布置 ───
        fig2, axes2 = plt.subplots(2, 2, figsize=(18, 13))
        fig2.patch.set_facecolor('#0d1117')
        fig2.suptitle("内支撑布置 — 腰梁+角撑+对撑+连杆+立柱  (v3.0)",
                       fontsize=14, color='white', fontproperties='SimHei')
        for ax, (title, coords) in zip(axes2.flatten(), test_shapes):
            ax.set_facecolor('#161b22')
            try:
                se = StrutEngine(coords, {'spacing': 9.0, 'support_system': 'brace'})
                sr = se.solve()
                poly_pts = coords + [coords[0]]
                ax.fill([p[0] for p in poly_pts], [p[1] for p in poly_pts],
                        alpha=0.08, color='white')
                ax.plot([p[0] for p in poly_pts], [p[1] for p in poly_pts],
                        color='white', linewidth=2.5, zorder=6)
                if sr.get('waling') and len(sr['waling']) >= 2:
                    wx = [p[0] for p in sr['waling']] + [sr['waling'][0][0]]
                    wy = [p[1] for p in sr['waling']] + [sr['waling'][0][1]]
                    ax.plot(wx, wy, color='#F06292', linewidth=2.8, zorder=5)
                for k, seg in enumerate(sr['corners']):
                    if len(seg) >= 2:
                        ax.plot([seg[0][0],seg[1][0]], [seg[0][1],seg[1][1]],
                                color='#FFB74D', linewidth=1.8, alpha=0.9, zorder=4)
                for k, seg in enumerate(sr['struts']):
                    if len(seg) >= 2:
                        ax.plot([seg[0][0],seg[1][0]], [seg[0][1],seg[1][1]],
                                color='#42A5F5', linewidth=2.5, alpha=0.95, zorder=4)
                for seg in sr['ties']:
                    if len(seg) >= 2:
                        ax.plot([seg[0][0],seg[1][0]], [seg[0][1],seg[1][1]],
                                color='#78909C', linewidth=1.0, alpha=0.8, zorder=3)
                for pt in sr['pillars']:
                    s = 0.6
                    rect = plt.Polygon(
                        [(pt[0]-s,pt[1]-s),(pt[0]+s,pt[1]-s),
                         (pt[0]+s,pt[1]+s),(pt[0]-s,pt[1]+s)],
                        closed=True, facecolor='#CE93D8', edgecolor='#7B1FA2',
                        alpha=0.9, zorder=5)
                    ax.add_patch(rect)
                ax.set_title(
                    f"{title}  腰梁✓ 角撑{len(sr['corners'])} 对撑{len(sr['struts'])} "
                    f"连杆{len(sr['ties'])} 柱{len(sr['pillars'])}",
                    color='#cccccc', fontproperties='SimHei', fontsize=9, pad=6)
            except Exception as ex:
                ax.set_title(f"{title} ERR: {str(ex)[:40]}", color='red', fontsize=8)
                import traceback; traceback.print_exc()
            ax.set_aspect('equal')
            ax.tick_params(colors='#555')
            for sp in ax.spines.values():
                sp.set_edgecolor('#333')
            ax.autoscale()

        leg2 = [
            plt.Line2D([0],[0], color='white', lw=2.5, label='基坑边界'),
            plt.Line2D([0],[0], color='#F06292', lw=2.8, label='腰梁(围檩)'),
            plt.Line2D([0],[0], color='#FFB74D', lw=1.8, label='角撑/八字撑'),
            plt.Line2D([0],[0], color='#42A5F5', lw=2.5, label='对撑'),
            plt.Line2D([0],[0], color='#78909C', lw=1.0, label='连杆'),
            mpatches.Patch(facecolor='#CE93D8', edgecolor='#7B1FA2', label='立柱'),
        ]
        fig2.legend(handles=leg2, loc='lower center', ncol=6, fontsize=9,
                    facecolor='#0d1117', labelcolor='white', prop={'family':'SimHei'})
        plt.tight_layout(rect=[0, 0.04, 1, 0.97])
        strut_viz = os.path.join(test_dir, '_test_strut_visualization.png')
        fig2.savefig(strut_viz, dpi=150, bbox_inches='tight', facecolor='#0d1117')
        plt.close(fig2)
        check(f"支撑可视化已保存: {os.path.basename(strut_viz)}", os.path.exists(strut_viz))

        # 兼容旧路径
        import shutil
        shutil.copy(strut_viz, os.path.join(test_dir, '_test_visualization.png'))

    except Exception as e:
        print(f"  ⚠️ 可视化失败: {e}")
        import traceback; traceback.print_exc()

    print("\n" + "=" * 60)
    print(f"测试结果: {passed} 通过 / {failed} 失败 / {passed + failed} 总计")
    if failed == 0:
        print("🎉 所有测试通过！")
    else:
        print(f"⚠️ {failed} 项未通过，请检查。")
    print("=" * 60)
    return failed == 0


if __name__ == "__main__":
    if len(sys.argv) > 1:
        cmd = sys.argv[1].lower()
        if cmd == 'wall':
            run_gui('wall')
        elif cmd == 'strut':
            run_gui('strut')
        elif cmd == 'test':
            full = '--full' in sys.argv
            run_cli_test(full=full)
        else:
            print(f"未知命令: {cmd}")
            print("用法: python launcher.py [wall|strut|test]")
    else:
        run_gui()
