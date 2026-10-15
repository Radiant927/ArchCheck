import sys, time, json
from playwright.sync_api import sync_playwright
sys.stdout.reconfigure(encoding="utf-8")
B="http://127.0.0.1:8765"
URL=f"{B}/viewer/?ifc={B}/ifc/default/FZK_Haus.ifc&session=default&lang=zh"
POS="()=>{const c=window.__viewer.context.getCamera().position;return [ +c.x.toFixed(2), +c.y.toFixed(2), +c.z.toFixed(2)];}"
with sync_playwright() as p:
    br=p.chromium.launch(channel="chrome",headless=True)
    pg=br.new_page()
    pg.goto(URL,wait_until="domcontentloaded")
    pg.wait_for_function("()=>document.getElementById('nav-bar')&&document.getElementById('nav-bar').style.display==='flex'",timeout=120000)
    time.sleep(1)
    print("start          ", pg.evaluate(POS))
    pg.select_option("#nav-floor", index=1); time.sleep(2)
    print("after floor    ", pg.evaluate(POS))
    pg.select_option("#nav-room", index=1); time.sleep(0.3)
    pg.click("#nav-enter"); time.sleep(0.5)
    print("enter +0.5s    ", pg.evaluate(POS))
    time.sleep(2.5)
    print("enter +3s      ", pg.evaluate(POS))
    br.close()
