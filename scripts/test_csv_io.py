# -*- coding: utf-8 -*-
"""Unit tests for risk.csv_io: encodings, header synonyms, value mapping,
bad-row dropping, ID validation, monitoring regime rule, templates.

Exit code nonzero on the first failed assertion group.
"""
import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from risk import csv_io

FAILS = []


def check(name, cond, detail=""):
    print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f" -- {detail}" if detail else ""))
    if not cond:
        FAILS.append(name)


BDATA = {
    "floors": [{
        "pipes": [{"global_id": "A1"}, {"global_id": "A2"},
                  {"global_id": "A3"}],
    }],
}

# 1. encoding
utf8_csv = "global_id,install_year,floor_env,prior_repairs\nA1,2010,dry,1\n".encode("utf-8-sig")
gbk_csv = "构件id,安装年份,环境,维修次数\nA2,2012,潮湿,2\n".encode("gbk")
check("UTF-8-BOM CSV parsed", list(csv_io.read_csv_bytes(utf8_csv).columns)[0] == "global_id")
check("GBK CSV + Chinese headers parsed",
      list(csv_io.read_csv_bytes(gbk_csv).columns)[0] == "构件id")
try:
    csv_io.read_csv_bytes(b"\xff\xfe,bad")
    check("garbage encoding rejected", False)
except ValueError:
    check("garbage encoding rejected", True)

# 2. service parse + value mapping
svc_rows = (
    "global_id,install_year,floor_env,prior_repairs\n"
    "A1,2010,干燥,1\n"
    "A2,2012/03,埋地,x\n"          # year invalid -> dropped
    "A3,2015,wet,0\n").encode("utf-8")
recs, problems = csv_io.parse_service_csv(
    csv_io.read_csv_bytes(svc_rows))
check("service valid rows", len(recs) == 2, str(len(recs)))
check("service floor_env zh mapped",
      {r["global_id"]: r["floor_env"] for r in recs} ==
      {"A1": "dry", "A3": "humid"})
check("service prior_repairs bad -> 0", recs[0]["prior_repairs"] == 1)
check("service problems reported", any("2012/03" in p for p in problems),
      str(problems))

# unrecognised env -> baseline dry, reported
svc2, p2 = csv_io.parse_service_csv(pd.DataFrame({
    "global_id": ["A1"], "install_year": [2010], "floor_env": ["garbage"],
    "prior_repairs": [0]}))
check("unknown env -> baseline dry + problem",
      svc2[0]["floor_env"] == "dry" and any("garbage" in p for p in p2))

# missing required column
svc3, p3 = csv_io.parse_service_csv(pd.DataFrame({"global_id": ["A1"]}))
check("missing install_year -> no records", not svc3 and p3)

# 3. log parse
log_rows = (
    "comp_id,year,status\n"
    "A1,2024,正常\n"
    "A2,2023,漏水\n"
    "A3,bad,alive\n"
    "A1,2018,???\n").encode("utf-8")
lrecs, lproblems = csv_io.parse_log_csv(csv_io.read_csv_bytes(log_rows))
check("log valid rows", len(lrecs) == 2, str(len(lrecs)))
check("log status zh mapped",
      {(r["global_id"], r["year"]): r["status"] for r in lrecs} ==
      {("A1", 2024): "alive", ("A2", 2023): "failed"})
check("log bad rows reported", len(lproblems) == 2, str(lproblems))

# 4. monitoring
mon_rows = (
    "global_id,depth_now_mm,growth_rate_mm_yr\n"
    "A1,1.2,0.05\nA2,2.4,0.10\n").encode("utf-8")
mrecs, mproblems, status = csv_io.parse_monitoring_csv(
    csv_io.read_csv_bytes(mon_rows))
check("sensor monitoring ok", status == "ok" and len(mrecs) == 2
      and all("growth_rate_mm_yr" in r for r in mrecs))

insp_rows = "global_id,depth_now_mm\nA1,1.2\nA2,2.4\n".encode("utf-8")
irecs, iproblems, istatus = csv_io.parse_monitoring_csv(
    csv_io.read_csv_bytes(insp_rows))
check("inspection monitoring ok", istatus == "ok"
      and all("growth_rate_mm_yr" not in r for r in irecs))

# mixed: rate column present but one row empty
mixed_rows = (
    "global_id,depth_now_mm,growth_rate_mm_yr\n"
    "A1,1.2,\nA2,2.4,0.10\n").encode("utf-8")
xrecs, xproblems, xstatus = csv_io.parse_monitoring_csv(
    csv_io.read_csv_bytes(mixed_rows))
check("mixed regime -> invalid, no records", xstatus == "invalid" and not xrecs,
      str(xproblems))

bad_depth = "global_id,depth_now_mm\nA1,-1\n".encode("utf-8")
drecs, dproblems, dstatus = csv_io.parse_monitoring_csv(
    csv_io.read_csv_bytes(bad_depth))
check("negative depth -> no records", not drecs and dstatus == "invalid")

# 5. ID validation
v = csv_io.validate_ids(
    [{"global_id": "A1"}, {"global_id": "A2"}, {"global_id": "ZZ"},
     {"global_id": "A1"}], BDATA)
check("ID matched/unmatched/dupes",
      len(v["matched"]) == 2 and v["unmatched"] == ["ZZ"]
      and v["dupes"] == ["A1"], str(v))

# 6. templates round-trip through own parsers
for tpl, parser, extra in (
        (csv_io.service_template(), csv_io.parse_service_csv, False),
        (csv_io.log_template(), csv_io.parse_log_csv, False),
        (csv_io.monitoring_template(), csv_io.parse_monitoring_csv, True)):
    df = csv_io.read_csv_bytes(tpl)
    if extra:
        r, pr, stt = parser(df)
        ok = stt == "ok" and len(r) == 2
    else:
        r, pr = parser(df)
        ok = len(r) == 2
    check(f"template {tpl[:20]} round-trips", ok, str(pr))

print("\n" + ("ALL CHECKS PASSED" if not FAILS
               else f"{len(FAILS)} CHECK(S) FAILED: {FAILS}"))
sys.exit(1 if FAILS else 0)
