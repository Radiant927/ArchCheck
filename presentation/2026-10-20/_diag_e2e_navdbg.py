# -*- coding: utf-8 -*-
"""E2E debug: after review, dump viewer frame console + nav-bar state over time."""
import sys, time, pathlib
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
    pg.on("console", lambda m: logs.append(f"[PAGE][{m.type}] {m.text}"))
    pg.on("pageerror", lambda e: logs.append(f"[PAGE][pageerror] {e}"))

    pg.goto(BASE, wait_until="networkidle")
    time.sleep(3)
    pg.set_input_files('input[type="file"]', IFC)
    pg.wait_for_function(
        "() => document.body.innerText.includes('开始审查')", timeout=180000)
    time.sleep(2)
    pg.get_by_role("button", name="开始审查").first.click()
    pg.wait_for_function(
        "() => document.body.innerText.includes('审查问题')", timeout=180000)
    time.sleep(6)

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
        print("!! no viewer frame")
        br.close(); sys.exit(1)
    print("viewer frame:", vf.url)

    vf.on("console", lambda m: logs.append(f"[VIEW][{m.type}] {m.text}"))
    vf.on("pageerror", lambda e: logs.append(f"[VIEW][pageerror] {e}"))

    # poll nav-bar state for 60s
    for i in range(30):
        st = vf.evaluate(
            "() => { const n=document.getElementById('nav-bar');"
            " const v=window.__viewer;"
            " return {exists: !!n, disp: n?n.style.display:null,"
            "  viewer: !!v, models: v? v.context.items.ifcModels.length : -1,"
            "  ready: !!(window.__viewer && window.__viewer.context"
            "    && window.__viewer.context.items.ifcModels.length)}; }")
        print(i, st)
        if st.get("disp") == "flex":
            break
        time.sleep(2)

    pg.screenshot(path=str(SHOTS / "dbg_full.png"))
    print("---- logs (last 40) ----")
    for l in logs[-40:]:
        print("   ", l[:200])
    br.close()
print("DONE")
