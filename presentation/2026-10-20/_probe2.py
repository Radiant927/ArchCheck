import sys, time, json
from playwright.sync_api import sync_playwright
sys.stdout.reconfigure(encoding="utf-8")
B="http://127.0.0.1:8765"
URL=f"{B}/viewer/?ifc={B}/ifc/default/FZK_Haus.ifc&session=default&lang=zh"
DUMP="""()=>{const c=window.__viewer.context.ifcCamera.cameraControls;
 const cam=window.__viewer.context.getCamera();
 const f=v=>[+v.x.toFixed(2),+v.y.toFixed(2),+v.z.toFixed(2)];
 return {pos:f(cam.position),
   tgtEnd:f(c._targetEnd), tgtNow:f(c._target),
   rEnd:+c._sphericalEnd.radius.toFixed(2), rNow:+c._spherical.radius.toFixed(2)};}"""
with sync_playwright() as p:
    br=p.chromium.launch(channel="chrome",headless=True)
    pg=br.new_page()
    pg.goto(URL,wait_until="domcontentloaded")
    pg.wait_for_function("()=>document.getElementById('nav-bar')&&document.getElementById('nav-bar').style.display==='flex'",timeout=120000)
    time.sleep(1)
    pg.select_option("#nav-floor", index=1); time.sleep(2)
    print("floor ", json.dumps(pg.evaluate(DUMP)))
    pg.select_option("#nav-room", index=1); time.sleep(0.3)
    pg.click("#nav-enter"); time.sleep(0.4)
    print("+0.4s ", json.dumps(pg.evaluate(DUMP)))
    time.sleep(2.6)
    print("+3s   ", json.dumps(pg.evaluate(DUMP)))
    br.close()
