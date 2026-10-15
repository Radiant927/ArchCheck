# -*- coding: utf-8 -*-
"""为 UI 演示/浏览器测试生成三份与真实 IFC 管道 global_id 对齐的维保 CSV。

    python scripts/make_demo_maintenance_csvs.py bim/samples/Duplex_MEP_20110907.ifc

输出到 output/demo_csv/：pipe_service.csv / maintenance_log.csv /
pipe_monitoring.csv（sensor 体制）。合成数据仅用于演示上传闭环，不是真实
建筑结论；管道的 material/pipe_type 同时写回 CSV 无法做到（这两列来自
IFC），不匹配时 adapter 按 baseline 处理，与平台既有行为一致。
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from bim.parser import parse_ifc, build_review_data
from risk.families import get_family
from risk.generator import (generate_population, annual_maintenance_log,
                            regime_measurements)

ifc_path = Path(sys.argv[1]) if len(sys.argv) > 1 else REPO / \
    "bim" / "samples" / "Duplex_MEP_20110907.ifc"
out = REPO / "output" / "demo_csv"
out.mkdir(parents=True, exist_ok=True)

print(f"parsing {ifc_path.name} ...")
bdata = build_review_data(parse_ifc(ifc_path))
gids = [p["global_id"] for fl in bdata.get("floors", [])
        for p in fl.get("pipes", []) if p.get("global_id")]
n = len(gids)
print(f"{n} pipes")

family = get_family("steel_pipe")
pop = generate_population(family, n, seed=7)

# real global_ids replace the synthetic ids; all failure/timing columns are
# derived from the same generated rows so the dataset stays self-consistent.
pop["comp_id"] = gids

service = pop[["comp_id", "install_year", "floor_env", "prior_repairs"]]
service.to_csv(out / "pipe_service.csv", index=False, encoding="utf-8-sig")

log = annual_maintenance_log(pop, years=range(2016, 2026))
log = log.rename(columns={"comp_id": "global_id"})
log.to_csv(out / "maintenance_log.csv", index=False, encoding="utf-8-sig")

reading = regime_measurements(family, pop, 7, "sensor", 0.05, 5)
reading = reading.rename(columns={"comp_id": "global_id"})
reading.to_csv(out / "pipe_monitoring.csv", index=False, encoding="utf-8-sig")

print(f"wrote {out}: service {len(service)}, log {len(log)}, "
      f"monitoring {len(reading)}")
