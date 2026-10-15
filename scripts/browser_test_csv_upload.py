# -*- coding: utf-8 -*-
"""端到端：维保/监测 CSV 上传入口（真实 IFC 上传，无任何预载注入）。

阶段 1（正向闭环）：真实上传 Duplex IFC -> 服务端解析 -> 上传三份与真实
管道 gid 对齐的 CSV -> 解析摘要 ID 全匹配 -> 开始审查 -> 结果页出现
排序清单 + 「在线传感器」体制标注；HTML 报告含标注。

阶段 2（诚实反馈）：FZK 真实上传 + gid 不匹配的 CSV -> 未匹配被报告；
移除按钮生效；审查后预测规则仍 NotChecked。

上传交互：Streamlit 1.59 的 file_uploader 位于
  section[data-testid="stFileUploaderDropzone"] 内的
  input[data-testid="stFileUploaderDropzoneInput"]。
对它 set_input_files 后，服务端往返约 10–20s 才回显摘要，故等待期放宽。

注：Duplex 服务端解析约 4 分钟，全程约 8–12 分钟，建议后台运行。
"""
import os
import re
import sys
import time
import pathlib

from playwright.sync_api import sync_playwright

REPO = pathlib.Path(r"C:\Users\32800\Desktop\NTU pre\ArchCheck")
BASE = os.environ.get("ARCHCHECK_BASE", "http://localhost:8501")
DUPLEX = str(REPO / "bim" / "samples" / "Duplex_MEP_20110907.ifc")
FZK = str(REPO / "bim" / "samples" / "FZK_Haus.ifc")
CSV_DIR = REPO / "output" / "demo_csv"
SHOTS = REPO / "presentation" / "2026-10-05" / "csv_upload"
SHOTS.mkdir(parents=True, exist_ok=True)

SUMMARY_RE = re.compile(r"有效\s*\d+\s*行")

findings = []


