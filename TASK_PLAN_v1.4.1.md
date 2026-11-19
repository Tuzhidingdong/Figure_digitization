# User Task Plan — scientific-figure-data-skill-v1.4.1

> The user owns this document. Antigravity and workers must preserve the original objective, constraints, scope and acceptance criteria. Execution progress belongs in the sibling STATUS.md.
>
> **Document status:** Frozen development baseline  
> **Project:** scientific-figure-data-skill  
> **Target repository:** Tuzhidingdong/scientific-figure-data  
> **Version:** v1.4.1  
> **Upstream dependency:** Tuzhidingdong/chem-literature  
> **Primary platform:** Windows 10/11  
> **Baseline hardware:** 8 GB RAM, 4 logical CPU cores, no dedicated GPU  
> **Default execution:** One isolated worker, sequential streaming, bounded memory  
> **Default LLM usage:** Zero tokens  
> **Execution tracking:** Sibling STATUS.md

## 1. Objective

Develop an independent, reusable scientific figure data extraction Skill named scientific-figure-data-skill.

The Skill processes existing outputs from the upstream chem-literature Skill and extracts scientifically meaningful numerical data from scientific figures, charts, spectra, and other visual representations in source PDFs.

The ultimate objective is to transform several thousand papers and their existing chem-literature outputs into traceable, queryable scientific data that can support:

- Finding different experimental techniques associated with the same paper and the same sample or research subject.
- Retrieving XRD, Raman, CV, GCD, EIS, and other measurements belonging to the same material or specimen.
- Associating plotted data with experimental conditions, reference systems, analytes, catalysts, products, and other scientific entities.
- Comparing scientifically compatible results across multiple papers.
- Constructing evidence-backed machine-learning datasets.
- Reusing previously extracted data without repeatedly processing unchanged papers.
- Reviewing, correcting, and versioning extracted scientific data without losing its original provenance.

The Skill must operate as an independent downstream project. It must not modify, replace, or redesign the upstream chem-literature Skill.

### Core engineering principle: resource-bounded streaming

The expected corpus contains thousands of papers. The system must not require high-end hardware or load the entire corpus, complete PDFs, or all extracted images into memory.

Its default operating strategy must be:

1. Discover papers incrementally.
2. Process one paper at a time.
3. Read PDF pages on demand.
4. Render only the pages and regions required by the current stage.
5. Process figures and panels independently.
6. Reconstruct series and persist points in bounded batches.
7. Release large image and PDF resources as soon as possible.
8. Retain only compact, reusable scientific context and evidence indexes in memory.
9. Save completed stages so interrupted jobs do not need to restart from the beginning.

The default implementation must use one worker and sequential processing. Parallelism is optional and must never be required for normal operation.

### Scientific integrity principle

This is an evidence-driven extraction and data-management system, not an autonomous scientific interpretation system.

The system must preserve the difference between:

- Values directly extracted from a figure.
- Values reported in tables or text.
- Values calculated from other observations.
- Values standardized through deterministic transformations.
- Scientific relationships inferred from source evidence.
- Relationships that remain uncertain.

It must never invent numerical precision, silently guess scientific semantics, or merge scientifically incompatible measurements.

Uncertain results should remain available with explicit states such as UNKNOWN, UNASSIGNED, NEEDS_REVIEW, REFERENCE_CONVERSION_UNRESOLVED, and NEEDS_SCHEMA_MAPPING.

The aim is reliable scientific data extraction, not maximizing the percentage of figures that appear automatically completed.

## 2. Current state

### 2.1 Existing upstream project

The upstream project already exists:

- Repository: Tuzhidingdong/chem-literature
- Role: Literature and PDF preprocessing.
- Existing outputs may include extracted text, tables, figure inventories, table inventories, captions, page references, figure images, evidence indexes, and other intermediate artifacts.

Possible text-context sources include:

- main_analysis.md
- si_analysis.md
- extracted_tables/
- Existing manifests and evidence indexes.
- Other supported upstream text and metadata artifacts.

Actual file availability and naming may vary across upstream versions and paper directories.

The downstream Skill must discover the available artifacts rather than assume that every paper contains every file.

### 2.2 New downstream project

The new project is an independent repository:

- Repository: Tuzhidingdong/scientific-figure-data
- Skill ID: scientific-figure-data-skill
- Version baseline: v1.4.1
- Role: Figure extraction, numerical reconstruction, scientific association, QC, review, storage, query, and ML-oriented export.

The upstream adapter must be read-only.

The downstream Skill must be independently installable and usable without requiring changes to chem-literature.

### 2.3 Initial scientific domains

**Battery and energy storage**

- XRD, Raman, FTIR, XPS.
- Cyclic voltammetry (CV).
- Galvanostatic charge/discharge (GCD).
- Electrochemical impedance spectroscopy (EIS).
- GITT and related measurements.
- Rate performance, cycling performance, capacity, energy, and power.

**Advanced oxidation processes (AOP)**

- Pollutant degradation kinetics.
- C/C0 versus time.
- Pollutant removal efficiency.
- TOC and COD.
- Radical quenching and active-species identification.
- Reaction conditions, catalysts, and reactors.

**PFOA/PFAS decomposition**

- PFOA, PFOS, PFHxA, and other target pollutants.
- Parent-compound removal.
- Defluorination and F⁻ release.
- Mineralization.
- Total fluorine and organic fluorine.
- Fluorine mass balance.
- Short-chain products.
- LC-MS/MS results where supported.

These domains must be implemented through extensible profiles rather than through fixed assumptions in the core engine.

### 2.4 Existing architectural decisions

The following conceptual distinctions are mandatory:

- SubjectEntity is not Condition.
- Condition is not Measurement.
- Measurement is not Series.
- Figure is not Panel.
- A digitized graphical series is not a scalar observation reported in a table or text.
- A figure-level sample association is not sufficient to establish the identity of every curve in that figure.
- Raw values are not normalized values.
- Extracted values are not automatically scientifically comparable values.
- Evidence must remain traceable through every transformation.

### 2.5 Development strategy

Development must proceed in this order:

1. Establish the repository, Skill structure, contracts, and STATUS.md.
2. Define the upstream adapter and corpus/paper manifests.
3. Perform a 3–5 PDF backend technical spike.
4. Establish a small annotated real-paper benchmark selected or approved by the user.
5. Implement the P0 streaming extraction and persistence workflow.
6. Validate P0 against real papers.
7. Add P1 and P2 capabilities incrementally.

Do not spend the development effort building a large general-purpose framework before proving that the actual PDF-to-series scientific extraction path works.

## 3. Required outcome

Deliver an independently usable Skill that can process thousands of existing chem-literature paper outputs incrementally, with bounded memory, reproducible results, and traceable scientific data.

### 3.1 Corpus input contract and upstream adapter

Implement a read-only upstream adapter.

For every paper, the adapter must:

1. Detect the paper directory and paper identifier.
2. Detect available upstream artifacts.
3. Identify relevant manifests, evidence indexes, figure inventories, tables, captions, page references, images, and text files.
4. Determine the available upstream version or artifact schema where possible.
5. Record missing, incomplete, duplicated, or corrupted inputs.
6. Generate a per-paper input snapshot.
7. Produce a stable fingerprint for downstream processing.

The snapshot must include:

- Paper ID.
- Upstream source identifier.
- Detected upstream version.
- Relative input paths.
- File roles.
- File sizes.
- Modification times.
- SHA256 hashes.
- Adapter version.
- Snapshot generation time.
- Missing or invalid artifacts.

File paths inside generated artifacts must use relative POSIX paths, even when the local runtime is Windows.

Content hashes are the authoritative input identity. File size and modification time may support fast change detection but must not silently replace content verification where correctness requires it.

Incomplete or damaged papers must be isolated and reported. They must not interrupt the complete corpus.

The adapter must never modify, move, rename, or delete upstream files.

### 3.2 Streaming extraction and paper-level context

The processing architecture must distinguish two fundamentally different resource categories.

**A. Heavy visual resources**

These include:

- PDF page objects.
- Rendered page images.
- Figure and panel crops.
- Full-resolution images.
- Vector path collections.
- Pixel-level image-processing buffers.
- Large numerical point collections.

These resources must be read and processed on demand. They must never be accumulated across the entire paper or corpus.

The normal sequence is:

Open PDF → Inspect one page → Identify required region → Render or extract evidence → Process current figure/panel → Persist results → Release resources → Continue

The implementation should use context managers, explicit close operations, and bounded buffers.

Avoid keeping multiple high-resolution page images open simultaneously in the default one-worker mode.

**B. Lightweight paper-level text context**

Scientific information is often distributed across different pages and across the MAIN/SI documents.

For example:

- A figure legend identifies a sample as Sample A.
- The chemical formula defining Sample A appears in the experimental section.
- The reference electrode appears in a separate electrochemical testing section.
- The error-bar definition appears in the SI.
- A table contains additional conditions for the same specimen.

Strictly limiting semantic interpretation to the current PDF page would break these relationships.

Therefore, the worker may build or load a compact paper-level context index before extracting figure semantics.

The index may be constructed from existing upstream outputs such as:

- main_analysis.md
- si_analysis.md
- extracted_tables/
- Existing evidence and text indexes.

This must not require rendering all PDF pages or reprocessing all original literature.

The context index should contain compact, searchable information such as:

- Sample names and aliases.
- Chemical formulas and material labels.
- Subject/entity candidates.
- Experimental-condition statements.
- Reference-electrode descriptions.
- Electrolyte and measurement conditions.
- Statistical and error-bar definitions.
- Analyte names and abbreviations.
- Product names.
- Relevant textual evidence snippets.
- Source file, line, page, table, or evidence references.

**Context-index memory rule**

