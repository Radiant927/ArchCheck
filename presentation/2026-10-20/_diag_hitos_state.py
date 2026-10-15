# -*- coding: utf-8 -*-
"""Debug: upload HITOS, poll page text for 150s to see what state it reaches."""
import sys, time, pathlib
from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding="utf-8")
BASE = "http://localhost:" + (sys.argv[1] if len(sys.argv) > 1 else "8503")
IFC = r"C:\Users\32800\Desktop\NTU pre\ArchCheck\bim\test-suites\real-project\HITOS-Large-Building_IFC2x3.ifc"
SHOTS = pathlib.Path(__file__).parent / "_hitos_e2e"
SHOTS.mkdir(parents=True, exist_ok=True)

with sync_playwright() as p:
    br = p.chromium.launch(channel="chrome", headless=True)
    pg = br.new_page(viewport={"width": 1600, "height": 1000})
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(BASE, wait_until="networkidle")
    time.sleep(2)
    pg.set_input_files('input[type="file"]', IFC)
    print("uploaded; polling…", flush=True)
    for i in range(10):
        time.sleep(15)
        try:
            txt = pg.evaluate("() => document.body.innerText.replace(/\\n+/g,' | ').slice(0,300)")
        except Exception as e:
            txt = f"<eval err {e}>"
        print(f"[t={15*(i+1)}s] {txt}", flush=True)
        if "开始审查" in txt or "审查问题" in txt:
            print(">>> reached review state", flush=True)
            break
    pg.screenshot(path=str(SHOTS / "dbg_state.png"))
    print("pageerrors:", errs[:5] if errs else "none")
    br.close()
print("DONE")
