# English Presentation Script · 2026-08-25 (under 15 minutes)

> Companion deck: `ArchCheck_Progress_2026-08-25.pptx` (9 slides)
> Style: plain English, every term explained. Read time ≈ 13–14 min.
> Timing at the bottom.

---

## Opening (no slide)

"Good afternoon. Today I want to walk you through what we did this week. Two parts. First: our semantic search for the building-code knowledge base — we moved from keyword matching to actually understanding questions. Second: the bigger picture — a six-tier roadmap we follow toward a production-ready compliance tool, where we are, and what comes next. I'll keep it clear — about 15 minutes."

---

## Slide 1 — Semantic Knowledge Base Search (30s)

This first part is about the knowledge base. Our tool reviews buildings against the codes.
To do that, we have built a RAG‑powered knowledge base from collected official regulatory materials.

---

## Slide 2 — Before: Three Hard Limits (1 min)

"Here's what the old keyword search couldn't do — three hard limits.

First, **synonyms**. Search for 'escape' and the system can't find clauses that use the word 'evacuation' — even though they mean the same thing. Second, **language**. Searching 'exit' in English never finds the Chinese word for exit, '出口'. Third, **natural language**. You can only type keywords — you can't ask a real question, like 'can gas pipes run in a residential stairwell?'

The result was frustrating. The knowledge base actually had the answers. Users just couldn't reach them."

---

## Slide 3 — Semantic Search Launched (1.5 min)

"So this week we launched semantic search. The idea is simple. Every code clause is converted into a mathematical vector — a list of 1,024 numbers that captures its *meaning*. When you ask a question, we convert that too, then find the clauses whose vectors are closest. We match meaning — that's why synonyms and different languages work.

On the technical side: the model is **bge-m3** — free, open-source, multilingual — so Chinese and English work together. It runs on a standard CPU, no GPU needed. The corpus is 1,590 text chunks from knowdlege base — one Chinese, five Singaporean.

And  These are  results we tested.Search 'escape stair width' — it finds both the Chinese evacuation-stairs clause *and* the Singaporean one . YOU can also Ask in English or ask  a whole question. Asking about a concrete scene, Even indirect phrasing,semantic search could understand.These are Things that keyword search could not do."

---

## Slide 4 — How Well Does It Work? (2 min)

" how well does it actually work? We wanted honest numbers, so we built a proper test: 63 questions. 55 that the knowledge base *should* be able to answer, plus 8 about topics it does **not** cover — to check it doesn't make things up.

Let me walk you through our evaluation results and break down what these metrics actually mean.
For each test question, we send it to our knowledge‑base search system and get back a ranked list of regulation clauses.
Starting with our top‑hit accuracy: 67% of the time, the very‑first result we return contains the exact regulation clause we are looking for.
Since our pipeline feeds the top‑three retrieved chunks into the LLM as context, we check our P3 score.
It reaches 84% — meaning the correct clause appears somewhere within those top‑three results that we pass to our language model.
We also achieve an 84% recall rate. In other words, 84 percent of all target clauses that should be retrieved are successfully picked up by our system.
The F1‑score of 75% gives us an overall balanced measure combining both precision and recall.
Now you may notice a much higher 91% figure. This comes from a less strict, document‑level test. It only confirms we found the correct regulation file — yet the specific clause inside that document could still be wrong.
Therefore, the stricter, more realistic benchmark for our retrieval quality is the P1 value at 67%.

Two findings worth knowing. First: **finding the document is not finding the clause** — that's the gap between 91% and 67%. Second, and this is honest: a classic keyword method — called BM25 — scored 71%, close to ours. So semantic search is **not a replacement** for keyword search. It wins on synonyms, cross-language and natural wording — so we keep both.

Finally, the **anti-fabrication guard**. On those 8 out-of-scope questions, without the guard, all 8 would return a confident-but-wrong answer. With the guard, only 4 do — and it never blocked a correct answer: zero out of 55. Accurate, and honest — nothing inflated."

---

## Slide 5 — Roadmap Title (30s)

"That's the search part. Now let me step back and show the bigger picture:based on the exited functions, this is the roadmap to make this tool genuinely production-ready — something you could actually trust for real building review."

---

## Slide 6 — The Roadmap at a Glance (2 min)

