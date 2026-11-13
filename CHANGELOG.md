# Changelog

## Unreleased

- Explained the purpose and concrete scenarios on all three demo pages, including full-width/half-width product identifiers, explicit zero values and quoted CSV fields.
- Added inline control explanations, a glossary, walkthroughs, result-reading guidance and a live model-call plan. UI descriptions do not change model prompts or evaluation data.

## v0.2.0 — 2026-11-13

- Added a real-model pilot using native Ollama or a configurable Chat Completions compatible endpoint.
- Added paired deployment contracts, a no-log control, a generic structured-line filter and a separately labelled oracle reference.
- Added bounded original-log retrieval, cumulative provider-reported usage, asynchronous UI progress, trace export and local per-run persistence.
- Kept four reserved tasks out of model runs; browser experiments are development-only.
- Added related-work notes, protocol documentation and actual pilot traces, including failed prompt calibrations.
- Kept both original offline demos. The installed 1B model does not reliably solve the paired tasks; this release makes no compression superiority claim.

## v0.1.0 — 2026-11-13

First public release of Agent Budget Lab.

- Two local, interactive experiments: tool-output compression and cheap-probe strategy selection.
- Three executable repair cases, editable visible logs and side-by-side compression results.
- Five locally trained scikit-learn models plus a keyword baseline; three budgeted selectors.
- Reproducible seeds, explicit budget accounting, actual run export and example JSON results.
- Chinese UI, English overview and detailed Chinese instructions.
- Windows launcher, MIT license, automated checks and a reproducible Release ZIP builder.

This release uses synthetic data and a fixed rule-based diagnosis policy. It does not call LLMs or reproduce a published benchmark.
