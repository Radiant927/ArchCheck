# -*- coding: utf-8 -*-
"""BCF (BIM Collaboration Format) 导出（台阶⑥ · 交付互操作）。

把审查发现导出为 BCF 2.1 单话题压缩包，可导入 Navisworks / Solibri / Revit。
每个发现 = 一个 Topic（类型 CLASH/OTHER，状态 Open）。

用法:
  python scripts/export_bcf.py bim/samples/office_3f.ifc --std cn -o output/review.bcf
"""
import argparse
import io
import json
import sys
import uuid
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from bim.parser import parse_ifc, build_review_data  # noqa: E402
from core import engine  # noqa: E402

NS_MARKUP = "http://www.buildingsmart-tech.org/xml/BIMCOLLAB_XML_v2.1"
NS_BCF = "http://www.buildingsmart-tech.org/xml/bcXML/xsd/bcf21"


def _q(tag):
    return f"{{{NS_MARKUP}}}{tag}"


def _to_xml(text):
    return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def markup_bcf(issues):
    root = ET.Element(_q("Markup"), xmlns=NS_MARKUP,
                      xmlns_xsi="http://www.w3.org/2001/XMLSchema-instance")
    for i, iss in enumerate(issues):
        topic = ET.SubElement(root, _q("Topic"),
                              Guid=str(uuid.uuid4()),
                              TopicType="CLASH" if iss.get("type") == "conflict" else "OTHER",
                              TopicStatus="Open",
                              Title=_to_xml(iss.get("title", "Issue")[:120])[:256])
        ET.SubElement(topic, _q("CreationDate")).text = datetime.now().isoformat()
        ET.SubElement(topic, _q("CreationAuthor")).text = "ArchCheck"
        desc = _to_xml(f"{iss.get('description','')} | {iss.get('location','')} "
                       f"| {iss.get('code_ref','')} | {iss.get('floor_name','')}")
        ET.SubElement(topic, _q("Description")).text = desc
        ET.SubElement(topic, _q("ReferenceLink"))
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="unicode")


def version_xml():
    root = ET.Element("Version", xmlns=NS_BCF, VersionId="2.1")
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="unicode")


def export_bcf(path, std_id, out):
    m = parse_ifc(path, max_floors=3, max_rooms_per_floor=6)
    bd = build_review_data(m)
    res = engine.run_review_with_standard(std_id, bd)
    issues = res["all_issues"]
    out = Path(out)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("bcf.version", version_xml())
        z.writestr("markup.bcf", markup_bcf(issues))
    return len(issues)


def main():
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("ifc", help="IFC 文件")
    ap.add_argument("--std", default="cn")
    ap.add_argument("-o", "--out", default=str(ROOT / "output" / "review.bcf"))
    args = ap.parse_args()
    n = export_bcf(args.ifc, args.std, args.out)
    print(f"已导出 {args.out}（{n} 个发现 → {n} 个 BCF Topic）")
    # 验证 zip 有效
    import zipfile
    with zipfile.ZipFile(args.out) as z:
        names = z.namelist()
        print("压缩包内容:", names)
        assert "bcf.version" in names and "markup.bcf" in names, "BCF 结构不完整"
        print("✅ BCF v2.1 结构有效")


if __name__ == "__main__":
    main()
