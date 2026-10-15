# -*- coding: utf-8 -*-
"""User-supplied maintenance CSV -> bdata records.

Pure functions (no Streamlit) so the parsing rules are unit-testable and the
UI layer only renders their output. Accepted files mirror the bdata contract
consumed by ``risk.adapter``:

  pipe_service.csv    global_id, install_year, floor_env, prior_repairs
  maintenance_log.csv global_id, year, status
  pipe_monitoring.csv global_id, depth_now_mm[, growth_rate_mm_yr]

Rows that cannot be parsed are dropped and reported; nothing is guessed.
Header synonyms (Chinese and English) are normalised on import.
"""

import io

import numpy as np
import pandas as pd

_HEADER_SYNONYMS = {
    "global_id": ["global_id", "gid", "id", "comp_id", "构件id", "管道id",
                  "构件编号"],
    "install_year": ["install_year", "year_installed", "installed_year",
                     "安装年份", "安装年"],
    "floor_env": ["floor_env", "env", "environment", "环境"],
    "prior_repairs": ["prior_repairs", "repairs", "repair_count", "既往维修",
                      "维修次数"],
    "year": ["year", "年份", "年"],
    "status": ["status", "state", "状态"],
    "depth_now_mm": ["depth_now_mm", "depth_mm", "depth", "壁厚", "腐蚀深度",
                     "当前壁厚"],
    "growth_rate_mm_yr": ["growth_rate_mm_yr", "growth_rate", "rate",
                          "腐蚀速率", "增长速率"],
}

_FLOOR_ENV_MAP = {
    "dry": "dry", "干燥": "dry", "干": "dry",
    "humid": "humid", "wet": "humid", "moist": "humid",
    "潮湿": "humid", "湿润": "humid", "湿": "humid",
    "underground": "underground", "buried": "underground", "ug": "underground",
    "埋地": "underground", "地下": "underground",
}

_STATUS_MAP = {
    "alive": "alive", "ok": "alive", "正常": "alive", "运行": "alive",
    "failed": "failed", "fail": "failed", "failure": "failed",
    "失效": "failed", "故障": "failed", "漏水": "failed",
    "穿孔": "failed", "锈蚀": "failed",
    "not_installed": "not_installed", "未安装": "not_installed",
}


def read_csv_bytes(data):
    """Parse uploaded CSV bytes/string. Tries UTF-8 (with BOM) first, then
    GBK — the encodings produced by Excel in English and Chinese locales."""
    if isinstance(data, str):
        data = data.encode("utf-8")
    last_err = None
    for enc in ("utf-8-sig", "gbk"):
        try:
            return pd.read_csv(io.BytesIO(data), encoding=enc, dtype=str)
        except UnicodeDecodeError as e:
            last_err = e
    raise ValueError(f"CSV encoding not recognised (expected UTF-8 or GBK): {last_err}")


def _normalise_columns(df):
    """Return {canonical: series} using the first matching synonym header."""
    lookup = {}
    for col in df.columns:
        key = str(col).strip().lower().replace(" ", "_")
        for canonical, syns in _HEADER_SYNONYMS.items():
            if key in syns and canonical not in lookup:
                lookup[canonical] = df[col]
    return lookup


def _as_float(value):
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if np.isfinite(f) else None


def _as_nonneg_int(value):
    f = _as_float(value)
    if f is None or f < 0:
        return None
    return int(f)


def _require(cols, name, problems, row):
    s = cols.get(name)
    if s is None:
        problems.append(f"缺少必需列 {name}")
        return None
    v = s.iloc[row]
    if v is None or (isinstance(v, float) and np.isnan(v)) or str(v).strip() == "":
        problems.append(f"第 {row + 2} 行：{name} 为空")
        return None
    return str(v).strip()


def parse_service_csv(df):
    """-> (records, problems). Records match bdata['pipe_service']."""
    cols = _normalise_columns(df)
    records, problems = [], []
    gid_col = cols.get("global_id")
    year_col = cols.get("install_year")
    if gid_col is None or year_col is None:
        return [], [f"缺少必需列（需要 global_id, install_year；实际列：{list(df.columns)}）"]
    env_seen_bad = set()
    for row in range(len(df)):
        gid = _require(cols, "global_id", problems, row)
        if gid is None:
            continue
        year = _as_float(year_col.iloc[row])
        if year is None:
            problems.append(f"第 {row + 2} 行：install_year 非法（{year_col.iloc[row]!r}）")
            continue
        raw_env = cols["floor_env"].iloc[row] if "floor_env" in cols else ""
        env = _FLOOR_ENV_MAP.get(str(raw_env or "").strip().lower())
        if env is None and str(raw_env or "").strip():
            env_seen_bad.add(str(raw_env).strip())
            env = "dry"  # adapter baseline for unrecognised environments
        elif env is None:
            env = "dry"
        repairs = 0
        if "prior_repairs" in cols:
            repairs = _as_nonneg_int(cols["prior_repairs"].iloc[row]) or 0
        records.append({"global_id": gid, "install_year": year,
                        "floor_env": env, "prior_repairs": repairs})
    for v in sorted(env_seen_bad):
        problems.append(f"floor_env 值 {v!r} 无法识别，已按默认 dry 处理")
    if not records:
        problems.append("没有任何有效数据行")
    return records, problems


