# cdt_webapp_v4 — qa_v9 grounded RAG Q&A on the synthetic cohort

A Streamlit app that turns the synthetic meningioma cohort into evidence-grounded
treatment recommendations (watch & wait / surgery / radiation) **and** answers
free-form clinical questions about the cohort with the full notebook-4.12 qa_v9
engine.

Pages 1 (Try It) and 2 (Recommendation) are unchanged from v3. Page 3 (Cohort)
has been rebuilt with the qa_v9 engine.

## Run

```bash
cd cdt_webapp_v4
pip install -r requirements.txt
streamlit run app.py
```

Optionally configure your OpenAI key (only the Q&A panel needs it):

```bash
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
# edit to add openai_api_key = "sk-..."
```

or `export OPENAI_API_KEY="sk-..."`.

## What's different from v3

| Aspect | v3 | v4 |
|---|---|---|
| Q&A router LLM call | 1 (filter spec only — 5 nullable fields) | 1 (full plan: qtype + filters + arms + stratifier + time_window + pathways + adjusters + parts) |
| Question types | None — every question collapses into "filter + fixed stats" | **9 types**: FACTUAL, DESCRIPTIVE, DESCRIPTIVE-TEMPORAL, COMPARATIVE, SUBGROUP-COMPARATIVE, TRAJECTORY, TEMPORAL-CONDITIONAL, PATHWAY-FUNNEL, COMPARATIVE-ADJUSTED + COMPOUND wrapper |
| Statistical core | Wilson CI on cohort proportion, breakdowns by grade/location/age/gender/first_action | Clopper-Pearson + Fisher's exact + Cochran-Mantel-Haenszel + IPW (single + multi-covariate via sklearn) + bootstrap CI + E-value + MDE + SMD baseline balance |
| Synthesis | Single compose call (2-4 sentences) | Interpretation paragraph + structured caveats + responsivity rewrite (4 LLM calls total) |
| Output | Markdown prose only | Structured panels: direct answer card, cohort funnel, outcomes table, subgroup detail with reliability badges + CMH pooled OR, collapsible appendix (baseline differences + adjusted analysis), caveats list with locked-vs-LLM markers |
| Deterministic caveats | None | 5 locked categories (strong selection effects, E-value sensitivity, underpowered, suppressed strata, COMPARATIVE-ADJUSTED no-sensitivity) |
| LLM model | gpt-4o-mini | **gpt-4o** |
| Data loader | Drops continuous size, months, surgery subtype, raw events | Retains all v7 fields (level_info with continuous size + months + surgery/radiation subtype + symptoms; v7_raw_events list; functional_status; action_sequence) |
| Page 1, 2 | Unchanged from v3 | Unchanged (copied verbatim) |
| Cost per question | ~$0.005 (2 calls, gpt-4o-mini) | ~$0.02–0.05 (4 calls, gpt-4o) |

The data source is identical: `data/dummy_cohort.csv` (the same 250 synthetic
patients from `ground_truths_synth_v4`). Nothing in v2 or v3 was modified.

## Layout

```
cdt_webapp_v4/
  app.py                 Overview / landing
  pages/
    1_Try_it.py          Patient picker + curated exemplars (= v3)
    2_Recommendation.py  Full decision detail for one patient (= v3)
    3_Cohort.py          Filters + pathway viz + data quality + qa_v9 Q&A
  lib/
    config.py            (= v3) where to point at a different CSV
    bootstrap.py         (= v3) cached cohort load
    buckets.py           (= v3) bucketing + action constants
    data_loader.py       expanded to keep continuous v7 fields + v9 keys
    engine.py            (= v3) recommendation engine for pages 1/2
    figures.py           (= v3) pathway Sankey
    nav.py, style.py     (= v3) shared UI
    openai_key.py        (= v3) key resolver
    qa.py                qa_v9 engine: router + 9 builders + stats + IPW + synth
    qa_render.py         Streamlit panels for screenshot-style structured output
  tools/
    build_dummy_csv.py   (= v3) synthetic cohort → demo CSV
  data/
    dummy_cohort.csv     (= v3) synthetic demo data (250 patients)
  .streamlit/, requirements.txt, README.md, .gitignore
```

## How the v9 Q&A pipeline works

```
question (free text)
   ↓
LLM router (gpt-4o)  →  typed plan JSON
   {qtype, base_filter, arms?, stratifier?, time_window?, pathways?, adjusters?, parts?}
   ↓
verify_router_plan (vocabulary + structural checks; 2-retry loop)
   ↓
dispatch_block_builder → per-qtype block (Clopper-Pearson, Fisher, CMH, IPW, E-value, SMD)
   ↓
build_deterministic_caveats (5 locked categories from data signals)
   ↓
LLM interpretation pass (paragraph; numbers locked from block)
   ↓
LLM caveats pass (1-3 additional structured caveats)
   ↓
LLM responsivity pass (rewrite direct_answer to literally address question)
   ↓
render_answer → Streamlit panels:
   - direct answer card (qtype + reliability badges)
   - cohort construction funnel
   - outcomes table with 95% CIs
   - comparison summary (abs diff + RR + Fisher p + E-value)
   - subgroup detail (by grade / age / location) with reliability + CMH OR
   - interpretation paragraph
   - caveats list (LOCKED vs LLM)
   - appendix: baseline differences (SMD), adjusted analysis (multi-cov IPW)
   - debug: router plan, locked block, verifier output
```

Same statistical core as notebook `4.12_knowledge_qa_v9_thirty.ipynb`. The only
operational differences from 4.12: the LLM model (gpt-4o vs gpt-5) and the
LLM transport (OpenAI SDK vs Azure LLM_wrapper).

Not for clinical use. Outputs are illustrative.