- Aim for a compact in-memory index with a default serialized size budget of approximately 500 KB per paper.
- This is a target budget, not a universal hard limit on valid input files.
- Build the index by streaming through text artifacts rather than loading every source artifact indiscriminately.
- If the compact index exceeds the configured budget, retain a smaller in-memory lookup structure and use a disk-backed index for less frequently accessed information.
- Do not discard relevant source evidence just to meet an arbitrary byte limit.

The context index must have its own fingerprint and version. It should be cached and reused when its source artifacts remain unchanged.

Each lookup result must retain the provenance of the source text. A sample alias found in main_analysis.md must be traceable to the relevant source location rather than becoming an unsupported global fact.

Figure and panel processing should query this paper-level context index for cross-page evidence. It must not preload all page images to obtain that information.

### 3.3 Figure and Panel inventory

Implement the hierarchy:

Paper → Figure → Panel → Series

Each object must have stable identifiers within its paper.

Store:

- Figure ID.
- Panel ID.
- Source PDF.
- Page number.
- Original bounding box.
- Normalized coordinates.
- Panel label.
- Caption.
- Figure-level shared legends.
- Panel-specific legends.
- Detection source.
- Segmentation algorithm version.
- Confidence or review state.

Figure-level shared legends must be stored independently and inherited by relevant panels where supported by evidence.

Panel segmentation must not erase shared-legend information.

### 3.4 Hybrid PDF evidence extraction

PDF-native text and geometric evidence must be separated from internal curve extraction.

The system should retrieve, where available:

- Text objects.
- Text coordinates.
- Font and text metadata.
- Vector paths.
- Axis lines.
- Tick marks.
- Clipping boundaries.
- Embedded image locations.
- Legend text.
- Page dimensions.
- Page rotation.
- Transformation matrices.
- Form XObject nesting information.

The extraction of axes and labels must be independent from the extraction of plotted curves.

Examples of required hybrid handling:

- Native PDF axes and labels with a rasterized curve.
- Native vector axes with multiple embedded image panels.
- Native legends and rasterized data lines.
- Vector plot borders combined with raster spectra.
- PDF text converted to path outlines.

The system must not classify a figure as wholly vector or wholly raster merely because one type of object is present.

### 3.5 Preliminary chart classification and extraction routing

Use inexpensive evidence first:

- Caption.
- Body references.
- Native axis text.
- Units.
- Legend text.
- OCR where required.
- Geometry and plot layout.

Generate a preliminary chart family classification, not an irreversible final classification.

The chart family may be refined after axis and curve evidence becomes available.

Avoid circular dependencies between classification and extraction.

### 3.6 Numerical data reconstruction

Reconstruct data points from supported plot regions.

Every extracted series must preserve:

- Original pixel coordinates.
- Plot coordinates.
- Axis calibration anchors.
- Calibrated numerical coordinates where available.
- Original units.
- Normalized units where valid.
- Point order.
- Original series label.
- Extraction method.
- Algorithm version.
- QC information.
- Evidence references.

For relative or arbitrary signal axes, retain pixel coordinates and relative signal representations. Do not invent absolute intensity units.

For CV and EIS, preserve the original traversal sequence and non-monotonic paths. Do not sort data points by X.

### 3.7 Scientific data model

Implement a reusable model containing at least:

- Paper
- Figure
- Panel
- SubjectEntity
- EntityRelationship
- Condition
- Measurement
- Series
- SeriesSubjectLink
- DataObservation
- EvidenceItem
- DigitizationRun
- Review records.
- QC records.

**SubjectEntity**

Represents scientific research subjects such as materials, specimens, electrodes, catalysts, analytes, detected products, background matrices, reactors, and other extensible entity roles.

**EntityRelationship**

Represents relationships between subject entities, such as precursor, composite component, derived material, parent compound, reaction product, or other supported relationships.

**Condition**

Represents experimental conditions independently from the research subject.

Examples include temperature, pH, electrolyte, concentration, current density, potential window, reaction time, catalyst dosage, and gas atmosphere.

Each condition must retain its value, unit, and source evidence where available.

**Measurement**

Represents the experimental or analytical event.

**Series**

Represents a digitized graphical result, including continuous curves, spectra, scatter series, bar series, and other supported plotted sequences.

**DataObservation**

Represents scalar values reported in text or tables, or explicitly calculated summaries derived from existing data.

Do not confuse a scalar value from a table with points digitized from a curve.

**SeriesSubjectLink**

A series-level association between the plotted result and one or more subject entities.

Required fields include:

- series_id
- entity_id
- role_in_series
- evidence_id
- Link status.
- Confidence or evidence-strength fields where appropriate.

Example roles include:

- tested_material
- electrode
- catalyst
- target_analyte
- detected_product
- background_matrix
- reactor

A single figure can contain curves belonging to different samples. Do not infer that all series in one figure share the same subject.

### 3.8 Domain profiles

Use inheritance-based profiles.

Initial profiles:

- Battery / energy storage.
- AOP.
- PFOA/PFAS.

The profile mechanism must allow future chemistry and materials domains to be added without redesigning the core processing engine.

Recommended configuration structure:

- profile.yaml: profile information, inheritance, condition schema.
- techniques.yaml: techniques, axes, units, metrics, QC rules.
- analytes.yaml: optional analyte/species registry.

Shared definitions should be inherited instead of copied into every profile.

### 3.9 P0/P1/P2 extraction boundaries

**P0 — Core extraction**

Prioritize:

- One-dimensional continuous curves.
- CV and EIS non-monotonic paths.
- XRD.
- Raman and FTIR.
- Supported XPS styles.
- GCD and battery performance curves.
- AOP degradation and concentration-time curves.
- PFAS parent-compound concentration curves.
- F⁻ release curves.

For raster-based P0 extraction, the initial automated scope is deliberately conservative:

- Color-distinguishable continuous curves.
- Spatially separable stacked spectra.
- High-contrast single-curve trajectories.
- Clearly separated plotted lines with sufficient image quality.

The following must not be treated as guaranteed P0 automatic-extraction capabilities:

- Dense curves using the same or nearly identical color.
- Multiple overlapping grayscale curves.
- Curves that can only be distinguished by complex marker shapes.
- Dense intersections.
- Ambiguous dashed/dotted line patterns.
- Curves whose identity requires uncertain marker-to-legend inference.

When such cases are ambiguous, preserve source evidence and route them to NEEDS_REVIEW.

This is a deliberate scientific-integrity boundary, not an extraction failure that must be hidden.

**P1 — Expanded chart recognition**

Add marker shape recognition, dashed and dotted line classification, improved same-color curve separation, more complex curve crossing resolution, bar charts, scatter charts, error bars, more advanced tables, and additional statistical and domain-specific QC.

**P2 — Specialized visual data**

Evaluate full heatmap matrix reconstruction, advanced LC-MS/MS spectrum reconstruction, complex nested tables, other specialized multidimensional visualizations, and deep microscopy image quantification.

For P2 heatmaps, the initial capability may be limited to spatial calibration, colorbar interpretation, and source image preservation. Do not claim a complete reconstructed pixel matrix unless it has been independently validated.

### 3.10 Query, review, and ML export

The final system must provide three complete downstream consumption paths.

**A. Scientific query**

Users must be able to query data by:

- Paper ID.
- Subject entity.
- Entity alias.
- Technique.
- Domain.
- Analyte.
- Measurement type.
- Figure or panel.
- Series role.
- Other supported metadata and conditions.

Queries must be able to combine filters.

Examples:

- Find XRD and CV series for the same identified sample in one paper.
- Find all supported CV measurements for a given electrode material.
- Find PFOA parent-compound concentration curves from a selected set of conditions.
- Find GCD data whose capacity basis is gravimetric.
- Find series with unresolved reference-electrode conversion.

A query must preserve the difference between an exact entity identity, a possible alias match, and an unresolved relationship.

**B. Review patch application**

The offline review helper exports a review patch JSON.

The system must support importing and applying this patch through a controlled CLI operation.

Command: review apply --patch PATCH_PATH

The patch must contain at least:

- Patch ID.
- Paper ID.
- Target figure/panel/series IDs.
- Target artifact path.
- Schema version.
- Original result hash.
- Patch creation time.
- Reviewer identity where provided.
- Intended corrections.
- Reason or review note where provided.

Before applying the patch:

1. Validate the patch schema.
2. Validate the target paper and artifact.
3. Verify the current target artifact hash.
4. Verify the patch base version and identifiers.
5. Validate that proposed changes are within the permitted editable fields.
6. Check that the patch has not already been applied.

If the current result hash matches original_result_hash, apply the patch as a new versioned result. Preserve the original result and review history.

The accepted result must become REVIEWED_ACCEPTED, and the SQLite index must be updated through the single-writer mechanism.

If the hashes do not match, reject application and record PATCH_CONFLICT_STALE_BASE.

Do not silently overwrite the new result. Preserve the patch and produce a conflict report for manual resolution or re-review.

Patch application must be atomic from the perspective of the active indexed result. A failed patch must not leave half-written canonical data or an inconsistent index.

**C. ML-oriented export**

Export must support filters and compatibility policies.

An exported dataset must preserve:

- Original values.
- Original units.
- Standardized values where justified.
- Subject/entity information.
- Measurement conditions.
- Technique and data family.
- Reference scale.
- Source paper and figure.
- Evidence identifiers.
- QC and review state.
- Comparability warnings.
- Schema and algorithm versions.

The exporter must not silently merge incompatible measurements.

It must be possible to exclude unresolved or insufficiently reviewed observations from a particular ML export without deleting them from the underlying scientific database.

## 4. Scope

### In scope

**A. Independent Skill and upstream integration**

