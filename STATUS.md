# STATUS — Figure_digitization

> Execution tracking for TASK_PLAN_v1.4.1.md. This file records implementation progress only; it does not modify the frozen objective, scope, constraints, or acceptance criteria.

## Baseline

- Task Plan: [TASK_PLAN_v1.4.1.md](./TASK_PLAN_v1.4.1.md)
- Task Plan version: v1.4.1
- Baseline status: FROZEN
- Plan commit: ffa4ce89df61e1539f912802288980f0209dbb38
- Implementation status: NOT STARTED
- Release status: NOT AUTHORIZED

## Current milestone

**M0 — Repository and technical-spike preparation**

The requirements baseline has been committed. No application code, extraction algorithm, runtime dependency, or release artifact has been implemented.

## Progress

| Area | Status | Evidence |
|---|---|---|
| v1.4.1 Task Plan frozen | COMPLETE | TASK_PLAN_v1.4.1.md |
| Upstream read-only contract | NOT STARTED | — |
| Corpus/paper manifest design | NOT STARTED | — |
| PDF backend technical spike (3–5 representative PDFs) | NOT STARTED | — |
| Annotated real-paper benchmark selection | PENDING USER INPUT | — |
| P0 implementation | NOT STARTED | — |
| P0 real-paper validation | NOT STARTED | — |
| P1 implementation | DEFERRED | — |
| P2 implementation | DEFERRED | — |

## Acceptance tracking

- P0 criteria: AC-01–AC-50 and AC-52–AC-98, subject to their stated prerequisites and evidence requirements.
- P1 criteria: AC-51, AC-99, AC-100.
- P2 criteria: AC-101.
- Release criteria: AC-06, AC-16, AC-36, AC-68, AC-94, AC-102 (some are also P0 implementation criteria).

No acceptance criterion is marked implemented or validated at baseline.

## First authorized engineering work

1. Initialize repository structure and documentation conventions without changing the frozen Task Plan.
2. Define the read-only chem-literature input contract and representative adapter fixtures.
3. Prepare the 3–5 PDF backend technical spike, including Peak RSS, per-page time, object/path coverage, Windows compatibility, and license review.
4. Record the spike results and backend decision before committing to the P0 PDF extraction implementation.

## Constraints carried forward

- Windows-first; baseline target 8 GB RAM / 4 logical CPU cores / no GPU.
- Default one-worker sequential streaming.
- Zero LLM tokens by default; no automatic paid-model fallback.
- Upstream chem-literature inputs are read-only.
- Real annotated papers are required for scientific acceptance.
- Do not claim calibrated QC while only provisional thresholds exist.
- No public release or publication is authorized.
