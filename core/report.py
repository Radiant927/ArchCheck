import io
import base64
from datetime import datetime
from core.config import C
from core import i18n

def generate_report(images_by_floor, all_issues, civil_r, eee_r, building_r, structural_r, mep_r, conflicts, std_meta,
                    predictive_r=None, predictive_ranking=None, predictive_monitor=None):
    t = i18n._I18N[i18n.LANG]
    sev_map = {"High": ("高", "high") if i18n.LANG == "zh" else ("High", "high"),
               "Medium": ("中", "mid") if i18n.LANG == "zh" else ("Medium", "mid"),
               "Low": ("低", "low") if i18n.LANG == "zh" else ("Low", "low"),
               "Missing": ("数据缺失", "mid") if i18n.LANG == "zh" else ("Data Missing", "mid"),
               "Predictive": ("预测性", "mid") if i18n.LANG == "zh" else ("Predictive", "mid")}
    priority_label = "优先处理" if i18n.LANG == "zh" else "PRIORITY"
    html_lang = "zh" if i18n.LANG == "zh" else "en"

    floors_html = ""
    for fname, img in images_by_floor.items():
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        img64 = base64.b64encode(buf.getvalue()).decode()
        floors_html += f'<h3>{fname}</h3><div class="img-box"><img src="data:image/png;base64,{img64}" alt="{fname}"></div>'

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    std_label = f'{std_meta.get("flag","")} {std_meta.get("name","")}'
    report_header = "ARCHCHECK · 审查报告" if i18n.LANG == "zh" else "ARCHCHECK · REPORT"

    def rows(items, cls):
        out = ""
        for i, iss in enumerate(items, 1):
            sv = iss.get("severity", "Medium")
            sv_label, sc = sev_map.get(sv, ("?", "mid"))
            rv = ""
            if iss.get("review_status") == "verified":
                rv = f'<span class="sev sev-low">✅ {t["review_verified"]}</span>'
            elif iss.get("review_status") == "manual":
                rv = f'<span class="sev sev-mid">⚠️ {t["review_manual"]}</span>'
            floor_info = ""
            if iss.get("floor_name"):
                floor_info = f' · <span style="color:{C["silver"]};font-size:12px;">{iss["floor_name"]}</span>'
            evid = ""
            if iss.get("review_status") == "verified" and iss.get("review_evidence"):
                evid = (f'<div class="meta" style="color:{C["green"]};">🔍 {t["review_evid"]}: '
                        f'{iss["review_evidence"][:140]}</div>')
            out += (
                f'<div class="card {cls}">'
                f'<div class="title">{i}. {iss["title"]}'
                f'<span class="sev sev-{sc}">{sv_label}</span>{rv}{floor_info}</div>'
                f'<div class="desc">{iss.get("description","")}</div>'
                f'<div class="meta">{t["report_loc"]}: {iss.get("location","-")} | {t["report_ref"]}: {iss.get("code_ref","-")}</div>'
                f'{evid}'
                f'</div>'
            )
        return out

    def summary_rows(cards):
        out = ""
        for c in cards:
            sv_label, sc = sev_map.get(c.get("severity", "Medium"), ("?", "mid"))
            dist = " · ".join(f"{fl}×{n}" for fl, n in c["by_floor"].items())
            out += (
                f'<div class="card">'
                f'<span class="sev sev-{sc}">{sv_label}</span> '
                f'<b>{c["rule_id"]}</b> · <span style="color:{C["muted"]};">{c["title"]}</span> '
                f'<span style="float:right;font-family:monospace;">×{c["count"]}</span>'
                f'<div class="meta">{t["report_distribution"]}: {dist or "—"}</div></div>')
        return out

    from core.engine import aggregate_issues
    _real = [i for i in all_issues if i.get("severity") != "Missing"]
    _n_missing = len(all_issues) - len(_real)
    _sum_cards = aggregate_issues(_real, group_by="rule")
    _miss_note = (f'<div class="meta">{t["missing_section"]}: {_n_missing}</div>'
                  if _n_missing else "")
    summary_section = (
        f'<h2>{t["report_summary_h"]}</h2>'
        f'<div class="meta" style="margin-bottom:10px;">{t["report_summary_sub"]}</div>'
        f'{summary_rows(_sum_cards)}{_miss_note}')

    def ranking_rows(ranking):
        out = ""
        for r in ranking:
            med = r.get("median_failure_year")
            out += (
                f'<div class="meta">#{r["rank"]} · {r["location"]}'
                f' · {r.get("floor_name") or ""} · p={r["p_fail_cycle"]:.0%}'
                f' · median {med if med is not None else "—"}</div>')
        return out

    pred_section = ""
    if predictive_r or predictive_ranking:
        regime = (predictive_monitor or {}).get("regime")
        regime_note = ""
        if regime == "inspection":
            regime_note = (f'<div class="meta" style="color:{C["purple"]};">'
                           f'{t["predictive_regime_inspection"]}</div>')
        elif regime == "sensor":
            regime_note = (f'<div class="meta" style="color:{C["purple"]};">'
                           f'{t["predictive_regime_sensor"]}</div>')
        pred_section = (
            f'<h2>{t["predictive_section_title"]}</h2>'
            f'{regime_note}'
            f'{rows(predictive_r or [], "bld")}'
            f'<h3>{t["predictive_ranking_title"]}</h3>'
            f'{ranking_rows(predictive_ranking or [])}')

    def crow(conflicts):
        out = ""
        for i, c in enumerate(conflicts, 1):
            out += (
                f'<div class="card cnf">'
                f'<div class="title">{i}. {c["title"]}'
                f'<span class="sev sev-high">{priority_label}</span></div>'
                f'<div class="desc">{c.get("description","")}</div>'
                f'<div class="meta">{t["report_loc"]}: {c.get("location","-")} | {c.get("related_issues","")}</div>'
                f'</div>'
            )
        return out

    no_civ = f'<div class="card" style="border-left:4px solid #7CB342;background:#EEF5E2;"><span class="title" style="color:#7CB342;">{t["report_no_civ"]}</span></div>'
    no_eee = f'<div class="card" style="border-left:4px solid #7CB342;background:#EEF5E2;"><span class="title" style="color:#7CB342;">{t["report_no_eee"]}</span></div>'
    no_bld = f'<div class="card" style="border-left:4px solid #7CB342;background:#EEF5E2;"><span class="title" style="color:#7CB342;">{t["report_no_bld"]}</span></div>'
    no_str = f'<div class="card" style="border-left:4px solid #7CB342;background:#EEF5E2;"><span class="title" style="color:#7CB342;">{t["report_no_str"]}</span></div>'
    no_mep = f'<div class="card" style="border-left:4px solid #7CB342;background:#EEF5E2;"><span class="title" style="color:#7CB342;">{t["report_no_mep"]}</span></div>'
    no_cnf = f'<div class="card" style="border-left:4px solid #7CB342;background:#EEF5E2;"><span class="title" style="color:#7CB342;">{t["report_no_conf"]}</span></div>'

    label_css = "" if i18n.LANG == "en" else "text-transform:none;letter-spacing:.12em;"

    return f"""<!DOCTYPE html><html lang="{html_lang}"><head><meta charset="UTF-8"><title>ArchCheck {t["report_title"]}</title><style>
*{{margin:0;padding:0;box-sizing:border-box;}}
body{{font-family:'Segoe UI','PingFang SC','Microsoft YaHei',sans-serif;max-width:960px;margin:0 auto;padding:40px 32px;color:{C["text"]};background:{C["bg"]};background-image:linear-gradient({C["border"]} 1px,transparent 1px),linear-gradient(90deg,{C["border"]} 1px,transparent 1px);background-size:32px 32px;}}
.band{{display:flex;height:6px;border-radius:3px;margin-bottom:32px;overflow:hidden;}}
.band-c{{flex:2;background:{C["blue"]};}}.band-e{{flex:1;background:{C["orange"]};}}.band-b{{flex:1;background:{C["purple"]};}}.band-r{{flex:1;background:{C["red"]};}}.band-p{{flex:.6;background:{C["green"]};}}
.label{{font-size:12px;letter-spacing:.34em;color:{C["silver"]};font-weight:600;text-transform:uppercase;margin-bottom:8px;{label_css}}}
.std-badge{{display:inline-block;padding:4px 12px;border-radius:2px;background:{C["purple"]}18;color:{C["purple"]};font-weight:600;font-size:13px;margin-bottom:12px;}}
h1{{font-size:52px;font-weight:800;line-height:1.15;margin-bottom:4px;}}h1 span{{color:{C["blue"]};}}
.subtitle{{font-size:17px;color:{C["muted"]};font-weight:300;margin-bottom:32px;}}
.stats{{display:flex;gap:12px;margin-bottom:32px;flex-wrap:wrap;}}
.stat{{flex:1;min-width:120px;background:#FFF;border:1px solid {C["border"]};border-radius:4px;padding:16px;text-align:center;}}
.stat .val{{font-size:36px;font-weight:800;}}.stat .lbl{{font-size:11px;color:{C["silver"]};letter-spacing:.08em;text-transform:uppercase;margin-top:4px;}}
.stat.c .val{{color:{C["blue"]};}}.stat.e .val{{color:{C["orange"]};}}.stat.b .val{{color:{C["purple"]};}}.stat.r .val{{color:{C["red"]};}}
h2{{font-size:24px;font-weight:700;margin:28px 0 12px;padding-bottom:8px;border-bottom:2px solid {C["text"]};}}
h3{{font-size:18px;font-weight:600;margin:20px 0 8px;color:{C["muted"]};}}
.img-box{{text-align:center;margin:16px 0;}}.img-box img{{max-width:100%;border-radius:4px;border:1px solid {C["border"]};}}
.card{{background:#FFF;border:1px solid {C["border"]};border-radius:2px;padding:14px 18px;margin-bottom:8px;}}
.card.civ{{border-left:4px solid {C["blue"]};}}.card.eee{{border-left:4px solid {C["orange"]};}}
.card.bld{{border-left:4px solid {C["purple"]};background:#F8F5FC;}}.card.str{{border-left:4px solid {C["green"]};background:#F0F7E9;}}.card.mep{{border-left:4px solid #1f6f8b;background:#EFF7FA;}}.card.cnf{{border-left:4px solid {C["red"]};background:#FEF2F2;}}
.card .title{{font-weight:700;font-size:15px;}}.card.civ .title{{color:{C["blue"]};}}.card.eee .title{{color:{C["orange"]};}}
.card.bld .title{{color:{C["purple"]};}}.card.str .title{{color:{C["green"]};}}.card.mep .title{{color:#1f6f8b;}}.card.cnf .title{{color:{C["red"]};}}
.card .desc{{font-size:14px;color:{C["muted"]};margin-top:4px;}}.card .meta{{font-size:13px;color:{C["silver"]};margin-top:4px;font-family:monospace;}}
.sev{{display:inline-block;margin-left:8px;padding:1px 8px;border-radius:2px;font-size:12px;font-weight:600;}}
.sev-high{{background:#FEF2F2;color:{C["red"]};}}.sev-mid{{background:#FFF7ED;color:{C["orange"]};}}.sev-low{{background:#F9FAFB;color:{C["silver"]};}}
.footer{{text-align:center;font-size:13px;color:{C["silver"]};margin-top:40px;border-top:1px solid {C["border"]};padding-top:16px;}}
</style></head><body>
<div class="label">{report_header}</div>
<div class="band"><div class="band-c"></div><div class="band-e"></div><div class="band-b"></div><div class="band-r"></div><div class="band-p"></div></div>
<div class="std-badge">{std_label}</div>
<h1>{t["report_title"]}</h1><div class="subtitle">{t["report_sub"]} · {now}</div>
<div class="stats">
<div class="stat"><div class="val">{len(civil_r)+len(eee_r)+len(building_r)+len(structural_r)+len(mep_r)}</div><div class="lbl">{t["report_total"]}</div></div>
<div class="stat c"><div class="val">{len(civil_r)}</div><div class="lbl">{t["s_civil"]}</div></div>
<div class="stat e"><div class="val">{len(eee_r)}</div><div class="lbl">{t["s_eee"]}</div></div>
<div class="stat b"><div class="val">{len(building_r)}</div><div class="lbl">{t["s_bld"]}</div></div>
<div class="stat b"><div class="val">{len(structural_r)}</div><div class="lbl">{t["s_str"]}</div></div>
<div class="stat b"><div class="val">{len(mep_r)}</div><div class="lbl">{t["s_mep"]}</div></div>
<div class="stat r"><div class="val">{len(conflicts)}</div><div class="lbl">{t["s_conf"]}</div></div>
</div>
{summary_section}
<h2>{t["report_annotated"]}</h2>
{floors_html}
<h2>{t["report_civ_h"]}</h2>
{rows(civil_r,'civ') if civil_r else no_civ}
<h2>{t["report_eee_h"]}</h2>
{rows(eee_r,'eee') if eee_r else no_eee}
<h2>{t["report_bld_h"]}</h2>
{rows(building_r,'bld') if building_r else no_bld}
<h2>{t["report_str_h"]}</h2>
{rows(structural_r,'str') if structural_r else no_str}
<h2>{t["report_mep_h"]}</h2>
{rows(mep_r,'mep') if mep_r else no_mep}
{pred_section}
<h2>{t["report_conf_h"]}</h2>
{crow(conflicts) if conflicts else no_cnf}
<div class="footer">{t["report_footer"]}</div>
</body></html>"""