- Create an independent repository and Skill.
- Read-only chem-literature adapter.
- Version and layout detection.
- Corpus and paper manifests.
- Input fingerprints.
- Compact paper-level text context indexes.
- Detection of incomplete and damaged inputs.

**B. Streaming and resource management**

- Paper-by-paper processing.
- Page-by-page PDF inspection.
- On-demand region rendering.
- Lazy figure and panel iteration.
- Bounded point-data batches.
- Incremental persistence.
- Resource-aware scheduling.
- Backpressure at actual asynchronous boundaries.
- Temporary-file and cache limits.

**C. PDF and figure processing**

- PDF backend abstraction.
- Native text and coordinate extraction.
- Vector geometry extraction.
- Raster evidence extraction.
- Hybrid extraction.
- Figure and panel inventory.
- Panel segmentation.
- Shared legend handling.
- Preliminary chart classification.
- Axis calibration.

**D. P0 chart extraction**

- Supported continuous curves.
- Supported CV and EIS paths.
- Supported spectra.
- GCD and battery performance plots.
- AOP concentration-time plots.
- PFAS parent-removal and F⁻ release plots.
- P0 conservative raster routing and review fallback.

**E. P1/P2 capabilities**

- Advanced markers and line styles.
- More difficult curve separation.
- Tables.
- Bar and scatter plots.
- Error bars.
- Advanced multidimensional figures.
- Specialized mass-spectrometry and microscopy extraction.

**F. Scientific data structures**

- Subject entities.
- Conditions.
- Measurements.
- Series.
- Scalar observations.
- Series-level subject relationships.
- Evidence and provenance.

**G. Scientific interpretation constraints**

- Battery capacity basis and measurement scope.
- AOP kinetics and mineralization distinctions.
- PFAS parent-removal, defluorination, and mineralization distinctions.
- Reference-electrode handling.
- Unit handling.
- Dual-axis assignment.
- Cross-page and MAIN/SI semantic association.

**H. QC and review**

- Multi-dimensional QC.
- Provisional thresholds.
- Calibrated thresholds.
- Offline review helper.
- Review patch export and application.
- Stale-base conflict handling.
- Reviewed-result immutability.

**I. Persistence and consumption**

- Panel-level merged CSV.
- Paper-level JSON artifacts.
- Versioned paper bundles.
- SQLite global query index.
- Rebuild capability.
- CLI query.
- CLI export.
- ML-oriented output with comparability metadata.

**J. Windows-first operation**

- Windows 10/11.
- Windows spawn compatibility.
- One-worker default.
- Native-thread limits.
- Resource monitoring.
- Worker crash isolation and recovery.
- Low-memory degraded mode.
- Unicode and long-path testing.

### Out of scope

- Modifying or redesigning chem-literature.
- Replacing upstream text and table extraction.
- A general autonomous literature-review agent.
- Autonomous scientific conclusion generation unsupported by evidence.
- Automatic publication or manuscript writing.
- Mandatory GPU processing.
- Mandatory parallel execution.
- Cloud processing or external upload of user papers and data.
- Mandatory use of LLMs.
- Paid model APIs.
- Universal automatic extraction of every figure style.
- Guaranteed zero-human-review processing.
- Automatic guessing of uncertain sample identities or experimental conditions.
- Automatic conversion across unresolved reference-electrode scales.
- Forced mapping of complex tables into an incorrect schema.
- Mandatory complete P1/P2 implementation before P0 can be accepted.
- Deleting source files or accepted review results.
- Replacing real-paper acceptance with synthetic tests.

## 5. Architecture / constraints

### Runtime(s)

- Python.
- Windows 10/11.
- Local command-line execution.
- Local filesystem.
- SQLite.
- JSON/JSONL and CSV canonical artifacts.
- Offline HTML review helper.
- Optional localhost-only review server.

All serialized internal paths must be relative POSIX paths. Local filesystem access must use pathlib.

### Hardware and resource constraints

**Baseline acceptance hardware**

- 8 GB RAM.
- 4 logical CPU cores.
- No dedicated GPU.

The default settings must be practical on this configuration.

This is a target engineering configuration, not a guarantee that every pathological or damaged PDF can be processed without memory or native-library failure.

The design must reduce such risks and recover safely when they occur.

**Default settings**

- workers = 1.
- Sequential paper processing.
- One active PDF per worker.
- On-demand PDF page loading.
- On-demand image rendering.
- One active heavy figure/panel extraction operation by default.
- Bounded point batches.
- Small bounded caches.
- No requirement to execute all stages concurrently.
- OCR disabled until required or explicitly enabled by the selected profile/configuration.

**Degraded mode**

For computers with less than the baseline memory or under memory pressure:

- Retain one worker.
- Reduce rendering DPI.
- Reduce image dimensions where scientifically acceptable.
- Lower image cache limits.
- Reduce point batch size.
- Disable optional OCR.
- Disable nonessential parallel operations.
- Use more frequent checkpoints.
- Process large papers one figure at a time.
- Use disk-backed indexes for larger context data.

A lower-specification computer should be able to process supported papers more slowly rather than being rejected solely because it lacks a high-end CPU or GPU.

### Streaming and flow-control semantics

The terms streaming, bounded queue, and backpressure must have precise implementation meanings.

**A. Within a single-paper worker**

The default one-worker processing path must use:

- Lazy iterators.
- Generators.
- On-demand page access.
- On-demand image rendering.
- Figure/panel-at-a-time processing.
- Bounded point batches.
- Immediate persistence of completed stage results.
- Explicit resource release.

When workers = 1, stage execution may be a synchronous function/generator chain.

Do not introduce unnecessary background threads, multiprocessing queues, image-frame queues, or serialization copies merely to satisfy a generic bounded-queue requirement.

Synchronous generator pull is the default flow-control mechanism inside the one-worker pipeline.

**B. Between the scheduler and multiple workers**

When workers > 1, use a bounded paper-job dispatch queue.

The queue must:

- Have a configurable maximum capacity.
- Avoid dispatching unlimited papers.
- Apply backpressure when workers cannot keep up.
- Pass paper IDs and immutable input references rather than large in-memory images.

**C. Between workers and the SQLite single writer**

Workers must not directly write concurrently to SQLite.

They should write paper-level canonical artifacts and submit small result descriptors or bounded messages to a single writer.

If messages are used, the result submission channel must have a configurable bounded capacity.

Large image arrays and point collections must not be copied through multiprocessing messages. Persist them to canonical artifacts and send paths, hashes, and compact metadata instead.

When one worker is used, a synchronous result handoff is acceptable; an artificial asynchronous queue is not required.

**D. Backpressure behavior**

Backpressure is required at asynchronous producer/consumer boundaries, not as a requirement to make every internal function asynchronous.

The system must stop dispatching new jobs or reduce intake when:

- Workers are busy.
- The result writer is behind.
- Memory pressure reaches a configured threshold.
- Temporary disk usage reaches a configured threshold.
- A downstream processing stage cannot consume new results safely.

### Scheduler and worker architecture

Separate global corpus scheduling from paper-level processing.

**Global scheduler responsibilities**

- Incremental paper discovery.
- Input snapshot validation.
- Job creation and status tracking.
- Resource-aware dispatch.
- Lease and heartbeat management.
- Failure classification.
- Worker supervision.
- Result registration.
- Single-writer SQLite updates.
- Corpus-level reporting.

**Paper worker responsibilities**

- Read one immutable input snapshot.
- Build or load the paper-level text context index.
- Process pages, figures, and panels incrementally.
- Persist canonical paper-level artifacts.
- Return compact result descriptors.
- Release large PDF/image resources after each task.

The default architecture should use one isolated worker process supervised by the scheduler. This allows the scheduler to recover when a native PDF or image library crashes the worker process.

Do not require a large worker pool for the default configuration.

**Native-library configuration**

Configure native thread pools conservatively:

- OMP_NUM_THREADS=1
- OPENBLAS_NUM_THREADS=1
- MKL_NUM_THREADS=1
- cv2.setNumThreads(1) where applicable.
- ONNX Runtime intra-op thread limits configured conservatively.

OCR models should be lazily loaded and reused within a worker lifetime.

Worker lifetime limits may be configurable to control memory growth.

**Crash recovery**

- Catch and report worker termination.
- Recover from BrokenProcessPool where multiprocessing is enabled.
- Recreate the worker.
- Preserve completed paper artifacts.
- Restart only the interrupted or invalidated stages.
- Isolate repeatedly failing PDFs.
- Record worker crash details and paper IDs.

Do not claim that process isolation makes all native-library crashes impossible.

### Job states, leases, and recovery

Paper jobs must support:

- PENDING
- RUNNING
- RETRY_WAIT
- COMPLETED
- COMPLETED_WITH_REVIEW
- NEEDS_REVIEW
- BLOCKED
- FAILED_PERMANENT

A running job must record:

- Worker identity.
- Start time.
- Last heartbeat.
- Lease expiration.
- Attempt count.
- Current stage.
- Relevant input fingerprint.

On restart:

1. Identify expired or orphaned jobs.
2. Record INTERRUPTED_RECOVERY.
3. Preserve valid completed stage outputs.
4. Return recoverable jobs to PENDING or RETRY_WAIT.
5. Prevent endless retry loops.
6. Preserve the complete task event history.

Distinguish transient, permanent, resource-related, unsupported-input, and scientific-ambiguity failures.

### Corpus manifest and stage fingerprints

Use a corpus-level manifest and per-paper snapshots.

Each paper snapshot should record:

- Paper ID.
- Upstream source and detected version.
- Relative paths.
- Artifact roles.
- Sizes and modification times.
- SHA256 hashes.
- Adapter version.
- Snapshot generation time.
- Missing or invalid artifacts.

Stage cache keys must include the relevant combination of:

