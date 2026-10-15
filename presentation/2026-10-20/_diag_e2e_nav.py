# -*- coding: utf-8 -*-
"""Streamlit 端到端：上传 FZK → 审查 → viewer iframe 内测楼层/房间导航。"""
import sys, time, re, pathlib
from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding="utf-8")
BASE = "http://localhost:8502"
IFC = r"C:\Users\32800\Desktop\NTU pre\ArchCheck\bim\samples\FZK_Haus.ifc"
SHOTS = pathlib.Path(__file__).parent / "_nav_e2e"
SHOTS.mkdir(parents=True, exist_ok=True)

with sync_playwright() as p:
    br = p.chromium.launch(channel="chrome", headless=True)
    pg = br.new_page(viewport={"width": 1700, "height": 1100})
    logs = []
    pg.on("console", lambda m: logs.append(f"[{m.type}] {m.text}"))
    pg.on("pageerror", lambda e: logs.append(f"[pageerror] {e}"))

    pg.goto(BASE, wait_until="networkidle")
    time.sleep(3)
    pg.set_input_files('input[type="file"]', IFC)
    print("uploaded, waiting for parse…")
    pg.wait_for_function(
        "() => document.body.innerText.includes('开始审查')", timeout=180000)
    time.sleep(2)
    pg.get_by_role("button", name="开始审查").first.click()
    print("reviewing…")
    pg.wait_for_function(
        "() => document.body.innerText.includes('审查问题')", timeout=180000)
    time.sleep(6)

    # 找到 viewer iframe（8765）——用元素 content_frame 拿跨源 frame
    vf = None
    for _ in range(40):
        el = pg.query_selector('iframe[src*="8765/viewer"]')
        if el:
            cf = el.content_frame()
            if cf:
                vf = cf
                break
        time.sleep(1)
    if not vf:
        print("!! viewer iframe not found; iframes:",
              pg.eval_on_selector_all("iframe", "els=>els.map(e=>e.src)"))
        pg.screenshot(path=str(SHOTS / "FAIL_noiframe.png"))
        br.close(); sys.exit(1)
    print("viewer frame:", vf.url[:90])

    # wait_for_function is unreliable on cross-origin frames -> poll via evaluate
    ok = False
    for _ in range(90):
        try:
            st = vf.evaluate(
                "() => { const n=document.getElementById('nav-bar');"
                " return n ? n.style.display : null; }")
        except Exception:
            st = None
        if st == "flex":
            ok = True
            break
        time.sleep(2)
    if not ok:
        print("!! nav-bar never shown")
        pg.screenshot(path=str(SHOTS / "FAIL_navbar.png"))
        br.close(); sys.exit(1)
    time.sleep(2)
    # /api/rooms 是否被成功读取（有面积标注说明 manifest 生效）
    floors = vf.eval_on_selector("#nav-floor", "el=>[...el.options].map(o=>o.textContent)")
    print("floors:", floors)
    pg.screenshot(path=str(SHOTS / "01_e2e_full.png"))

    vf.select_option("#nav-floor", index=1)
    time.sleep(3)
    rooms = vf.eval_on_selector("#nav-room", "el=>[...el.options].map(o=>o.textContent)")
    print("rooms:", rooms[:10])
    if len(rooms) > 1:
        vf.select_option("#nav-room", index=1)
        time.sleep(0.3)
        vf.click("#nav-enter")
        time.sleep(3)
        pg.screenshot(path=str(SHOTS / "02_e2e_inside.png"))
        nav = [l for l in logs if "[nav]" in l or "moveCameraTo" in l]
        print("nav logs:", nav[-4:])

    errs = [l for l in logs if "pageerror" in l]
    print("pageerrors:", errs[:5] if errs else "none")
    br.close()
print("DONE")
