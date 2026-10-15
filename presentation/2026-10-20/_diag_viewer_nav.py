# -*- coding: utf-8 -*-
"""3D viewer 楼层/房间导航 + 进入室内 浏览器验证（直连 viewer，绕过 streamlit）。

用法：python _diag_viewer_nav.py [ifc文件basename]
"""
import sys, time, pathlib
from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding="utf-8")
BASE = "http://127.0.0.1:8765"
IFC_NAME = sys.argv[1] if len(sys.argv) > 1 else "FZK_Haus.ifc"
URL = f"{BASE}/viewer/?ifc={BASE}/ifc/default/{IFC_NAME}&session=default&lang=zh"
SHOTS = pathlib.Path(__file__).parent / "_nav_diag"
SHOTS.mkdir(parents=True, exist_ok=True)

logs = []
with sync_playwright() as p:
    browser = p.chromium.launch(channel="chrome", headless=True)
    page = browser.new_page(viewport={"width": 1500, "height": 950})
    page.on("console", lambda m: logs.append(f"[{m.type}] {m.text}"))
    page.on("pageerror", lambda e: logs.append(f"[pageerror] {e}"))

    print("open", URL)
    page.goto(URL, wait_until="domcontentloaded")
    try:
        page.wait_for_function(
            "() => window.__viewer && document.getElementById('nav-bar')"
            " && document.getElementById('nav-bar').style.display === 'flex'",
            timeout=120000)
    except Exception as e:
        print("!! nav bar not shown:", e)
        page.screenshot(path=str(SHOTS / "FAIL_navbar.png"))
        for l in logs[-30:]:
            print("   ", l[:180])
        browser.close(); sys.exit(1)

    time.sleep(2)
    page.screenshot(path=str(SHOTS / "01_loaded_full.png"))

    # 楼层/房间下拉内容
    floors = page.eval_on_selector("#nav-floor", "el => [...el.options].map(o=>o.textContent)")
    print("floors:", floors)

    # 选第一层
    page.select_option("#nav-floor", index=1)
    time.sleep(3)
    rooms = page.eval_on_selector("#nav-room", "el => [...el.options].map(o=>o.textContent)")
    print("rooms(first floor):", rooms[:25])
    page.screenshot(path=str(SHOTS / "02_floor_selected.png"))

    # 选第一个房间 → 进入
    if len(rooms) > 1:
        page.select_option("#nav-room", index=1)
        time.sleep(0.3)
        page.click("#nav-enter")
        time.sleep(3)
        page.screenshot(path=str(SHOTS / "03_inside_room.png"))
        camlog = [l for l in logs if "[nav]" in l]
        print("nav logs:", camlog[-6:])
    else:
        print("!! no rooms on first floor")

    # 回到全景
    page.click("#nav-home")
    time.sleep(2)
    page.screenshot(path=str(SHOTS / "04_back_full.png"))

    errs = [l for l in logs if "pageerror" in l or "[error]" in l]
    print("errors:", errs[-8:] if errs else "none")
    browser.close()
print("DONE ->", SHOTS)