- PDF SHA256.
- Relevant upstream artifact fingerprints.
- Paper context-index fingerprint.
- Adapter version.
- Stage implementation version.
- Algorithm version.
- Profile version.
- Parameters and configuration that affect the output.

A changed paper-context artifact must invalidate semantic association stages that depend on it, but must not automatically invalidate unrelated image rendering or curve geometry stages.

A changed PDF must invalidate dependent visual and semantic stages as appropriate.

Unchanged inputs and algorithms must reuse valid completed results.

### PDF backend technical spike

Do not commit to a single PDF library before the backend spike.

Compare a suitable combination of:

- pypdfium2 high-level rendering and inspection.
- pypdfium2.raw for direct PDFium C API access.
- pdfminer.six for text and layout extraction.
- pikepdf / QPDF for PDF object and content-stream inspection.
- Other libraries only where a measured gap justifies them.
- PyMuPDF only if its functionality is necessary and its AGPL-3.0/commercial licensing implications are acceptable.

The spike must distinguish the capabilities of rendering, text extraction, object traversal, and full vector-path extraction.

Do not assume that:

- pypdfium2 high-level APIs expose every required object.
- Every raw PDFium function is stable or available in every bundled build.
- pikepdf content-stream access automatically solves vector geometry reconstruction.
- pdfminer.six text/layout extraction is equivalent to complete graphical-path access.
- Any one backend can solve all PDF extraction requirements.

The spike must explicitly evaluate PDFium's raw page-object and path-segment APIs, including the behavior and stability of relevant functions, nested Form XObjects, object ownership, and transformation handling.

**Performance measurement**

For each candidate backend and representative PDF, record:

- Per-page wall-clock time.
- Full-paper processing time.
- Peak resident memory (Peak RSS).
- Number of page objects inspected.
- Number of path segments inspected where applicable.
- Text extraction coverage.
- Vector-path coverage.
- Embedded image coverage.
- Clipping and transformation handling.
- Nested Form XObject handling.
- Failure and unsupported-case behavior.

Do not treat anecdotal measurements such as a fixed 15–40 second page time or a fixed 600 MB memory footprint as universal properties of a library. Use them as risks to investigate, not as predetermined benchmark results.

The benchmark must include dense-vector pages on the target 8 GB Windows environment.

### PDF and dependency licensing

Record:

- Package name and version.
- Direct and transitive dependencies.
- License identifier.
- Binary-distribution requirements.
- Bundled native libraries.
- OCR engine license.
- OCR model-weight terms.
- Any additional notices required for redistribution.

The presence of an open-source license does not automatically establish that every bundled binary and dependency has identical license terms.

Do not ship an unreviewed PDF backend or OCR model merely because it can be installed through pip.

### Chart extraction algorithms

**VectorExtractor**

Must evaluate:

- Page-object traversal.
- Path segments.
- Text-as-path filtering.
- Path fragmentation.
- Clipping.
- Page rotation.
- Coordinate transformations.
- Form XObject nesting.
- Stroke and fill distinctions.
- Dash patterns.
- Small markers and peaks.
- Path endpoint joining.

All heuristic thresholds must be configurable and validated against representative PDFs.

Do not hardcode universal path-fragment length, font-size, or endpoint distance rules.

**RasterExtractor**

P0 automated support prioritizes:

- Color-distinguishable continuous curves.
- Spatially separable stacked spectra.
- High-contrast single-curve trajectories.

P0 must not promise universal separation of same-color overlapping curves, complex markers, dashed-line families, or dense crossings.

When ambiguity is detected, preserve the geometry and source image, record the ambiguity, and route to NEEDS_REVIEW.

P1 may improve marker-shape classification, dashed and dotted line recognition, same-color line separation, complex crossings, multi-series tracking, and legend association.

**CV/EIS extraction**

Do not rely on simple column-by-column X scanning.

Use appropriate methods such as skeletonization, graph-based tracing, path continuity, tangent and curvature constraints, and branch and loop detection.

Preserve original traversal order, loops, branch points, and turning points.

**Spectra extraction**

- XRD stacked spectra may use horizontal projection and layer separation when the visual layout supports it.
- Raman and FTIR sloping or curved baselines require local ridge and slope-continuity tracking.
- XPS Shirley/Tougaard-like background behavior must not be handled by blindly applying horizontal projection.
- Ambiguous or crossing spectra must be routed for review rather than forced into a single path.

### Panel segmentation and legends

- Store figure-level shared legends independently.
- Support inheritance by applicable panels.
- Preserve the evidence supporting legend inheritance.
- Store panel-specific legend information separately.
- Do not infer that a legend is irrelevant merely because it falls outside a cropped panel.

### Axis calibration

Support numeric linear axes, categorical axes, relative signal axes, multiple axes, independent calibration by panel or axis group, and calibrated plot regions with source pixel coordinates.

For numeric axes, require sufficient numeric anchors. A simple linear axis generally requires at least two suitable anchors.

Record anchors, transformations, units, residuals, and source evidence.

### Relative signal intensity

Support distinct modes such as:

- CALIBRATED_NUMERIC
- ARBITRARY_RELATIVE
- SERIES_RELATIVE_SIGNAL

For a relative signal axis:

- Preserve original pixel coordinates.
- Preserve relative signal values.
- Record normalization methods if applied.
- Do not assign absolute intensity units.
- Do not suggest unsupported cross-paper absolute comparability.

### Dual Y axes

Each series must support LEFT, RIGHT, or UNASSIGNED.

Candidate evidence includes axis label color, tick-label color, curve color, legend semantics, axis titles, metric units, and textual descriptions.

An inconclusive assignment remains UNASSIGNED and can enter review.

Do not discard an otherwise useful curve merely because its axis side is unresolved.

### Scientific units and reference-electrode conversion

**General units**

Keep dimensional conversion separate from reference-scale conversion.

Preserve original values and units.

Perform deterministic conversions only when the dimensions and relevant assumptions are explicit.

**Reference electrode fields**

Store, where available:

- Reference electrode label.
- Reference electrode type.
- Filling solution.
- Filling-solution concentration.
- Electrolyte.
- Temperature.
- pH.
- Original potential scale.
- Original potential value and unit.
- Conversion formula.
- Conversion constants.
- Conversion source and evidence.
- Normalized result, only when sufficiently supported.

Labels such as RHE, SHE, SCE, Ag/AgCl, Li/Li+, Na/Na+, and Zn/Zn2+ are not sufficient on their own to establish a valid conversion.

If required conditions are missing:

- Preserve the original value and scale.
- Leave the normalized scale unresolved.
- Mark REFERENCE_CONVERSION_UNRESOLVED.
- Do not apply a guessed fixed offset.

Never merge unresolved potential scales as if they were identical.

### Domain-specific scientific constraints

**Battery**

Do not mix gravimetric capacity, areal capacity, volumetric capacity, positive-electrode capacity, negative-electrode capacity, full-cell capacity, half-cell measurements, different current-density or rate conventions, or different cycling conditions.

**AOP**

Keep distinct parent pollutant concentration, removal efficiency, degradation rate, kinetic rate constant, TOC, COD, radical and active-species evidence, and mineralization.

**PFOA/PFAS**

Keep distinct parent-compound removal, defluorination, mineralization, F⁻ release, total fluorine, organic fluorine, short-chain products, LC-MS/MS evidence, and fluorine mass balance.

<LOD and <LOQ must retain the original comparator and limit information. Never convert them to zero.

### QC and confidence

Do not use one confidence score as a substitute for individual extraction quality dimensions.

Record independent states or confidence measures for:

- Panel segmentation.
- Chart-family classification.
- Axis detection.
- Axis calibration.
- Series extraction.
- Point reconstruction.
- Legend association.
- Subject linking.
- Condition interpretation.
- Unit interpretation.
- Reference-scale conversion.

Possible QC checks include anchor residuals, overlay and reprojection agreement, curve pixel coverage, path continuity, point density, curve separation, axis range plausibility, monotonic and non-monotonic path constraints, error-bar detection consistency, legend association evidence, entity-link evidence, and domain-specific scientific constraints.

Chamfer distance alone is insufficient.

**Two-stage QC threshold policy**

Provide two separate versioned configuration files:

1. qc_thresholds_provisional.yaml
2. qc_thresholds_calibrated.yaml

qc_thresholds_provisional.yaml:

- Used during initial implementation, integration tests, and early pilot processing.
- Contains documented engineering defaults.
- Allows the pipeline to run before a complete real-paper benchmark is available.
- Every resulting QC report must explicitly carry PROVISIONAL_UNCALIBRATED.
- Must not be presented as scientifically validated acceptance thresholds.

qc_thresholds_calibrated.yaml:

- Generated or approved only after validation against manually annotated real-paper figures.
- Records benchmark dataset identity and version.
- Records annotation version and calibration procedure.
- Records algorithm and profile versions for which thresholds were assessed.
- Must not silently overwrite provisional or previous calibrated configurations.

Until calibrated thresholds are available, functional development may proceed using provisional thresholds, but the system must not claim final scientific accuracy or calibrated production QC.

### Canonical storage and paper bundles

Use three complementary storage layers.

**A. Canonical paper-level artifacts**

Example structure:

- paper_manifest.json
- figure_inventory.json
- panel_layout.json
- digitization.json
- panel_series.csv
- evidence/
- Review records.
- Version records.
- Other required paper-level metadata.

Each panel_series.csv can contain multiple series distinguished by series_id.

Keep calibration, extraction metadata, QC, and provenance in associated JSON metadata.

Avoid generating a tiny file for each curve or individual point when a merged panel-level file can preserve the same traceability.

Do not delete necessary original crops or non-regenerable evidence merely to reduce the file count.

**B. Paper bundle snapshot**

paper_bundle.json is a portable, rebuildable snapshot.

