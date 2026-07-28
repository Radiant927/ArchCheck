# ArchCheck

AI-powered building code compliance review platform with a multi-agent architecture (Civil + EEE + Coordinator).

## Overview

ArchCheck automates building plan review by having specialized agents independently check fire safety (Civil) and electrical (EEE) compliance, then merging results to detect cross-discipline conflicts.

**Key features:**
- **Multi-Agent Review** — Civil Agent (GB 50016), EEE Agent (GB 51309/50054/50055), Coordinator for conflict detection
- **JSON-Driven Rule Engine** — 8 operators, conditional filtering, hot-reloadable rules
- **Violation Annotation** — Color-coded numbered markers overlaid on floor plans
- **Correction Suggestions** — Green callout boxes with specific fix instructions per violation
- **One-Click Export** — Annotated PNG, correction plan PNG, and self-contained HTML report

## Quick Start

```bash
# Clone and enter the project
cd ArchCheck

# Install dependencies
pip install -r requirements.txt

# Launch the app
streamlit run app.py
# Opens http://localhost:8501
```

Click **"Quick Demo"** to load sample building data and see a full review pipeline.

## Project Structure

```
ArchCheck/
├── app.py                  # Main Streamlit application (upload, review, results, architecture pages)
├── requirements.txt        # Python dependencies
├── .streamlit/
│   └── config.toml         # Streamlit theme configuration
├── data/
│   ├── civil_rules.json    # Civil/fire safety rules (4 rules, GB 50016)
│   ├── eee_rules.json      # Electrical safety rules (4 rules, GB 51309/50054/50055)
│   └── demo_building_data.json  # Demo building with 5 rooms + 2 fire zones
├── scripts/
│   ├── generate_floor_plans.py  # Generate demo floor plan images
│   └── generate_ppt.py          # Generate presentation slides
├── docs/
│   ├── tasks.md                  # Development task log (completed)
│   ├── 讲稿.docx                 # Defense presentation script
│   ├── ArchCheck_答辩讲稿指南.md  # Defense presentation guide
│   └── 网页介绍讲稿.md            # Web platform introduction script
└── output/                 # Runtime generated images and reports (gitignored)
```

## Agent Architecture

```
Upload Floor Plan
       │
       ▼
┌──────────────────┐    ┌──────────────────┐
│   Civil Agent    │    │    EEE Agent     │
│  (Fire Safety)   │    │  (Electrical)    │
│  GB 50016        │    │  GB 51309/50054  │
│  4 rules         │    │  4 rules         │
└────────┬─────────┘    └────────┬─────────┘
         │                       │
         └───────────┬───────────┘
                     ▼
         ┌──────────────────────┐
         │    Coordinator       │
         │  Merge + Conflict    │
         │  Detection           │
         └──────────┬───────────┘
                     ▼
            Results + Report
```

Both agents run in parallel on the same building data. The Coordinator merges results by location and flags zones where both civil and electrical violations overlap — the cross-discipline conflicts that manual review most often misses.

## Rules Configuration

Rules are stored as JSON and can be modified without changing code:

```json
{
    "id": "CIVIL-001",
    "name": "Evacuation Distance Check",
    "field": "corridor_length_m",
    "operator": "<=",
    "threshold": 30,
    "severity": "High",
    "code_ref": "GB 50016 5.5.17",
    "message": "Corridor too long (actual {value}m > limit {threshold}m)."
}
```

Supported operators: `<=`, `>=`, `>`, `<`, `==`, `!=`, `in`, `not_in`. Rules support optional condition fields (only evaluate when a precondition is met).

## Demo Boundaries

This is a **proof-of-concept prototype**. The multi-agent architecture, rule engine, violation annotation, and report generation are real and functional. However:

- **Floor plans** are code-generated schematic drawings (no CV/OCR integration)
- **Building data** is hardcoded JSON (not extracted from uploaded images)
- **Rule count** is limited to 8 demonstration rules

The architecture is designed so that CV-based drawing recognition can be added as a data source without changing the core review engine.

## License

MIT — see [LICENSE](LICENSE) for details.
