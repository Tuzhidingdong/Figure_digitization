# STATUS — Figure_digitization

> Execution tracking for [TASK_PLAN_v1.4.1.md](./TASK_PLAN_v1.4.1.md). This file records implementation progress only; it does not modify the frozen objective, scope, constraints, or acceptance criteria.

## Baseline

- Task Plan: [TASK_PLAN_v1.4.1.md](./TASK_PLAN_v1.4.1.md)
- Task Plan version: v1.4.1
- Baseline status: FROZEN — DO NOT EDIT
- Plan commit: 6d6386e13da72d67d70bc0a93b83df2cce6594c3
- Implementation branch: main
- Implementation status: IN PROGRESS
- Release status: NOT AUTHORIZED
- Default runtime: Windows 10/11; 8 GB RAM; 4 logical CPU cores; no GPU
- Default worker mode: one isolated worker, sequential lazy streaming
- Default LLM usage: zero tokens

## Current milestone

**M0 — Repository and executable foundation**

The frozen requirements baseline has been verified. Implementation is authorized. The repository had no application code at the start of this milestone. Work is proceeding on `main`; the frozen Task Plan is not being edited.

## Progress

| Area | Status | Evidence / notes |
|---|---|---|
| v1.4.1 Task Plan frozen | COMPLETE | `TASK_PLAN_v1.4.1.md`; original blob retained |
| Implementation authorization | COMPLETE | User authorization in conversation, 2026-11-19 |
| Repository foundation and package metadata | IN PROGRESS | Initial implementation |
| Read-only upstream adapter | NOT STARTED | |
| Corpus/paper manifests and fingerprints | NOT STARTED | |
| Paper-level MAIN/SI context index | NOT STARTED | |
| PDF backend abstraction and 3–5-PDF probe | NOT STARTED | No approved real PDF benchmark files supplied yet |
| Scheduler, leases, recovery | NOT STARTED | |
| P0 figure/panel inventory | NOT STARTED | |
| P0 raster/vector/hybrid extraction | NOT STARTED | Must report actual supported scope honestly |
| Domain profiles | NOT STARTED | Battery / AOP / PFOA-PFAS |
| Canonical artifacts and SQLite single writer | NOT STARTED | |
| Query and ML export CLI | NOT STARTED | |
| Offline review helper and patch apply | NOT STARTED | |
| QC provisional thresholds | NOT STARTED | Calibrated thresholds require annotated real papers |
| Windows resource and crash tests | NOT STARTED | Cannot be fully verified in hosted GitHub-only development |
| Real-paper P0 validation | BLOCKED ON USER BENCHMARK INPUT | No approved PDFs/annotations are present in this repository |
| P1 implementation | DEFERRED | Per frozen plan |
| P2 implementation | DEFERRED | Per frozen plan |

## Acceptance tracking

The canonical acceptance criteria are AC-01–AC-102 in the frozen Task Plan.

No criterion is marked scientifically validated until corresponding evidence is recorded. Implementation tests do not substitute for real-paper benchmark acceptance.

- P0: AC-01–AC-50, AC-52–AC-98, subject to stated prerequisites.
- P1: AC-51, AC-99–AC-100.
- P2: AC-101.
- Release: AC-06, AC-16, AC-36, AC-68, AC-94, AC-102.

## Engineering log

### 2026-11-19 — M0 started

- Verified repository default branch and frozen Task Plan.
- Verified baseline Task Plan commit: `6d6386e13da72d67d70bc0a93b83df2cce6594c3`.
- Verified latest pre-development commit: `a8d7ed790d52b36208771450098d0721a5a40c27`.
- Confirmed the repository had no application code at the start.
- User explicitly authorized implementation directly in this repository.
- Non-negotiable: do not modify `TASK_PLAN_v1.4.1.md`.
- Real-paper backend benchmarking and calibrated QC remain dependent on user-approved PDF/annotation inputs.

## Constraints carried forward

- Windows-first; baseline 8 GB RAM / 4 logical CPU cores / no GPU.
- One worker by default; lazy synchronous iteration inside the worker.
- Bounded queues only at actual asynchronous boundaries.
- Heavy PDF/image resources must be loaded on demand and released promptly.
- Compact cross-page MAIN/SI text context is allowed; image pages remain on-demand.
- Zero LLM tokens by default; no automatic paid-model fallback.
- Upstream `chem-literature` inputs are read-only.
- Workers never write concurrently to SQLite.
- Real annotated papers are required for scientific acceptance.
- Provisional QC must be labeled `PROVISIONAL_UNCALIBRATED`.
- P0 ambiguous same-color/crossing/marker-dependent raster curves may be routed to `NEEDS_REVIEW`.
- Review patches must use base-hash validation and reject stale patches.
- No public release or publication is authorized.