It must include schema_version, bundle_version, generated_at, paper_id, input_fingerprint, adapter version, algorithm versions, profile versions, canonical artifact references, content hashes, completion state, and review state.

It is not the only authoritative data store.

**C. Global SQLite index**

SQLite provides query support, entity relationships, technique and domain filtering, series-level subject lookup, status and review lookup, export selection, and corpus-level statistics.

Use a single writer.

Workers do not directly write concurrently to the shared SQLite database.

The index must be rebuildable from paper bundles and canonical artifacts.

When a bundle is missing or corrupted, rebuild from canonical paper-level artifacts where possible.

Do not rely on a routine full scan of hundreds of thousands of individual data files.

**Format strategy**

- JSON/JSONL for manifests, events, metadata, and provenance.
- CSV for merged panel-level point data.
- SQLite for queries and relationships.
- Parquet only when actual corpus size and downstream usage justify it.

Do not make Parquet a mandatory MVP dependency.

### Idempotency and result versioning

Every digitization run must have a unique DigitizationRun identity.

The result identity must be reproducible from the relevant input fingerprint, context-index fingerprint, algorithm version, profile version, configuration, and calibration evidence.

Unchanged stages must reuse valid cached outputs.

Accepted human-review results must be protected.

By default:

- run --all does not overwrite REVIEWED_ACCEPTED.
- Changes to algorithms or profiles create new result versions when recomputation is requested.
- Previous accepted versions remain available.
- Recalculation does not silently replace the active reviewed result.

Provide force-recompute-reviewed.

This operation must create a new DigitizationRun version and preserve the previous version for comparison or rollback.

### Review helper and patch application

The review helper is a lightweight offline interface, not a full desktop application.

The preferred MVP is a static HTML helper supporting folder selection, folder drag-and-drop, browser local-file reading, and review patch JSON export.

It must not depend on file:// fetch access to neighboring JSON files.

The review interface should display source figure and panel, panel boundaries, extracted curve overlay, axis calibration anchors, series labels, legend assignments, dual-axis assignments, QC warnings, and unresolved scientific relationships.

Provide an optional local review server only when controlled local saving is required.

The local server must bind only to 127.0.0.1 and must not expose a LAN-accessible service.

**Review patch application**

CLI: review apply --patch PATCH_PATH

Optional safety operation: review apply --patch PATCH_PATH --dry-run

Required behavior:

1. Validate schema and permitted change types.
2. Check paper, panel, and series identifiers.
3. Verify original_result_hash.
4. Detect duplicate patch application.
5. Reject stale-base patches with PATCH_CONFLICT_STALE_BASE.
6. Preserve rejected patches and produce a conflict report.
7. For a valid patch, create a new reviewed result version.
8. Preserve the original digitization result.
9. Mark the active reviewed result REVIEWED_ACCEPTED.
10. Update SQLite through its single writer.
11. Record reviewer, time, original hash, revised hash, and patch ID.
12. Ensure the artifact and index update are consistent.

Do not apply arbitrary filesystem operations or unrestricted JSON modifications from untrusted review patch files.

### Required CLI

The CLI must provide equivalent functionality to the following commands. Names may be adjusted if the behavior remains explicit and testable.

**Input and processing**

- scan
- run --all
- run --resume
- run --failed-only
- run --paper-id
- run --dry-run

**Monitoring**

- status
- report
- validate

**Scientific query and export**

- query
- export

query must support filters including paper ID, entity, entity ID, technique, domain, analyte, series role, relevant conditions, and QC/review states.

Multiple filters must be combinable.

The implementation must distinguish exact entity identity, alias search results, and unresolved matches.

export must support equivalent domain, entity, technique, paper, QC, and review filters.

It must include a manifest that records the export schema, input selection, compatibility constraints, and provenance requirements.

**Review**

- review
- review apply --patch PATCH_PATH
- review apply --patch PATCH_PATH --dry-run

**Catalog**

- index rebuild

**Resource controls**

Provide configurable equivalents of workers, memory limit, maximum open PDFs, render DPI, OCR, cache limit, temporary disk limit, and batch size.

The default configuration must remain one-worker and low-resource.

### Security / permission constraints

- Treat PDFs, images, extracted text, metadata, and review patches as untrusted data.
- Do not execute embedded PDF scripts, attachments, or executable content.
- Keep the upstream directory read-only.
- Do not upload research papers or extracted data to external services.
- Keep review services bound to 127.0.0.1.
- Do not expose local review services to the LAN.
- Maintain dependency and license records.
- Do not perform hidden network access.
- Do not invoke hidden or unauthorized LLM calls.
- Do not silently overwrite canonical or accepted data.
- Do not delete original PDFs or upstream artifacts.
- Clean temporary files only through explicit retention rules.
- Use parameterized database queries.
- Validate review patches against a strict schema and allowed field operations.

### Other non-negotiable rules

1. The independent Skill must not modify the upstream Skill.
2. Default worker count must be one.
3. Heavy visual resources must be processed on demand.
4. Paper-level scientific text context may span pages and MAIN/SI documents.
5. Large context inputs must use streaming construction and disk-backed lookup when necessary.
6. Single-worker synchronous flow must not be burdened with unnecessary queues.
7. Bounded queues and backpressure apply at actual asynchronous boundaries.
8. Workers must not concurrently write to SQLite.
9. OCR must be lazy-loaded and reused.
10. No high-end GPU or workstation is required for normal P0 operation.
11. Same-color or complex ambiguous raster curves may be routed to review.
12. Uncertain dual-axis assignments must remain UNASSIGNED.
13. Unresolved reference-electrode conversion must not use guessed offsets.
14. Original numerical values and units must always be retained.
15. Battery, AOP, and PFAS semantics must remain distinct.
16. <LOD and <LOQ must never become zero.
17. Accepted review results must not be silently overwritten.
18. Review patches must be checked against their base hash.
19. Provisional QC results must not be described as calibrated.
20. Scientific accuracy claims require real annotated paper evidence.
21. P1/P2 scope must not block the P0 milestone.
22. The Task Plan is the user's objective and constraint document; progress belongs in STATUS.md.

## 6. Acceptance criteria

### Stage labels and acceptance policy

Each acceptance criterion is assigned a development stage.

- [P0]: Required for the first usable core extraction workflow.
- [P1]: Required for the subsequent expanded chart and data-mapping milestone.
- [P2]: Specialized capabilities and later-stage development.
- [Release]: Additional evidence required before claiming the corresponding release boundary.

A criterion may have more than one label, for example [P0][Release].

P1 and P2 criteria must not be treated as blockers to P0 functional acceptance unless the user explicitly changes the scope.

A P0 feature may be functionally implemented while remaining scientifically provisional. Functional completion is not the same as calibrated scientific acceptance.

### A. Independent project and upstream compatibility

- [ ] AC-01 [P0]: A standalone repository Tuzhidingdong/scientific-figure-data exists with an independently usable Skill entry point.
- [ ] AC-02 [P0]: The new Skill runs without requiring changes to chem-literature.
- [ ] AC-03 [P0]: The adapter can detect and consume supported upstream artifact layouts and version differences.
- [ ] AC-04 [P0]: Every processed paper has an input snapshot with relative paths, file roles, metadata, SHA256 fingerprints, and detected upstream version information.
- [ ] AC-05 [P0]: Missing, incomplete, or corrupted upstream artifacts isolate the affected paper without stopping the complete corpus.
- [ ] AC-06 [P0][Release]: Tests confirm that upstream paths, directory structure, and source-file hashes remain unchanged.

### B. Streaming and low-resource execution

- [ ] AC-07 [P0]: Corpus discovery is incremental and does not require loading the complete corpus into memory.
- [ ] AC-08 [P0]: PDF pages are inspected and rendered on demand; all pages are not rendered or retained simultaneously.
- [ ] AC-09 [P0]: Figures, panels, and series are processed in bounded units and completed stages are persisted incrementally.
- [ ] AC-10 [P0]: Lazy iteration provides synchronous flow control inside the default single-worker pipeline. Bounded queues and backpressure are implemented at asynchronous scheduler/worker and worker/writer boundaries when those boundaries are used. The system does not introduce unnecessary internal queues for workers=1.
- [ ] AC-11 [P0]: Default execution uses one worker and does not require GPU acceleration.
- [ ] AC-12 [P0]: OCR is loaded lazily and reused within a worker rather than reloaded for every paper or page.
- [ ] AC-13 [P0]: Native CPU thread pools are configured conservatively to prevent thread oversubscription.
- [ ] AC-14 [P0]: Memory, PDF count, image cache, point batch, and temporary disk limits are configurable.
- [ ] AC-15 [P0]: A low-resource mode supports sequential operation with reduced rendering resolution and optional OCR disabled.
- [ ] AC-16 [P0][Release]: Resource testing on the target ordinary Windows configuration records peak RSS, CPU behavior, temporary disk use, processing throughput, and failure recovery. The test must not depend on a high-memory workstation.
- [ ] AC-17 [P0]: Resource-pressure handling pauses or limits new work safely without corrupting existing results.

### C. Scheduler, resume, and failure recovery

- [ ] AC-18 [P0]: Global scheduling and paper-level processing are separate components.
- [ ] AC-19 [P0]: Workers do not concurrently write to the shared SQLite database.
- [ ] AC-20 [P0]: Jobs support all defined processing and review states.
- [ ] AC-21 [P0]: Running jobs have heartbeat and lease-expiration information.
- [ ] AC-22 [P0]: Restart recovery detects orphaned jobs and records INTERRUPTED_RECOVERY.
- [ ] AC-23 [P0]: Recoverable failures have finite retries; permanent failures do not enter an endless retry loop.
- [ ] AC-24 [P0]: Simulated worker crashes or BrokenProcessPool do not destroy completed results or stop all papers from processing.
- [ ] AC-25 [P0]: Resume reuses valid completed stages and does not repeat unaffected work.

