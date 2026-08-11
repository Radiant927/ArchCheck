# ArchCheck

AI-powered multi-floor building code compliance review platform with a multi-agent architecture (Civil + EEE + Building + Coordinator) and switchable code standards (China GB / Singapore Fire Code 2023).

## Overview

ArchCheck automates building plan review by running specialized agents independently per floor (fire safety, electrical), aggregating whole-building totals, then merging results to detect cross-discipline conflicts on the same floor. Each floor may be compliant individually while the building as a whole fails aggregate thresholds — a gap manual review routinely misses.

**Key features:**
- **Multi-Agent Review** — Civil Agent (per-floor fire safety), EEE Agent (per-floor electrical), Building Agent (cross-floor aggregates), Coordinator (conflict detection)
- **Standard Switching** — Toggle between Chinese GB standards and Singapore Fire Code 2023 with one click; rules, thresholds, and code references swap automatically
- **JSON-Driven Rule Engine** — 8 operators, conditional filtering, per-standard rule directories, hot-reloadable without code changes
- **Multi-Floor Data Model** — Floors[] array + building_params; review engine iterates floors then checks whole-building totals
- **Per-Floor Annotation** — Color-coded numbered markers overlaid on floor plans; each floor gets its own annotated and correction images
- **One-Click Export** — Per-floor annotated PNG, per-floor correction PNG, unified HTML report covering all floors

## Quick Start

```bash
cd ArchCheck
pip install -r requirements.txt
streamlit run app.py
# Opens http://localhost:8501
```

Click **"Quick Demo"** to load a 3-floor sample building. Switch between 🇨🇳 GB and 🇸🇬 FC23 in the sidebar to see how violations differ between standards.

## Project Structure

```
ArchCheck/
├── app.py                     # Streamlit UI (imports from core/)
├── core/                      # Modularized engine + display logic
│   ├── config.py              # Paths (HERE/OUTPUT/DATA) + design tokens (C)
│   ├── i18n.py                # Bilingual dict, T/LANG, set_language, labels
│   ├── engine.py              # Rule engine: load_standard, run_rules, run_full_review
│   ├── drawing.py             # Floor-plan drawing / annotation / correction / section
│   └── report.py              # HTML report generator
├── bim/                       # (new) IFC ingestion — ifcopenshell → building JSON
│   └── parser.py
├── llm/                       # (new) DeepSeek (OpenAI-compatible) client
│   └── client.py
├── data/
│   ├── demo_building_data.json         # 3-floor demo (each floor compliant, building totals fail)
│   └── standards/
│       ├── cn/
│       │   ├── meta.json               # Chinese standard metadata
│       │   ├── civil_rules.json        # GB 50016 — 4 rules
│       │   ├── eee_rules.json          # GB 51309 / 50054 / 50055 — 4 rules
│       │   └── building_rules.json     # GB 50016 / 50974 — 4 cross-floor rules
│       └── sg/
│           ├── meta.json               # Singapore standard metadata
│           ├── civil_rules.json        # FC23 — 4 rules
│           ├── eee_rules.json          # CP 5 / SS 551 / SS 531 — 4 rules
│           └── building_rules.json     # FC23 / SS 575 — 4 cross-floor rules
├── docs/                      # Documentation (this README, demo scripts)
├── scripts/                   # Asset generators (floor plans, defense PPT)
└── output/                    # Runtime generated images (gitignored)
```

## Agent Architecture

```
Upload + Configure (floors + standard)
               │
               ▼
        ┌──────┴──────┐
        ▼             ▼
  Civil Agent    EEE Agent       (runs per floor)
  GB/FC23        GB/FC23
        │             │
        └──────┬──────┘
               ▼
        Building Agent           (aggregate across floors)
        Cross-floor totals
               │
               ▼
        Coordinator              (same-floor civil+eee conflict detection)
               │
               ▼
        Per-floor results + unified HTML report
```

## Rule Format

Rules are stored per standard as JSON and can be edited without changing code:

```json
{
    "id": "BLD-004",
    "name": "Emergency Power Duration Check",
    "field": "emergency_power_duration_min",
    "operator": ">=",
    "threshold": 90,
    "unit": "min",
    "severity": "High",
    "code_ref": "GB 51309 3.2.4",
    "message": "Emergency power {value}min < required {threshold}min."
}
```

Supported operators: `<=`, `>=`, `>`, `<`, `==`, `!=`, `in`, `not_in`. Rules support optional conditional filtering (only evaluate when a precondition on another field is met).

## Adding a New Standard

Adding a standard is a **config-only** change — drop a folder and it appears in
the sidebar automatically (scanned from `data/standards/`):

1. Create `data/standards/<code>/meta.json` (`id`, `name`, `short_name`, `flag`, `language`, `civil_codes`, `eee_codes`)
2. Add rule packs with the shared schema: `civil_rules.json`, `eee_rules.json`,
   `building_rules.json`, and optional `structural_rules.json`
3. Rules may add a `dynamic_threshold` block (formula → RAG/LLM → fallback)

No engine or `app.py` code changes needed.

## Demo Boundaries

This is a proof-of-concept prototype:
- **Floor plans** are code-generated schematic drawings (no CV/OCR integration)
- **Building data** is JSON-driven (not extracted from uploaded images)
- **Building-level rules** use whole-building parameters (no vertical geometric continuity checks)
- **Cross-floor** means aggregate totals, not 3D spatial reasoning

The architecture is designed so CV-based drawing recognition and BIM/IFC parsing can be added as data sources without changing the core review engine.

## License

MIT — see [LICENSE](LICENSE) for details.
