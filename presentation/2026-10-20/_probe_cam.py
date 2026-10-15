import sys, time, json
from playwright.sync_api import sync_playwright
sys.stdout.reconfigure(encoding="utf-8")
B="http://127.0.0.1:8765"
URL=f"{B}/viewer/?ifc={B}/ifc/default/FZK_Haus.ifc&session=default&lang=zh"
with sync_playwright() as p:
    br=p.chromium.launch(channel="chrome",headless=True)
    pg=br.new_page()
    pg.goto(URL,wait_until="domcontentloaded")
    pg.wait_for_function("()=>document.getElementById('nav-bar')&&document.getElementById('nav-bar').style.display==='flex'",timeout=120000)
    time.sleep(1)
    r=pg.evaluate("""() => {
      const v=window.__viewer, cam=v.context.getCamera();
      const c=v.context.ifcCamera.cameraControls;
      const out={hasSetLookAt: !!(c&&c.setLookAt), hasSetPos: !!(c&&c.setPosition),
                 minD:c&&c.minDistance, maxD:c&&c.maxDistance,
                 before:[cam.position.x,cam.position.y,cam.position.z]};
      c.setLookAt(-2.65,0.60,-5.00, 1.0,0.60,-5.00, false);
      out.afterImmediate=[cam.position.x,cam.position.y,cam.position.z];
      out.sph=c._sphericalEnd? {r:c._sphericalEnd.radius,theta:c._sphericalEnd.theta,phi:c._sphericalEnd.phi}:null;
      return out;
    }""")
    print(json.dumps(r,ensure_ascii=False))
    time.sleep(2)
    r2=pg.evaluate("()=>{const c=window.__viewer.context.getCamera().position;return [c.x,c.y,c.z];}")
    print("after 2s:", r2)
    br.close()