### D. Figure and panel processing

- [ ] AC-26 [P0]: Figures and panels have stable identifiers and traceable source-page references.
- [ ] AC-27 [P0]: Panel boundaries preserve normalized coordinates, source coordinates, and detection provenance.
- [ ] AC-28 [P0]: Shared figure-level legends can be inherited by relevant panels.
- [ ] AC-29 [P0]: Panel-segmentation uncertainty is recorded separately from chart classification and extraction uncertainty.
- [ ] AC-30 [P0]: Preliminary chart classification can be revised as additional visual or textual evidence becomes available.

### E. PDF backend and hybrid extraction

- [ ] AC-31 [P0]: A technical spike using 3–5 representative PDFs compares candidate backends, including pypdfium2, its raw API, and relevant alternatives such as pdfminer.six and pikepdf/QPDF, on native text, coordinates, vector paths, embedded images, clipping, rotation, Form XObjects, text-as-path, and fragmented paths.
- [ ] AC-32 [P0]: The final backend combination is selected based on measured functionality, stability, licensing, performance, and memory behavior, not an assumed single-library solution.
- [ ] AC-33 [P0]: Native PDF text and axis evidence can be combined with raster curve extraction in the same figure.
- [ ] AC-34 [P0]: The presence of vector objects does not force the entire figure through a vector-only route.
- [ ] AC-35 [P0]: Raster curves do not cause native PDF axis, label, or legend evidence to be discarded.
- [ ] AC-36 [P0][Release]: The final PDF and OCR dependencies have documented versions, license identifiers, bundled-library notices, and model-weight distribution terms.

### F. P0 scientific extraction

- [ ] AC-37 [P0]: The P0 workflow can inventory, calibrate, extract, QC, and persist supported one-dimensional series.
- [ ] AC-38 [P0]: Supported CV extraction preserves original traversal order and does not sort data by X.
- [ ] AC-39 [P0]: Supported EIS extraction preserves non-monotonic and loop-shaped paths.
- [ ] AC-40 [P0]: Numeric calibration and arbitrary/relative signal axes are handled as distinct modes.
- [ ] AC-41 [P0]: Relative-intensity spectra are never falsely represented as absolute physical intensities.
- [ ] AC-42 [P0]: Supported XRD, Raman, FTIR, and XPS styles can be extracted or explicitly routed for review when unsupported.
- [ ] AC-43 [P0]: Supported GCD and battery performance plots produce traceable numerical series.
- [ ] AC-44 [P0]: Supported AOP and PFAS concentration-time figures produce traceable numerical series.
- [ ] AC-45 [P0]: Parent-compound degradation and F⁻ release are represented as distinct measurements.
- [ ] AC-46 [P0]: P0 raster automation remains within the defined low-ambiguity boundary. Ambiguous same-color crossings, marker-dependent distinctions, and dense overlapping curves are routed to NEEDS_REVIEW instead of being forced into automatic extraction.

### G. Data model and subject linkage

- [ ] AC-47 [P0]: The data model separates SubjectEntity, Condition, Measurement, Series, and DataObservation.
- [ ] AC-48 [P0]: Different series in the same figure can be independently linked to different subject entities.
- [ ] AC-49 [P0]: SeriesSubjectLink records subject role and evidence provenance.
- [ ] AC-50 [P0]: Uncertain sample identities and subject relationships remain UNASSIGNED or NEEDS_REVIEW.
- [ ] AC-51 [P1]: Table/text scalar observations remain distinguishable from figure-digitized point data.
- [ ] AC-52 [P0]: Queries can retrieve different techniques associated with the same paper and the same supported sample/entity.

### H. Domain profiles and semantic constraints

- [ ] AC-53 [P0]: Battery, AOP, and PFOA/PFAS profiles exist and inherit shared definitions.
- [ ] AC-54 [P0]: New domain profiles can be added through supported configuration-level extensions without redesigning the core engine.
- [ ] AC-55 [P0]: Battery capacity bases and positive-electrode, negative-electrode, half-cell, and full-cell measurement scopes are not silently mixed.
- [ ] AC-56 [P0]: AOP removal efficiency, pollutant concentration, degradation kinetics, TOC, and COD are distinct metrics.
- [ ] AC-57 [P0]: PFAS parent-compound removal, defluorination, mineralization, F⁻ release, and fluorine mass-balance measurements remain distinct.
- [ ] AC-58 [P0]: <LOD and <LOQ preserve their original comparator and detection/quantification limit. They are never converted to zero.
- [ ] AC-59 [P0]: Experimental conditions are stored separately from material and sample identity.

### I. Units, reference electrodes, and axes

- [ ] AC-60 [P0]: Original values and units are retained separately from standardized values.
- [ ] AC-61 [P0]: Dimensional conversion and reference-electrode conversion are separate operations.
- [ ] AC-62 [P0]: Reference-electrode conversion is not triggered by a reference label alone.
- [ ] AC-63 [P0]: When conversion conditions are incomplete, the original potential is retained and the normalized reference scale remains unresolved.
- [ ] AC-64 [P0]: Dual-axis series record LEFT, RIGHT, or UNASSIGNED.
- [ ] AC-65 [P0]: An unresolved axis-side assignment does not force valid curve geometry to be discarded.

### J. QC and evidence chain

- [ ] AC-66 [P0]: Every series records its source PDF fingerprint, figure, panel, page, extraction channel, algorithm version, and relevant source evidence.
- [ ] AC-67 [P0]: QC records separate panel, chart-family, calibration, extraction, subject-link, condition, and unit-interpretation states.
- [ ] AC-68 [P0][Release]: qc_thresholds_provisional.yaml and qc_thresholds_calibrated.yaml are separate, versioned configurations. Provisional results are explicitly marked PROVISIONAL_UNCALIBRATED; calibrated thresholds are tied to manually annotated real-paper benchmarks.
- [ ] AC-69 [P0]: QC includes relevant calibration, overlay, coverage, continuity, path, density, separation, and scientific checks rather than relying only on Chamfer distance.
- [ ] AC-70 [P0]: QC thresholds are measured against manually annotated real-paper figures before scientific accuracy claims are made.
- [ ] AC-71 [P0]: Unsupported or ambiguous results are preserved with explicit review states rather than silently discarded or assigned guessed values.

### K. Storage, indexing, and version governance

- [ ] AC-72 [P0]: Multiple series from one panel can be stored in a merged panel_series.csv, distinguished by series_id.
- [ ] AC-73 [P0]: Calibration, series metadata, provenance, and QC are stored in associated canonical metadata artifacts.
- [ ] AC-74 [P0]: paper_bundle.json records schema version, bundle version, input fingerprint, generation time, algorithms, profiles, and content hashes.
- [ ] AC-75 [P0]: SQLite is a rebuildable global query index with a single-writer architecture.
- [ ] AC-76 [P0]: The global index can be rebuilt from bundles and canonical artifacts without routinely scanning every individual point file.
- [ ] AC-77 [P0]: Unchanged inputs and unchanged algorithms reuse valid stage cache results.
- [ ] AC-78 [P0]: Accepted review results are not overwritten by default batch execution.
- [ ] AC-79 [P0]: Explicit reviewed-result recomputation creates a new run/version and preserves the previous accepted result.

### L. Review helper and patch application

- [ ] AC-80 [P0]: The offline review helper can load selected paper artifacts without relying on file:// fetch access to adjacent JSON files.
- [ ] AC-81 [P0]: Reviewers can inspect source crops, panel boundaries, curve overlays, axis anchors, series labels, and QC warnings.
- [ ] AC-82 [P0]: The reviewer can export a schema-validated review patch JSON containing the original result hash.
- [ ] AC-83 [P0]: Review patches retain reviewer information, timestamps, original hashes, revised content, and review history where available.
- [ ] AC-84 [P0]: Any local review server binds only to 127.0.0.1.
- [ ] AC-85 [P0]: Review operations never silently overwrite accepted results.
- [ ] AC-86 [P0]: review apply --patch PATCH_PATH verifies the patch schema, target identifiers, and original_result_hash; a matching patch creates a new REVIEWED_ACCEPTED version and updates SQLite through the single writer.
- [ ] AC-87 [P0]: A stale patch is rejected with PATCH_CONFLICT_STALE_BASE, preserved for inspection, and does not overwrite the current digitization result.
- [ ] AC-88 [P0]: Reapplying an already applied patch is detected and does not create duplicate corrections.

### M. CLI, scientific query, export, and reporting

- [ ] AC-89 [P0]: The CLI supports corpus scan, full run, resume, failed-only retry, paper-specific processing, dry-run, status, report, validation, review, and index rebuild.
- [ ] AC-90 [P0]: The CLI provides a functional query command supporting combined paper_id, entity/entity ID, technique, domain, analyte, series role, condition, QC, and review filters.
- [ ] AC-91 [P0]: The CLI provides a functional export command that selects data by query filters and generates a versioned export manifest with provenance and compatibility metadata.
- [ ] AC-92 [P0]: A user can query for multiple techniques associated with the same paper and supported sample/entity, such as XRD and CV for the same material.
- [ ] AC-93 [P0]: An ML export can retain original values, units, entity identity, conditions, provenance, QC/review status, and comparability warnings without silently merging incompatible measurements.
- [ ] AC-94 [P0][Release]: Corpus reports accurately include discovered papers, eligible papers, skipped papers, completed papers, review-required papers, permanently failed papers, retries, failure reasons, elapsed time, throughput, peak memory, temporary disk usage, and algorithm/profile versions.
- [ ] AC-95 [P0]: Default processing records zero LLM token usage.
- [ ] AC-96 [P0]: No paid model is invoked automatically or used as a fallback.
- [ ] AC-97 [P0]: Core extraction, persistence, query, and export remain usable when optional LLM functionality is disabled or unavailable.

