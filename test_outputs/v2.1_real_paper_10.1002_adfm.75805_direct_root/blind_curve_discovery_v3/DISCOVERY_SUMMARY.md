# Blind curve discovery v3 - generic algorithm improvements

## Algorithm changes (what changed and why)
- **Generic non-data-graphic classification**: every connected candidate component now gets aspect ratio, area/fill/solidity (convex hull), skeleton-to-area ratio, bbox rectangularity, PCA direction consistency, line-width estimate, row/column alignment with other components, nearby-component count, path continuity with other paths, and original-image luminance/chroma. Classification is rule-based from these features; no fixed region, component ID, target count or hardcoded color is used.
- **Global trajectory association**: greedy reciprocal pairing was replaced by a deterministic successive-shortest-path **min-cost flow path cover**. Nodes are ordered path fragments; directed edges score endpoint residual, tangent change, X ordering, occlusion gap, line-width and luminance consistency, with one-fragment-one-trajectory capacity constraints. Edges: 2 over 17 fragments.
- **Junction/crossing analysis**: degree!=2 skeleton nodes are enumerated over all valid port pairings, scored by tangent straightness and competing margin; no junction is auto-collapsed and no pixels are synthesized.
- **Source-pixel audit**: all new official points must belong to the pre-morphology candidate foreground mask; v2 audit/bridge CSVs were read as historical inputs only.

## Per-change report
- Candidate components enumerated: 67.
- Classified NON_DATA_GRAPHIC_CANDIDATE: 41; AMBIGUOUS_REVIEW kept: 24; DATA_PATH_CANDIDATE: 2.
- Global trajectory hypotheses: 16 (plus 14 junction hypotheses).
- Base global solution raw edge cost: 1.539 (flow objective -28.461 with continuity bonus 30.0); fragments assigned: 17; unassigned: 0.
- Competing solution ALT_E1: raw cost 2.084 vs base 1.539, flow margin 0.545, confidence LOW_NEAR_TIE; constraint: forbid edge F062.P1 -> F062.P3.
- Competing solution ALT_C15: raw cost 2.084 vs base 1.539, flow margin 0.545, confidence LOW_NEAR_TIE; constraint: forbid all edges of base chain 15.

## Which hypotheses gained or lost support
- Near-horizontal neutral strip fragments lost support as independent data paths: they merge into shallow filled components that are now classified non-data or ambiguous, and the only surviving link among such fragments has a LOW_NEAR_TIE margin of 0.545.
- Compact near-square chromatic blocks gained support as non-data graphics: generic solidity/rectangularity/row-alignment features classify them without any fixed region or ID.
- Merged shallow filled components with several paths and many junctions (strip grids/glyph rows) LOST support as trajectories: the generic multi-strip rule removed them from the fragment graph, so the multi-fragment chain they previously produced is no longer emitted.
- The border-spanning component matching the plot frame was rejected generically by a border-pixel-fraction rule, not by coordinate constants.
- Long continuous chromatic and achromatic paths retained support as the only DATA_PATH_CANDIDATE components under the generic rules; their independence remains the best-supported reading, with achromatic identity still evidence-only.
- Junction continuations are no longer forced to a single branched path; competing port pairings are retained with margins.

## Source-pixel audit result
- New points audited: 552; valid original foreground: 542; excluded: 10 [[192, 96], [193, 96], [194, 96], [195, 95], [196, 95], [197, 95], [198, 103], [207, 98], [206, 96], [206, 95]].
- All official points are exact source pixels; morphology never created a measurement point; real gaps and independent segments are preserved.

## Remaining unresolved items and next capability
- All 17 fragments were placed in chains (mostly singletons; one linked pair), but every placement is REVIEW_ONLY; 0 fragments have no chain, and 24 components remain AMBIGUOUS_REVIEW. The linked pair has a 0.545 near-tie margin, so its association is not resolved.
- Next needed capability: local machine-readable text/axis anchors (OCR) to unblock calibration, plus a validated achromatic-identity extractor and scale-aware scoring learned from annotated papers (thresholds here remain provisional).

## Confirmation
- No vision model/LLM, no forbidden prior outputs read, no source committed, git status unchanged from session start; worktree HEAD a296ca29205215b1bf71380a966bc6d814776f01.
