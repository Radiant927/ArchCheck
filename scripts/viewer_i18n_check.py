# -*- coding: utf-8 -*-
"""验证部署后的 3D viewer：英文悬停显示 Size，中文显示 尺寸。"""
import sys, pathlib
from playwright.sync_api import sync_playwright

BASE = "http://localhost:8765/viewer/?ifc=default.ifc&lang="
SHOTS = pathlib.Path(r"C:\Users\32800\Desktop\NTU pre\ArchCheck\presentation\2026-10-05\i18n_check")
SHOTS.mkdir(parents=True, exist_ok=True)

findings = []
def check(name, ok, detail=""):
    findings.append((name, ok, detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name} {detail}")

def run_lang(p, lang, want, avoid):
    browser = p.chromium.launch(channel="chrome", headless=True)
    page = browser.new_page(viewport={"width": 1280, "height": 860})
    page.set_default_timeout(90000)
    page.goto(BASE + lang, wait_until="domcontentloaded")
    page.locator("canvas").first.wait_for()
    page.wait_for_function(
        "() => /loaded|加载完成/.test(document.getElementById('status').textContent)",
        timeout=90000)
    page.wait_for_timeout(3000)

    tip = ""
    for fx, fy in [(0.5,0.5),(0.45,0.46),(0.55,0.54),(0.4,0.5),(0.6,0.45),(0.5,0.6),(0.35,0.5)]:
        page.mouse.move(1280*fx, 860*fy)
        page.wait_for_timeout(120)
        t = page.locator("#hover-tip")
        if t.is_visible():
            tip = t.inner_text()
            if want in tip:
                break
    page.screenshot(path=str(SHOTS / f"hover_{lang}.png"))
    check(f"[{lang}] 悬停浮层出现", bool(tip), repr(tip[:60]))
    check(f"[{lang}] 含 '{want}'", want in tip, repr(tip[:80]))
    check(f"[{lang}] 不含 '{avoid}'", avoid not in tip, "")
    browser.close()

with sync_playwright() as p:
    run_lang(p, "en", "Size", "尺寸")
    run_lang(p, "zh", "尺寸", "Size")

npass = sum(1 for _, ok, _ in findings if ok)
print(f"\n{npass}/{len(findings)} passed")
sys.exit(0 if npass == len(findings) else 1)
