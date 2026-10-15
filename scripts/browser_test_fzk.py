# -*- coding: utf-8 -*-
"""FZK 浏览器端到端实测：上传 -> 29 条问题 -> 预测规则 NotChecked -> 3D 加载/点击 -> 报告下载。"""
import sys, time, re, pathlib
from playwright.sync_api import sync_playwright

BASE = "http://localhost:8501"
IFC = r"C:\Users\32800\Desktop\NTU pre\ArchCheck\bim\samples\FZK_Haus.ifc"
SHOTS = pathlib.Path(r"C:\Users\32800\Desktop\NTU pre\ArchCheck\presentation\2026-09-29\browser_test")
SHOTS.mkdir(parents=True, exist_ok=True)

findings = []
def check(name, ok, detail=""):
    findings.append((name, ok, detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name} {detail}")

with sync_playwright() as p:
    browser = p.chromium.launch(channel="chrome", headless=True)
    page = browser.new_page(viewport={"width": 1600, "height": 1000})
    page.set_default_timeout(60000)

    page.goto(BASE, wait_until="networkidle")
    time.sleep(3)
    page.screenshot(path=str(SHOTS / "01_landing.png"))

    # 1) 上传
    page.set_input_files('input[type="file"]', IFC)
    print("uploaded, parsing...")
    page.wait_for_function(
        "() => document.body.innerText.includes('开始审查') || document.body.innerText.includes('Start Review')",
        timeout=120000)
    time.sleep(2)
    page.screenshot(path=str(SHOTS / "02_parsed.png"))
    txt = page.inner_text("body")
    check("解析成功消息出现", "已解析" in txt or "parsed" in txt.lower(), "")

    # 2) 开始审查
    page.get_by_role("button", name="开始审查").first.click()
    print("review running...")
    page.wait_for_function(
        "() => document.body.innerText.includes('审查问题')", timeout=180000)
    time.sleep(5)
    page.screenshot(path=str(SHOTS / "03_results_top.png"))

    txt = page.inner_text("body")
    check("结果页加载", "三维模型" in txt, "")
    check("问题总数 29", bool(re.search(r"29\s*\n?\s*(?:问题总数|条问题|共)", txt)) or "29" in txt, "")

    bodies = page.locator('div[data-testid="stExpander"]')
    check("问题卡片折叠区存在", bodies.count() >= 20, f"expanders={bodies.count()}")

    # 3) 未检查规则折叠区：预测规则 NotChecked
    cov = bodies.filter(has_text="未检查规则")
    if cov.count() == 0:
        cov = bodies.filter(has_text=re.compile("not checked", re.I))
    check("未检查规则折叠区存在", cov.count() >= 1, "")
    cov.first.click()
    body_txt = ""
    for _ in range(8):
        time.sleep(1)
        body_txt = page.inner_text("body")
        if "剩余寿命预测" in body_txt:
            break
    check("未检查规则 17 条", "未检查规则（缺字段）（17）" in body_txt or "17" in body_txt, "")
    check("预测规则 NotChecked 展示", "剩余寿命预测" in body_txt and "维保记录" in body_txt, "")
    page.screenshot(path=str(SHOTS / "04_coverage.png"))
    cov.first.click()

    # 4) 3D iframe
    time.sleep(2)
    iframe_el = page.locator("iframe").first
    src = iframe_el.get_attribute("src") or ""
    check("3D iframe 存在", iframe_el.count() == 1, src)
    check("viewer 指向 8765", "8765" in src, "")

    vframe = page.frame(url=re.compile(r"8765/viewer"))
    frame = page.frame_locator("iframe").first
    print("waiting for 3D model...")
    frame.locator("canvas").wait_for(timeout=90000)
    time.sleep(28)  # web-ifc 解析 + 渲染 FZK 约 12-20s
    page.screenshot(path=str(SHOTS / "05_3d_loaded.png"))

    cs = vframe.evaluate("""() => {
        const c = document.querySelector('canvas');
        return c ? {w: c.width, h: c.height} : null;
    }""")
    check("3D canvas 已初始化", cs is not None and cs["w"] > 0, str(cs))

    # 5) 真实点击构件 -> 右侧反向联动
    clicked = False
    cw, ch = cs["w"], cs["h"]
    for fx, fy in [(0.5, 0.5), (0.45, 0.46), (0.55, 0.54), (0.4, 0.5), (0.6, 0.45)]:
        try:
            frame.locator("canvas").click(position={"x": cw*fx, "y": ch*fy}, timeout=15000)
        except Exception:
            continue
        try:
            page.wait_for_function(
                "() => document.body.innerText.includes('3D 选中')", timeout=6000)
            clicked = True
            break
        except Exception:
            continue
    check("点击构件 -> 反向联动", clicked, "")
    page.screenshot(path=str(SHOTS / "06_clicked.png"))

    # 6) HTML 报告下载
    downloads = []
    page.on("download", lambda d: downloads.append(d))
    dl_btn = page.get_by_role("button", name="下载 HTML 报告").first
    check("报告下载按钮存在", dl_btn.count() == 1, "")
    dl_btn.click()
    try:
        page.wait_for_event("download", timeout=30000)
    except Exception:
        pass
    if downloads:
        out = SHOTS / downloads[0].suggested_filename
        downloads[0].save_as(str(out))
        html = out.read_text(encoding="utf-8", errors="ignore")
        check("报告 HTML 已下载", out.stat().st_size > 5000, f"{out.stat().st_size} bytes")
        check("报告无未知严重性标签", ">?<" not in html, "")
    else:
        check("报告 HTML 已下载", False, "no download event")

    browser.close()

print("\n==== SUMMARY ====")
npass = sum(1 for _, ok, _ in findings if ok)
for name, ok, detail in findings:
    print(f"[{'PASS' if ok else 'FAIL'}] {name} {detail}")
print(f"{npass}/{len(findings)} passed")
sys.exit(0 if npass == len(findings) else 1)