"We organised the work into six tiers, each benchmarked against how the industry does it. 

**Tier 1 — IFC reading.** Reading the building model. This week we already read spaces, doors, structure, MEP — that's mechanical, electrical and plumbing — plus electrical equipment, and we compute exact area, volume and materials. Next: connections between elements, distribution systems, openings, and quantity sets.

**Tier 2 — Quality validation.** Checking the model itself is complete. Done: four QA checks, with honest flags when something isn't checked. Next: an IDS-based validator — the industry's machine-readable way to tell us the exact problems and automatically catch missing data.

**Tier 3 — Precise geometry and quantities.** The one I did this week — I'll show it on the next slide.

**Tier 4 — Clash and coordination.** 
Its goal is to spot locations where different building systems interfere with each other.
So far we have completed our basic‑level check between pipes and structural elements, with verified results.
Moving forward, we will carry out full cross‑disciplinary clash detection, headroom clearance inspection and site‑grading analysis.

**Tier 5 — Rules.** We now have rules covering five disciplines, with a total of 16 rules.
Our tool can convert raw regulatory text into executable machine‑based rules.
Moving ahead, we plan to scale up our rule set from 16 to over 50, while adding contextual conditions and rule exceptions.

**Tier 6 — Delivery and trust.** its about the format to Export results. 

One sentence: the foundation is built — precise geometry, real samples, multi-discipline rules, delivery formats. Now we build up."

---

## Slide 7 — Breakthrough: Precise Geometry (1.5 min)

"Let me walk you through the part i focus on most this week: precise geometry and quantity calculation.

**Exact area.** we apply triangle projection rather than rough bounding shapes.
As an example, an L‑shaped room was over‑estimated at 36 m² with the old box method, while its true area is 27 m².

**Exact volume.** We can also compute real‑world volumes. 

**Material and quantity take-off.** Our system supports material‑based quantity take‑off. It outputs volumes for concrete, steel and other materials,as well as counts of different element types, which directly meets construction‑cost estimating requirements.

**Mixed-unit repair.** Besides that, we have built‑in mixed‑unit repair. Many real‑world models contain unit inconsistency errors,
for instance stating millimetres while modelled in metres. Our tool automatically detects and fixes this issue.

**Basic clash pre-check.** We have also implemented basic clash pre‑checks. We can identify cases where pipes physically go through beams,
and confirm real collisions instead of false clashes caused by bounding‑box approximation.

---


## Slide 9 — Next Steps, Consolidated (1.5 min)

"Finally, what we plan to do next .

**Knowledge-base side**, we have four priorities.
First, we will tackle difficult search queries involving paraphrased wording and technical aliases. Right now our performance here stands at only 45 %, which is our main weak point.
Second, we aim to improve cross‑code retrieval. When a single question requires both Chinese and Singaporean building codes, our current recall rate is just 33 %. We plan to route searches by jurisdiction or split the query to handle this.
Third, we will strengthen our safety guard mechanism using the score gap between top‑ranked results. So far we have achieved zero false rejects.
Fourth, we will keep expanding our test dataset alongside our growing knowledge base.

**Platform side:** We will extend our rule set from 16 to over 50 rules, starting with fire safety, egress and MEP requirements. This will take two to three weeks.
We will add IDS‑based model quality checking within one‑to‑two weeks.
Then we deepen clash‑detection functions, covering full‑discipline interference checks, headroom clearance and site grading, over two weeks.
For final delivery features, we will implement BCF viewpoints and richer COBie exports, and run tests on more than 10 real‑world projects, which will take another one‑to‑two weeks.
Long‑term goals include geometry boolean operations, full rule coverage, and performance benchmarking against commercial software tools.

---

## Timing

| Slide | Section | Time |
|---|---|---|
| — | Opening | 0:15 |
| 1 | Semantic title | 0:30 |
| 2 | Before: three hard limits | 1:00 |
| 3 | Semantic search launched | 1:30 |
| 4 | Results | 2:00 |
| 5 | Roadmap title | 0:30 |
| 6 | Roadmap overview | 2:00 |
| 7 | Breakthrough: geometry | 1:30 |
| 8 | Done vs still open | 1:30 |
| 9 | Next steps | 1:30 |
| — | Total | ≈ 13:15 |
