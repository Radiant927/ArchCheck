# -*- coding: utf-8 -*-
"""FZK「定位到 3D」逐条诊断：点每个定位按钮，抓 viewer 控制台日志。"""
import sys, time, re, pathlib
from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding="utf-8")
BASE = "http://localhost:8502"
IFC = r"C:\Users\32800\Desktop\NTU pre\ArchCheck\bim\samples\FZK_Haus.ifc"
SHOTS = pathlib.Path(__file__).parent / "_locate_diag"
SHOTS.mkdir(parents=True, exist_ok=True)

logs = []
with sync_playwright() as p:
    browser = p.chromium.launch(channel="chrome", headless=True)
    page = browser.new_page(viewport={"width": 1600, "height": 1000})
    page.on("console", lambda m: logs.append(f"[{m.type}] {m.text}"))

    page.goto(BASE, wait_until="networkidle")
    time.sleep(2)
    page.set_input_files('input[type="file"]', IFC)
    print("uploaded, parsing...")
    page.wait_for_function(
        "() => document.body.innerText.includes('开始审查')", timeout=120000)
    time.sleep(2)
    page.get_by_role("button", name="开始审查").first.click()
    print("review running...")
    page.wait_for_function(
        "() => document.body.innerText.includes('审查问题')", timeout=180000)
    time.sleep(4)

    # 展开所有问题卡片
    headers = page.locator('div[data-testid="stExpander"] summary')
    n_exp = headers.count()
    print("expanders:", n_exp)
    for i in range(n_exp):
        try:
            h = page.locator('div[data-testid="stExpander"] summary').nth(i)
            if h.get_attribute("aria-expanded") != "true":
                h.click()
                time.sleep(0.4)
        except Exception:
            pass
    time.sleep(1)
    page.screenshot(path=str(SHOTS / "01_cards.png"))

    btns = page.get_by_role("button", name=re.compile("定位到 3D"))
    n_btn = btns.count()
    print("locate buttons:", n_btn)

    for i in range(n_btn):
        logs.clear()
        try:
            # Streamlit rerun 后按钮重建，每次重新取
            b = page.get_by_role("button", name=re.compile("定位到 3D")).nth(i)
            label = b.evaluate("el => el.closest('[data-testid=\"stExpander\"]')?.innerText?.slice(0,60) || '?'")
            b.click()
            time.sleep(2.2)
            hl = [l for l in logs if "highlight" in l or "viewer" in l]
            print(f"\n--- button {i}: {label!r}")
            for l in hl[-6:]:
                print("   ", l[:160])
        except Exception as e:
            print(f"--- button {i}: CLICK ERROR {e}")

    browser.close()
print("\nDONE")