### N. P1/P2 boundaries and release claims

- [ ] AC-98 [P0]: Documentation explicitly distinguishes validated P0 automatic extraction from P1 and P2 planned or experimental capabilities.
- [ ] AC-99 [P1]: P1 supports the documented expansion of tables, bar charts, scatter plots, error bars, marker classification, and more difficult curve separation.
- [ ] AC-100 [P1]: Complex tables can remain preserved with NEEDS_SCHEMA_MAPPING rather than being forced into incorrect automatic mappings.
- [ ] AC-101 [P2]: P2 heatmap, advanced LC-MS/MS, and specialized image reconstruction features are identified as experimental or deferred unless independently validated.
- [ ] AC-102 [Release]: A release or production-readiness claim is supported by real-paper benchmark results, target-Windows resource tests, dependency/license review, data integrity evidence, and documented limitations. Passing synthetic or unit tests alone is insufficient.

## 7. Tests / evidence

### Required tests

**A. Upstream adapter and input-contract tests**

Test:

- Different supported chem-literature artifact versions.
- Different paper directory layouts.
- Missing manifests.
- Missing figure indexes.
- Missing SI files.
- Missing extracted tables.
- Incomplete paper outputs.
- Corrupted artifacts.
- Duplicate paper identifiers.
- Unicode paths and unusual file names.
- Input fingerprint changes.
- Context-index fingerprint changes.

Verify that source directories remain unchanged, snapshot manifests are reproducible, missing inputs isolate only the affected paper, and changed inputs invalidate only dependent stages.

**B. Paper-level context-index tests**

Test cross-page and MAIN/SI semantic resolution.

Representative cases should include:

1. Figure legend contains Sample A; chemical formula appears in a separate main-text section.
2. Figure caption contains a sample alias; the full sample definition appears in an upstream text artifact.
3. CV figure lacks a reference-electrode detail; the testing section identifies the electrode.
4. Error bars are visible in a figure; the statistical definition appears in the SI.
5. A sample alias appears in multiple tables and narrative passages.
6. The same abbreviation has different meanings in different contexts.

Verify that the context index uses only available upstream outputs, source evidence references remain traceable, no PDF rendering is required solely to retrieve already extracted text, the index can be built incrementally, unchanged context is reused, larger-than-budget text artifacts use bounded or disk-backed lookup, and ambiguous aliases are not silently resolved.

**C. Streaming and memory tests**

Test incremental corpus enumeration, one-paper-at-a-time execution, lazy PDF page access, on-demand region rendering, figure/panel iteration, bounded point batches, explicit resource release, small cache behavior, temporary disk limits, queue backpressure at concurrent boundaries, and synchronous generator flow under workers=1.

Run on the target ordinary Windows configuration:

- Approximately 8 GB RAM.
- 4 logical CPU cores.
- No dedicated GPU.

Record peak RSS, per-paper peak memory, per-page processing time, figure rendering time, temporary disk usage, cache size, number of simultaneously open PDFs, CPU utilization, and processing throughput.

Also test a lower-memory degraded configuration with one worker and optional OCR disabled.

A resource test must not require a high-end workstation to succeed.

**D. Windows process and crash-recovery tests**

Test Windows spawn behavior, worker startup and shutdown, native library thread limits, OCR lazy initialization and reuse, worker process termination, BrokenProcessPool behavior if multiprocessing is enabled, lease expiration, INTERRUPTED_RECOVERY, finite retry policy, corrupted PDF isolation, recovery after native-library crashes, long paths, and Unicode paths.

Verify that completed paper artifacts remain valid after a crash.

**E. PDF backend technical spike**

Use 3–5 representative real PDFs.

The set should cover native PDF text, text coordinates, native vector axes, vector curves, rasterized figures, hybrid vector/raster figures, dense path pages, clipping, page rotation, Form XObjects, text converted to paths, fragmented paths, small markers, and dense spectra or scatter points.

Compare pypdfium2 high-level APIs, pypdfium2.raw, pdfminer.six, pikepdf/QPDF, and other necessary candidates.

For each candidate, document:

- What evidence it can extract.
- What evidence it misses.
- Whether nested objects can be inspected.
- Whether transformation and clipping information is available.
- Whether path geometry is recoverable.
- Whether raw API functions are available and stable in the selected build.
- Peak RSS.
- Per-page processing time.
- Full-paper processing time.
- Error behavior.
- Dependency and license implications.

The spike must not select a backend solely because it has a convenient rendering function.

The result should be a documented backend combination and a list of unsupported PDF structures.

**F. Figure and extraction algorithm tests**

Test figure inventory, panel segmentation, shared legend inheritance, text and axis extraction, vector path filtering, path fragmentation, hybrid extraction, numeric axis calibration, relative signal axes, dual Y axes, CV/EIS path order, curve crossings, occlusion, color-distinguishable curves, same-color ambiguity detection, marker-dependent ambiguity detection, XRD stacked spectra, sloped spectral baselines, XPS background behavior, and series/legend association.

Use synthetic images for deterministic unit tests, but do not present synthetic success as evidence of real-paper scientific accuracy.

**G. Scientific semantics and data model tests**

Test multiple samples in the same paper, different samples in one figure, multiple series in one panel, a subject linked to different techniques, MAIN/SI context linking, alias matching, ambiguous entity assignment, experimental condition separation, measurement separation, table observations versus digitized series, battery capacity-basis preservation, half-cell/full-cell separation, AOP removal versus TOC/COD/mineralization, PFAS parent removal versus defluorination and mineralization, fluoride release, fluorine mass-balance checks, <LOD and <LOQ, unresolved reference-electrode scales, and dual-axis UNASSIGNED.

**H. QC threshold tests**

Test both configurations separately.

Provisional configuration:

- qc_thresholds_provisional.yaml exists.
- P0 development and regression processing can run.
- Results are explicitly marked PROVISIONAL_UNCALIBRATED.
- Provisional results cannot be misreported as calibrated scientific validation.

Calibrated configuration:

- qc_thresholds_calibrated.yaml is generated or approved from an annotated real-paper benchmark.
- Benchmark identity and annotation version are recorded.
- Thresholds are tied to relevant algorithm/profile versions.
- A change to the benchmark or algorithm requires an explicit recalibration decision.
- Previous threshold versions remain recoverable.

**I. Persistence and version-governance tests**

Test paper manifest writing, figure and panel inventory writing, digitization.json, panel_series.csv, paper bundle generation, content hash verification, SQLite single-writer behavior, index rebuild, recovery from a damaged bundle, stage cache reuse, changed-input invalidation, reviewed-result lock, forced reviewed-result recomputation, immutable previous versions, and atomic result updates.

**J. Review patch tests**

Test static offline review loading, folder selection and drag-and-drop, curve overlay visualization, axis-anchor correction, panel-boundary correction, series-label correction, review patch export, review patch schema validation, matching original hash, stale original hash, duplicate patch submission, unsupported patch fields, patch apply dry-run, valid patch application, SQLite index refresh, and conflict report generation.

Verify that a stale patch cannot overwrite a newer digitization result.

**K. Query and export tests**

Test queries by paper ID, entity ID, entity alias, technique, domain, analyte, series role, relevant condition, QC status, and review status.

Test combined queries.

At least one integration test must retrieve different techniques linked to the same paper and supported sample/entity.

Test exports that preserve original values, original units, source evidence, entity and condition metadata, QC/review state, and comparability warnings; support exclusion of unresolved data when explicitly requested; and never silently merge incompatible reference scales or battery capacity bases.

**L. CLI and reporting tests**

Test scan, run --all, run --resume, run --failed-only, run --paper-id, run --dry-run, status, report, validate, query, export, review, review apply --patch, and index rebuild.

Verify report counts against actual job records.

Verify that default token usage is zero.

### Regression tests

Maintain a small, stable regression corpus covering:

1. Native vector figures.
2. Rasterized figures.
3. Hybrid figures.
4. Multi-panel figures and shared legends.
5. CV or EIS non-monotonic paths.
6. Multiple samples and techniques in one paper.
7. Unresolved dual-axis assignment.
8. Relative spectral intensity.
9. Battery capacity-basis separation.
10. AOP/PFAS semantic separation.
11. <LOD or <LOQ handling.
12. Incomplete upstream output.
13. Interrupted processing.
14. Accepted manual-review result.
15. Cross-page sample definition.
16. Reference-electrode information located in a different section.
17. Error-bar definition located in SI.
18. Valid review patch.
19. Stale review patch.
20. Query and ML export for a linked sample.

Keep routine regression tests small enough to run on the target Windows configuration.

### Manual acceptance (if needed)

Use real PDFs and their corresponding chem-literature outputs selected or approved by the user.

The benchmark must contain representative papers from Battery, AOP, and PFOA/PFAS. The user can determine exact paper counts and paper selection.

For manually annotated figures, record source PDF SHA256, page, figure and panel boundaries, axis anchors, expected curve paths or sampled reference points, correct series labels, subject relationships, experimental conditions where available, units and scales, known ambiguities, and expected unresolved fields.

Evaluate axis calibration error, curve-position or point error, visible curve coverage, point order, curve separation, legend association, entity association, condition association, unit interpretation, reference-electrode handling, and review routing for ambiguous figures.

**Tier 1 — P0 acceptance**

Demonstrate the end-to-end path:

chem-literature outputs → input snapshot → context index → figure/panel inventory → PDF evidence → supported P0 extraction → calibration → numerical reconstruction → semantic linking → QC → storage → SQLite index → query → export