def check(name, ok, detail=""):
    findings.append((name, ok, detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name} {detail}")


def _maint_open(page):
    """True 当 maint 展开区处于打开状态：折叠时其子节点 inner_text 为空。"""
    sec = page.get_by_test_id("stFileUploaderDropzone")
    if sec.count() < 4:
        return False
    try:
        return bool(sec.nth(1).inner_text().strip())
    except Exception:
        return False


def ensure_maint_open(page):
    exp = page.locator('div[data-testid="stExpander"]').filter(
        has_text="维保与监测数据")
    if exp.count() == 0:
        exp = page.locator('div[data-testid="stExpander"]').filter(
            has_text=re.compile("maintenance", re.I))
    for _ in range(4):
        if _maint_open(page):
            return True
        if exp.count() == 0:
            return False
        exp.first.click()
        page.wait_for_timeout(1200)
    return _maint_open(page)


def n_summaries(page):
    return len(SUMMARY_RE.findall(page.inner_text("body")))


def upload_csv(page, idx, path, target_n, timeout_s=300):
    """idx: 1=service, 2=log, 3=monitoring（0 为 IFC uploader）。

    Duplex 等服务端解析耗时的模型，上传后需要较长时间（可 >2 min）才回显摘要；
    每次 rerun 还会把展开区收起，故轮询期间持续确保其打开，否则读到空文本。
    """
    ensure_maint_open(page)
    sec = page.get_by_test_id("stFileUploaderDropzone")
    sec.nth(idx).locator('input[type="file"]').set_input_files(str(path))
    for _ in range(max(1, timeout_s // 4)):
        page.wait_for_timeout(4000)
        if not _maint_open(page):
            ensure_maint_open(page)
        if n_summaries(page) >= target_n:
            return True
    return False


with sync_playwright() as p:
    browser = p.chromium.launch(channel="chrome", headless=True)
    page = browser.new_page(viewport={"width": 1600, "height": 1100})
    page.set_default_timeout(90000)

    # ================= 阶段 1：Duplex 正向闭环（真实上传） =================
    print("=== phase 1: Duplex positive loop (real upload) ===")
    page.goto(BASE, wait_until="domcontentloaded")
    page.wait_for_timeout(3000)
    page.set_input_files('input[type="file"]', DUPLEX)
    print("Duplex uploading, server parsing (~4 min)...")
    page.wait_for_function(
        "() => document.body.innerText.includes('开始审查')", timeout=420000)
    page.wait_for_timeout(2000)
    check("Duplex 解析完成、出现开始审查", True)

    ok1 = upload_csv(page, 1, CSV_DIR / "pipe_service.csv", 1)
    check("服务台账上传并回显摘要", ok1)
    ok2 = upload_csv(page, 2, CSV_DIR / "maintenance_log.csv", 2)
    check("维保日志上传并回显摘要", ok2)
    ok3 = upload_csv(page, 3, CSV_DIR / "pipe_monitoring.csv", 3)
    check("监测读数上传并回显摘要", ok3)
    ensure_maint_open(page)
    page.screenshot(path=str(SHOTS / "01_csv_summaries.png"))
    txt = page.inner_text("body")

    check("台账摘要：全 425 匹配",
          bool(re.search(r"有效\s*425\s*行\s*·\s*ID\s*匹配\s*425", txt)), "")
    check("三份摘要均在页", n_summaries(page) >= 3, f"n={n_summaries(page)}")

    page.get_by_role("button", name="开始审查").first.click()
    print("running review...")
    page.wait_for_function(
        "() => document.body.innerText.includes('审查问题')", timeout=300000)
    page.wait_for_function(
        "() => document.body.innerText.includes('风险排序检修清单')",
        timeout=300000)
    page.wait_for_function(
        "() => document.body.innerText.includes('在线传感器')", timeout=60000)
    txt = page.inner_text("body")
    check("结果页排序清单出现", "风险排序检修清单" in txt, "")
    check("体制标注：在线传感器", "监测体制：在线传感器" in txt, "")
    page.screenshot(path=str(SHOTS / "02_positive_results.png"))

    downloads = []
    page.on("download", lambda d: downloads.append(d))
    page.get_by_role("button", name="下载 HTML 报告").first.click()
    try:
        page.wait_for_event("download", timeout=30000)
    except Exception:
        pass
    if downloads:
        out = SHOTS / "report_csv_upload.html"
        downloads[0].save_as(str(out))
        html = out.read_text(encoding="utf-8", errors="ignore")
        check("报告含排序清单", "风险排序检修清单" in html, "")
        check("报告含在线传感器标注", "监测体制：在线传感器" in html, "")
    else:
        check("报告下载", False, "no download")

    # ================= 阶段 2：FZK 不匹配 / 弃权 =================
    print("\n=== phase 2: FZK mismatch + abstention ===")
    page.goto(BASE, wait_until="domcontentloaded")
    page.wait_for_timeout(3000)
    page.set_input_files('input[type="file"]', FZK)
    page.wait_for_function(
        "() => document.body.innerText.includes('开始审查')", timeout=180000)
    page.wait_for_timeout(2000)
    # Duplex gids do not exist in FZK -> every service row is unmatched
    ok = upload_csv(page, 1, CSV_DIR / "pipe_service.csv", 1)
    check("FZK 上传 CSV 并回显摘要", ok)
    txt = page.inner_text("body")
    check("未匹配被诚实报告",
          bool(re.search(r"未匹配\s*425", txt)),
          txt[txt.find("有效"):txt.find("有效") + 80] if "有效" in txt else "")
    page.screenshot(path=str(SHOTS / "03_unmatched.png"))

    ensure_maint_open(page)
    rm = page.get_by_role("button", name=re.compile("移除"))
    check("上传当次即出现移除按钮", rm.count() >= 1, f"count={rm.count()}")
    if rm.count() >= 1:
        rm.first.click()
        gone = False
        for _ in range(20):
            page.wait_for_timeout(3000)
            if not _maint_open(page):
                ensure_maint_open(page)
            txt = page.inner_text("body")
            if not re.search(r"未匹配\s*425", txt) and "尚未上传" in txt:
                gone = True
                break
        check("移除后回到尚未上传", gone, f"尚未上传={txt.count('尚未上传')}")
    else:
        check("移除后回到尚未上传", False, "no remove button")

    page.get_by_role("button", name="开始审查").first.click()
    page.wait_for_function(
        "() => document.body.innerText.includes('审查问题')", timeout=180000)
    page.wait_for_timeout(4000)
    exp = page.locator('div[data-testid="stExpander"]').filter(
        has_text="未检查规则")
    exp.first.click()
    page.wait_for_timeout(2000)
    txt = page.inner_text("body")
    check("FZK 预测规则仍 NotChecked", "剩余寿命预测" in txt, "")
    page.screenshot(path=str(SHOTS / "04_fzk_still_notchecked.png"))

    browser.close()

print("\n==== SUMMARY ====")
npass = sum(1 for _, ok, _ in findings if ok)
for name, ok, detail in findings:
    print(f"[{'PASS' if ok else 'FAIL'}] {name} {detail}")
print(f"{npass}/{len(findings)} passed")
sys.exit(0 if npass == len(findings) else 1)