def parse_log_csv(df):
    """-> (records, problems). Records match bdata['maintenance_log']."""
    cols = _normalise_columns(df)
    if "global_id" not in cols or "year" not in cols or "status" not in cols:
        return [], [f"缺少必需列（需要 global_id, year, status；实际列：{list(df.columns)}）"]
    records, problems = [], []
    status_seen_bad = set()
    for row in range(len(df)):
        gid = _require(cols, "global_id", problems, row)
        if gid is None:
            continue
        year = _as_nonneg_int(cols["year"].iloc[row])
        if year is None:
            problems.append(f"第 {row + 2} 行：year 非法（{cols['year'].iloc[row]!r}）")
            continue
        raw_status = str(cols["status"].iloc[row] or "").strip().lower()
        status = _STATUS_MAP.get(raw_status)
        if status is None:
            status_seen_bad.add(raw_status)
            continue
        records.append({"global_id": gid, "year": year, "status": status})
    for v in sorted(status_seen_bad):
        problems.append(f"status 值 {v!r} 无法识别，该行已丢弃")
    if not records:
        problems.append("没有任何有效数据行")
    return records, problems


def parse_monitoring_csv(df):
    """-> (records, problems, status). status is 'ok' or 'invalid'.

    The growth-rate column must be present on every row or absent entirely;
    a mixed file is a contract violation and nothing is loaded."""
    cols = _normalise_columns(df)
    if "global_id" not in cols or "depth_now_mm" not in cols:
        return [], [f"缺少必需列（需要 global_id, depth_now_mm；实际列：{list(df.columns)}）"], "invalid"
    has_rate_col = "growth_rate_mm_yr" in cols
    records, problems = [], []
    rate_missing = 0
    for row in range(len(df)):
        gid = _require(cols, "global_id", problems, row)
        if gid is None:
            continue
        depth = _as_float(cols["depth_now_mm"].iloc[row])
        if depth is None or depth < 0:
            problems.append(f"第 {row + 2} 行：depth_now_mm 非法（{cols['depth_now_mm'].iloc[row]!r}）")
            continue
        rec = {"global_id": gid, "depth_now_mm": depth}
        if has_rate_col:
            rate = _as_float(cols["growth_rate_mm_yr"].iloc[row])
            if rate is None or rate < 0:
                rate_missing += 1
                continue
            rec["growth_rate_mm_yr"] = rate
        records.append(rec)
    if not records:
        return records, problems + ["没有任何有效数据行"], "invalid"
    if has_rate_col and (rate_missing > 0 or any(
            "growth_rate_mm_yr" not in r for r in records)):
        return [], ["growth_rate_mm_yr 必须在每一行都存在或都不存在"], "invalid"
    return records, problems, "ok"


def building_pipe_ids(bdata):
    """Set of pipe global_ids extracted from the building."""
    ids = set()
    for fl in bdata.get("floors", []):
        for p in fl.get("pipes", []):
            gid = p.get("global_id")
            if gid:
                ids.add(str(gid))
    return ids


def validate_ids(records, bdata):
    """Match uploaded rows against the building's pipe global_ids."""
    known = building_pipe_ids(bdata)
    matched, unmatched, seen, dupes = [], [], set(), []
    for r in records:
        gid = str(r["global_id"])
        if gid in seen:
            dupes.append(gid)
            continue
        seen.add(gid)
        if gid in known:
            matched.append(r)
        else:
            unmatched.append(gid)
    return {"matched": matched, "unmatched": unmatched, "dupes": dupes,
            "n_known": len(known)}


def _csv_bytes(headers, rows):
    buf = io.StringIO()
    buf.write(",".join(headers) + "\n")
    for r in rows:
        buf.write(",".join(str(v) for v in r) + "\n")
    return buf.getvalue().encode("utf-8-sig")


def service_template():
    return _csv_bytes(
        ["global_id", "install_year", "floor_env", "prior_repairs"],
        [["P0001", 2014, "dry", 0], ["P0002", 2009, "humid", 1]])


def log_template():
    return _csv_bytes(
        ["global_id", "year", "status"],
        [["P0001", 2024, "alive"], ["P0002", 2023, "failed"]])


def monitoring_template():
    return _csv_bytes(
        ["global_id", "depth_now_mm", "growth_rate_mm_yr"],
        [["P0001", 1.20, 0.08], ["P0002", 2.55, 0.15]])
