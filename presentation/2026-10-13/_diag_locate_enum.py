# -*- coding: utf-8 -*-
"""枚举 FZK 结果页所有「定位」按钮：名称/所属卡片/禁用 + 顶部截图。"""
import sys, time, re, pathlib
from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding="utf-8")
BASE = "http://localhost:8502"
IFC = r"C:\Users\32800\Desktop\NTU pre\ArchCheck\bim\samples\FZK_Haus.ifc"
SHOTS = pathlib.Path(__file__).parent / "_locate_diag"

with sync_playwright() as p:
    browser = p.chromium.launch(channel="chrome", headless=True)
    page = browser.new_page(viewport={"width": 1600, "height": 1000})
    page.goto(BASE, wait_until="networkidle")
    time.sleep(2)
    page.set_input_files('input[type="file"]', IFC)
    page.wait_for_function("() => document.body.innerText.includes('开始审查')", timeout=120000)
    time.sleep(2)
    page.get_by_role("button", name="开始审查").first.click()
    page.wait_for_function("() => document.body.innerText.includes('审查问题')", timeout=180000)
    time.sleep(4)

    # 展开所有折叠区
    for _ in range(3):
        hs = page.locator('div[data-testid="stExpander"] summary[aria-expanded="false"]')
        if hs.count() == 0:
            break
        for i in range(hs.count()):
            try:
                page.locator('div[data-testid="stExpander"] summary[aria-expanded="false"]').nth(0).click()
                time.sleep(0.3)
            except Exception:
                break
        time.sleep(0.5)
    time.sleep(1)
    page.keyboard.press("Home")
    time.sleep(1)
    page.screenshot(path=str(SHOTS / "02_top.png"))

    btns = page.get_by_role("button", name=re.compile("定位"))
    print("ALL locate-ish buttons:", btns.count())
    for i in range(btns.count()):
        b = btns.nth(i)
        info = b.evaluate("""el => ({
            text: el.innerText,
            disabled: el.disabled,
            card: el.closest('[data-testid=\"stExpander\"]')?.querySelector('summary')?.innerText?.slice(0,50) || '(outside)',
            visible: !!(el.offsetWidth || el.offsetHeight)
        })""")
        print(f"[{i}] vis={info['visible']} dis={info['disabled']} card={info['card']!r} text={info['text']!r}")
    browser.close()
print("DONE")
