# -*- coding: utf-8 -*-
"""HITOS 端到端可用性：上传→解析(计时)→审查→问题卡片→viewer 楼层/房间导航→进室内。"""
import sys, time, pathlib, re
from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding="utf-8")
BASE = "http://localhost:" + (sys.argv[1] if len(sys.argv) > 1 else "8502")
IFC = r"C:\Users\32800\Desktop\NTU pre\ArchCheck\bim\test-suites\real-project\HITOS-Large-Building_IFC2x3.ifc"
SHOTS = pathlib.Path(__file__).parent / "_hitos_e2e"
SHOTS.mkdir(parents=True, exist_ok=True)

logs = []
def L(s):
    print(s); sys.stdout.flush()

with sync_playwright() as p:
    br = p.chromium.launch(channel="chrome", headless=True)
    pg = br.new_page(viewport={"width": 1700, "height": 1100})
    pg.on("console", lambda m: logs.append(f"[{m.type}] {m.text}"))
    pg.on("pageerror", lambda e: logs.append(f"[pageerror] {e}"))

    t0 = time.time()
    pg.goto(BASE, wait_until="networkidle")
    L(f"goto done t={time.time()-t0:.1f}s")
    pg.set_input_files('input[type="file"]', IFC)
    L("uploaded HITOS, waiting for parse…")
    pg.wait_for_function(
        "() => document.body.innerText.includes('开始审查')", timeout=600000)
    t_parse = time.time() - t0
    L(f"PARSE OK t={t_parse:.1f}s")
    time.sleep(2)

    pg.get_by_role("button", name="开始审查").first.click()
    L("reviewing…")
    t1 = time.time()
    pg.wait_for_function(
        "() => document.body.innerText.includes('审查问题')", timeout=600000)
    L(f"REVIEW OK t={time.time()-t1:.1f}s (total {time.time()-t0:.1f}s)")
    time.sleep(6)
    pg.screenshot(path=str(SHOTS / "01_review_result.png"))

    # 问题卡片数量
    n_exp = pg.locator('div[data-testid="stExpander"]').count()
    n_loc = pg.get_by_role("button", name=re.compile("定位到 3D")).count()
    L(f"expanders={n_exp} locate_buttons={n_loc}")

    # viewer iframe
    vf = None
    for _ in range(60):
        el = pg.query_selector('iframe[src*="8765/viewer"]')
        if el:
            cf = el.content_frame()
            if cf:
                vf = cf; break
        time.sleep(1)
    if not vf:
        L("!! viewer iframe not found")
        pg.screenshot(path=str(SHOTS / "FAIL_noiframe.png"))
        br.close(); sys.exit(1)
    L(f"viewer frame: {vf.url[:90]}")

    ok = False
    for _ in range(120):
        try:
            st = vf.evaluate("() => { const n=document.getElementById('nav-bar');"
                             " return n ? n.style.display : null; }")
        except Exception:
            st = None
        if st == "flex":
            ok = True; break
        time.sleep(2)
    if not ok:
        L("!! nav-bar never shown (HITOS)")
        pg.screenshot(path=str(SHOTS / "FAIL_navbar.png"))
        br.close(); sys.exit(1)
    time.sleep(2)
    floors = vf.eval_on_selector("#nav-floor", "el=>[...el.options].map(o=>o.textContent)")
    L(f"floors({len(floors)}): {floors[:8]}")
    pg.screenshot(path=str(SHOTS / "02_viewer_full.png"))

    vf.select_option("#nav-floor", index=1)
    time.sleep(3)
    rooms = vf.eval_on_selector("#nav-room", "el=>[...el.options].map(o=>o.textContent)")
    L(f"rooms on floor1({len(rooms)}): {rooms[:6]}")
    if len(rooms) > 1:
        vf.select_option("#nav-room", index=1)
        time.sleep(0.4)
        vf.click("#nav-enter")
        time.sleep(3)
        pg.screenshot(path=str(SHOTS / "03_inside_room.png"))
        nav = [l for l in logs if "[nav]" in l]
        L(f"nav logs: {nav[-3:]}")

    errs = [l for l in logs if "pageerror" in l]
    L(f"pageerrors: {errs[:4] if errs else 'none'}")
    br.close()
L("DONE")
