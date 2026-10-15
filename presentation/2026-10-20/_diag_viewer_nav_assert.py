# -*- coding: utf-8 -*-
"""进入房间后的状态断言：相机位置是否落在房间 bbox 内、基础模型是否隐藏、
隔离子集是否建立、房间线框是否加入场景。"""
import sys, time, json
from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding="utf-8")
BASE = "http://127.0.0.1:8765"
IFC_NAME = sys.argv[1] if len(sys.argv) > 1 else "FZK_Haus.ifc"
URL = f"{BASE}/viewer/?ifc={BASE}/ifc/default/{IFC_NAME}&session=default&lang=zh"

PROBE = """
() => {
  const v = window.__viewer;
  const cam = v.context.getCamera();
  const models = v.context.items.ifcModels.map(m => m.visible);
  let subset = null, outline = false;
  try { subset = !!v.IFC.loader.ifcManager.getSubset(0, undefined, 'floor-isolate'); } catch(e){}
  v.context.getScene().traverse(o => { if (o.name === 'room-outline') outline = true; });
  return { cam: [cam.position.x, cam.position.y, cam.position.z],
           modelsVisible: models, subset, outline };
}
"""

with sync_playwright() as p:
    browser = p.chromium.launch(channel="chrome", headless=True)
    page = browser.new_page(viewport={"width": 1400, "height": 900})
    logs = []
    page.on("console", lambda m: logs.append(m.text))
    page.goto(URL, wait_until="domcontentloaded")
    page.wait_for_function(
        "() => document.getElementById('nav-bar')"
        " && document.getElementById('nav-bar').style.display === 'flex'", timeout=120000)
    time.sleep(1)
    print("BEFORE:", json.dumps(page.evaluate(PROBE), ensure_ascii=False))

    page.select_option("#nav-floor", index=1)
    time.sleep(3)
    page.select_option("#nav-room", index=1)
    time.sleep(0.3)
    page.click("#nav-enter")
    time.sleep(3)
    print("AFTER :", json.dumps(page.evaluate(PROBE), ensure_ascii=False))
    print("nav logs:", [l for l in logs if "[nav]" in l][-5:])

    page.click("#nav-home")
    time.sleep(2)
    print("HOME  :", json.dumps(page.evaluate(PROBE), ensure_ascii=False))
    browser.close()