The end-to-end path must work on real approved papers.

The P0 acceptance boundary does not require universal extraction of ambiguous same-color curves or complex markers. Correctly preserving and routing them to review is an acceptable P0 outcome.

**Tier 2 — P1 acceptance**

Add and validate tables, bar charts, scatter plots, error bars, advanced marker and line-style recognition, improved difficult-curve separation, and additional domain-specific QC.

**Tier 3 — P2 acceptance**

Evaluate heatmap matrix reconstruction, advanced LC-MS/MS visual reconstruction, complex nested tables, and specialized microscopy or multidimensional image extraction.

Do not classify a P1 or P2 feature as production-ready merely because its code module exists.

## 8. Deliverables

### 8.1 Independent project

- Standalone Tuzhidingdong/scientific-figure-data repository.
- scientific-figure-data-skill entry point.
- Installation instructions.
- Windows execution guide.
- Low-resource configuration guide.
- Upstream adapter documentation.
- P0/P1/P2 capability matrix.
- Scientific semantics documentation.
- Data schema documentation.
- CLI reference.

### 8.2 Source modules

Modules should cover upstream adapter, input manifests and fingerprints, paper-level context index, corpus scheduler, worker supervision, lazy PDF access, PDF backend abstraction, PDF evidence extraction, figure inventory, panel segmentation, legend inheritance, chart classification, vector extraction, raster extraction, hybrid extraction, spectrum extraction, axis calibration, numerical reconstruction, scientific semantic parsing, subject entities and relationships, condition and measurement handling, domain profiles, unit conversion, reference-electrode handling, QC, provisional and calibrated threshold management, review helper, review patch application, canonical artifact writing, SQLite indexing, query, export, CLI, and reporting.

Avoid unnecessary abstraction layers. Modules should have clear, testable interfaces and should not duplicate responsibilities.

### 8.3 PDF backend spike and dependencies

Deliver:

- 3–5 representative PDF benchmark inputs or their approved local references.
- Backend comparison report.
- Per-page Peak RSS and elapsed-time measurements.
- Path and object coverage analysis.
- Known limitations.
- Final backend combination decision.
- Dependency lock/configuration.
- License inventory.
- OCR engine and weight license record.

### 8.4 Data and configuration schemas

Deliver:

- Database schema and migrations.
- Paper manifest schema.
- Context-index schema.
- Figure and panel inventory schemas.
- Digitization metadata schema.
- Review patch schema.
- Paper bundle schema.
- Query/export schema.
- Battery profile.
- AOP profile.
- PFOA/PFAS profile.
- Technique and metric registries.
- Unit and analyte registries.
- qc_thresholds_provisional.yaml.
- qc_thresholds_calibrated.yaml when real benchmark calibration is completed.
- Default low-resource configuration.

### 8.5 Review helper

Deliver offline static HTML helper, folder selection and drag-and-drop support, panel and curve overlays, axis-anchor visualization, series and legend association display, review patch JSON export, patch validation and application CLI, stale-base conflict reporting, review history and immutable-result handling, and an optional localhost-only service if justified.

### 8.6 Storage and indexes

Deliver per-paper input snapshot, compact context index, figure inventory, panel layout, digitization.json, panel-level panel_series.csv, evidence artifacts, versioned paper_bundle.json, rebuildable SQLite catalog, review patch history, and digitization run history.

### 8.7 CLI and downstream consumption

Deliver functioning commands for corpus scan, batch processing, resume and retry, single-paper processing, dry-run, status and report, scientific query, ML-oriented export, review task listing, review patch application, index rebuild, and data/schema validation.

Query and export are required product capabilities, not optional future conveniences.

### 8.8 Tests and benchmark evidence

Deliver unit tests, integration tests, Windows resource tests, crash-recovery tests, adapter compatibility tests, context-index tests, PDF backend spike report, annotated real-paper benchmark, P0 extraction evaluation, P1/P2 capability and limitation report, review patch test evidence, query/export test evidence, and regression corpus instructions.

### 8.9 Corpus processing and execution tracking

Deliver corpus manifest, per-paper input snapshots, run event records, job and lease status, resource and performance reports, corpus-level summary, and sibling STATUS.md.

The report must include total papers discovered, eligible papers, skipped papers, completed papers, completed-with-review papers, papers needing review, permanently failed papers, retry counts, failure reason distribution, elapsed time, throughput, peak RSS, temporary disk usage, algorithm versions, profile versions, QC threshold configuration and calibration state, and LLM token usage (expected to be zero by default).

STATUS.md must track progress against AC identifiers and stage labels, including completed P0 criteria, in-progress P0 criteria, P0 blockers, P1 deferred criteria, P2 deferred criteria, release criteria, evidence/test references, and decisions requiring user approval.

STATUS.md is an execution log and must not redefine this Task Plan.

## 9. Release boundary

- [x] Code/files only; do not publish.
- [ ] Prepare a release candidate; wait for my approval before publishing.
- [ ] Other:

This Task Plan authorizes development planning and implementation work only.

It does not authorize public package publication, public release announcements, automatic deployment, or claims of universal scientific extraction accuracy.

Before a release candidate is proposed, report:

1. Implemented P0 functionality.
2. P0 real-paper benchmark results.
3. Actual supported figure styles.
4. Known unsupported and ambiguous figure styles.
5. Windows target-hardware resource behavior.
6. PDF backend and dependency/license assessment.
7. Input immutability evidence.
8. Resume and crash-recovery evidence.
9. Query and export results.
10. Review patch and conflict-handling evidence.
11. QC threshold calibration status.
12. Token usage.
13. P1/P2 limitations.
14. Remaining manual-review requirements.

A P0 functional milestone may be reported as implemented while QC remains provisional. It must not be described as scientifically calibrated or production-ready until the relevant real-paper benchmark and release criteria have been satisfied.

Final acceptance remains subject to the user's review of actual outputs from approved papers.

## 10. User decisions already made

1. The new Skill is an independent downstream project, not a modification of chem-literature.
2. The target repository is Tuzhidingdong/scientific-figure-data.
3. The Skill ID is scientific-figure-data-skill.
4. The new Skill consumes existing chem-literature artifacts through a read-only adapter.
5. The expected corpus contains several thousand papers.
6. The system must support incremental processing, resume, failure isolation, and index rebuilding.
7. The initial research domains are Battery/Energy Storage, AOP, and PFOA/PFAS.
8. Future scientific domains must be addable through profiles.
9. The main practical query includes finding different techniques for the same paper and same sample/entity, such as XRD and CV for one material.
10. Series-level subject linking is mandatory.
11. Subject entities, experimental conditions, measurement events, and series must remain separate concepts.
12. Cross-page and MAIN/SI semantic context is necessary. A panel's scientific interpretation must not be limited to information printed on the same PDF page.
13. Heavy visual data must be processed page-by-page, figure-by-figure, and panel-by-panel on demand.
14. A compact paper-level text/alias/context index may be built from existing upstream outputs. Approximately 500 KB is a default in-memory target, not a hard limit that causes source information to be discarded.
15. Default operation is Windows 10/11, approximately 8 GB RAM, 4 logical CPU cores, without a dedicated GPU.
16. The default worker count is one.
17. Sequential lazy iteration is preferred inside the single worker. Do not create unnecessary queues or internal parallelism.
18. Bounded queues and backpressure apply where asynchronous scheduler/worker or result-writer boundaries actually exist.
19. The scheduler supervises isolated paper workers. Workers do not concurrently write to SQLite.
20. OCR is optional, lazy-loaded, and reused within the worker.
21. The design must provide degraded operation for computers below the baseline hardware configuration.
22. The PDF backend must be selected after a 3–5 representative PDF technical spike.
23. pypdfium2.raw, pikepdf/QPDF, and pdfminer.six should be evaluated according to their actual responsibilities and benchmark results. No single backend is assumed to solve every extraction problem.
24. PDF and OCR dependency licenses and bundled native-library licenses must be reviewed.
25. P0 raster extraction must prioritize low-ambiguity curves. Complex same-color crossings, marker-dependent distinctions, and difficult line styles may be routed to review. Advanced automatic recognition belongs in P1.
26. Provisional QC thresholds may be used during development. Scientific validation requires a separately calibrated threshold configuration based on annotated real papers.
27. QC must track independent extraction dimensions, not only one overall confidence score.
28. Battery, AOP, and PFAS semantics must remain scientifically distinct.
29. Reference-electrode conversion must be conservative and evidence-based.
30. Unresolved dual-axis assignments must remain UNASSIGNED.
31. Original values and units must be retained separately from standardized values.
32. <LOD and <LOQ must never be converted to zero.
33. Storage should use canonical paper-level artifacts, merged panel CSV, JSON metadata, paper bundle snapshots, and a rebuildable SQLite index.
34. Parquet is deferred until justified by actual corpus size and downstream use.
35. Scientific query and ML-oriented export are core product functions and must have CLI support.
36. Offline review must support exporting review patches.
37. Review patch application must verify original_result_hash, preserve prior versions, and reject stale patches with PATCH_CONFLICT_STALE_BASE.
38. Accepted review results must not be silently overwritten.
39. Default execution must use zero LLM tokens.
40. Any future LLM functionality must be explicitly enabled, restricted to a model confirmed to be free under the user's OpenCode Go subscription, and must never use automatic paid fallback.
41. Real annotated papers selected or approved by the user are required for scientific acceptance.
42. Synthetic tests cannot substitute for real-paper acceptance.
43. P1/P2 development must not block P0 functional acceptance unless the user explicitly changes the scope.
44. Execution progress belongs in the sibling STATUS.md; this Task Plan remains the governing objective and acceptance baseline.
45. Current authorization is code/files only. No publication or release is authorized.
