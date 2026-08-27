# ArchCheck Platform Intro · 3-min Script (2026-08-25)

> Use: opening intro of the platform + architecture, then a live demo with **office_3f** that walks through the platform features page by page.
> Demo setup: sidebar standard = **🇸🇬 Singapore Standard** (English UI).
> Demo model: `bim/samples/office_3f.ifc` (self-built sample, ground truth known, parses in ~2 s).
> Total runtime: ~3 minutes. Timings are guides — the demo is the core; trim the architecture part if running long.

---


---

## 〔0:15–1:00〕Architecture page (brief — the demo carries the story)

> This is the architecture — a pipeline of **five role-based agents**. They are **modules with separate responsibilities**, not autonomous agents:

<flow>
IFC upload → ① BIM Reader → ② Compliance Judge → ⑤ Independent Reviewer → ④ Reasoner
                    ↘ ③ KB Steward (knowledge base feeds ② and ⑤)
</flow>

> - **① BIM Reader** — parses the IFC model, runs model-usability QA, and outputs a **health score 0–100**; a broken model is blocked here;
> - **② Compliance Judge** — a **deterministic rules engine** that reviews **five disciplines** (fire, electrical, structural, accessibility, MEP) — **value vs threshold**, dynamic thresholds, cross-floor aggregation, conflict detection;
> - **③ KB Steward** — maintains the regulation knowledge base (RAG), supplies the **code references and dynamic thresholds** used in judgement;
> - **④ Reasoner** — the LLM, only writes the **review narrative** and coordinates cross-discipline conflicts; **it never judges numbers**;
> - **⑤ Independent Reviewer** — retrieves the regulation text and **re-verifies** the judgement (verified ✅ / manual ⚠️) with an evidence snippet.
>
> The reason for splitting into five is to avoid a single over-loaded module: **reading, judging, and re-verifying all run on deterministic code** — reproducible and auditable — while the LLM only does narrative. Standards: **China GB ↔ Singapore Fire Code 2023**, one-click switch, bilingual UI.

---

## 〔1:00–2:45〕Live demo — office_3f (walk through the features)

### Upload page — what the reader does
> Now the demo. I upload **office_3f**, a three-storey office model I generated with a script, so the ground truth is known.
> Parsing takes about two seconds. Right away, **① BIM Reader** reports the **model health score: 100** — four check categories all pass: **length units, space completeness, geometry validity, space-boundary references**. A broken model would be blocked here.
> Below, the parsed **building parameters** — floors, footprint **323 m²**, 18 rooms, walls/doors/windows per floor, door width 0.9 m. Note the honesty markers: **🟢 = from the model, 🟠 = default, pending input** — nothing is fabricated.
> And the plan views generated from the **real geometry**: a **3D isometric** of the whole building, a **top-down plan per floor** (selectable), and a **building section** showing storey relations. These are data-driven — change the model, the drawings update.

### Run review → results page
> Now run the review. The results page is organized by the same agents.

> **Top stats:** 15 findings, 3 **high-severity**, 0 conflicts, all 5 disciplines actually judged — plus a per-discipline status line so "checked & clean" is distinguishable from "not checked".

> **Findings list (② Compliance Judge).** A filter by discipline. Each card shows: title, **discipline tag + severity tag + floor tag**, the measured-vs-required description, and **location + code reference**. Highlights:
> - Ground-floor exit width **2.4 m < 3.0 m (High)** — Fire Code;
> - Fire water tank **160 m³ < 180 m³ (High)**;
> - Emergency lighting missing in corridors, transformer undersized (**650 kW < 750 kW**)…
> Some findings carry a green **evidence snippet** (⑤ Independent Reviewer) retrieved from the RAG corpus.

> **Right panel:** the **3D view** again, and the **annotated per-floor plan** — findings marked on the room centroids, with a floor selector. Below, the **whole-building section** showing where on each floor the fire/electrical/conflict issues sit.

> **More sections:** an expander with **structural quantities by material** (real volumes), a coarse **MEP-vs-structure clash** candidate list.

> **Standard switching.** Switch the sidebar to China GB — the review re-runs automatically and a diff panel shows what **appears/disappears** between the two standards. Same model, different code basis.

> **④ Reasoner (LLM).** One click generates an **AI review narrative** and cross-discipline coordination advice — this is the only place the LLM speaks; it summarizes, it doesn't judge.

> **Export.** HTML report, **Excel** of all findings, and annotated/correction plan images — one click.

---

## 〔2:45–3:00〕Close · data foundation + one-line summary

> The code references come from the **RAG knowledge base**: free standards (Fire Code 2023, GB 55037/55036…) are **fully searchable**; paid standards keep an index and are marked "refer to the original text".
> One-line summary: **data is truly read from the model, judgement is truly made by a rules engine, and the code basis is verifiable in the knowledge base.**

---

## Demo quick reference (avoid surprises live)

1. Sidebar standard: **Singapore** (English). Switch to China Standard to demo the **standard diff**.
2. Model path: `bim/samples/office_3f.ifc` (~2 s parse).
3. Health **100** → results page → **15 findings / 3 High**.
4. Reproducible numbers: exit width **2.4 vs 3.0**, tank **160 vs 180**, transformer **650 vs 750**.
5. Feature tour order: upload QA → params 🟢🟠 → 3D/plan/section → stats → findings cards (tags, code_ref, evidence) → annotated plan → section → standard diff → AI report → export.

> Backup model: FZK Haus (real ArchiCAD model) — mention as "a real-world model" if needed; default demo stays office_3f.
