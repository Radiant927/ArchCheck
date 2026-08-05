# ArchCheck — 演示口语稿 (优化易读版)

> **How to run the app:** switch the sidebar to **🇸🇬 Singapore FC23** (English UI), then follow the steps below.
>
> **Numbers:** SG standard shows **14 issues**; flip to **🇨🇳 China GB** and it becomes **20 issues** with the UI switching to Chinese — a live demo of one-click standard switching.

---

## Opening (0:00 – 0:20)

**Screen:** Upload & Review page

> “This is ArchCheck — an AI platform that checks building codes for multi-floor buildings. Traditional checking is slow, makes mistakes, and misses two big problems. First, each floor might look fine alone, but the whole building fails when we add up the numbers. Second, different teams might mark problems at the same spot，we need to detect that. our platform is aimed to solve both problems using multiple AI agents.”

---

## Standard Switching (0:20 – 0:35)

**Screen:** click the sidebar radio

> “On the left, we can switch the checking standard  — China GB or Singapore Fire Code. Changing the standard doesn’t just change he numbers; the whole rule set, code references, and even the app language change automatically.”

**Action:** flip 🇸🇬→🇨🇳 (UI flips to Chinese), then back.

---

## Architecture (0:35 – 0:45)

now lets move to the “Platform Architecture” page

> “We have four AI agents: Civil for fire safety, EEE for electrical, Building for whole-building totals, and a Manager to find conflicts.”

**Action:** scroll quickly.

### Development Roadmap

Finally, here is our development roadmap.

Phase 1 is already complete. We built the core engine, including the multi-agent framework, the JSON rules, and the HTML report and so on.

For Phase 2, we plan to add AI analysis. We will use computer vision to detect rooms, use ML to predict issue severity, and support more international standards.

In the future, Phase 3 will focus on an enterprise platform. We plan to add BIM support, real-time collaboration, and cloud deployment.

---

## Load Demo (0:45 – 0:55)

**Screen:** back to “Upload & Review”

> “We will use a three-floor office building to make a simple demo.The right is the eidition area. Every number here is editable and directly runs the rules. Let’s load the sample.”

**Action:** click “Quick Demo”.

---

## Review Animation (0:55 – 1:15)

**Screen:** agent logs streaming

> “The check runs floor by floor. Civil and EEE check each floor at the same time. Then, the Building agent adds up the totals for the whole building — like exit width, water tank, and power. Finally, the Manager finds conflicts between teams. Let it finish.”

---

## Results — the key message (1:15 – 2:05)

**Screen:** results page

> “Here are the results — 14 issues. The most important parts are the last two cards: whole-building issues and cross-team conflicts.”

**Action:** click the “Building” tab.

> “This is what normal checks miss. Each floor looks fine, but the whole-building totals fail. Let’s look at the fire water tank. Every floor meets its own requirement, but when the Building agent adds them up, the total water volume is not enough for the whole building. The purple line in this 3D view shows that total running through all floors.”

**Action:** expand “Standard Switching Impact”.

> “If we switch the standard, the rules for the water tank change. For example, under the China GB standard, the required volume is much larger. One building, two rule sets, easily compared.”

**Action:** select a floor, show Before/After, then the “Conflicts” tab.

> “On each floor, blue markers are civil, orange are electrical, and green boxes give clear fixes. Finally, the Manager marks spots where both teams find problems — like this corridor. Everything can be exported to a marked plan and a report.”

---

## Closing (2:05 – 2:20)

> “Multiple AI agents working together, one-click standard switching, and a smart rule system that lets you add new rules without changing the code. That’s ArchCheck.”
