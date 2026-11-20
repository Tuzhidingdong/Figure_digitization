# Windows low-resource operation

Target baseline: Windows 10/11, 8 GB RAM, four logical CPU cores, no GPU.

Recommended initial setup:

    py -3.11 -m venv .venv
    .venv\Scripts\activate
    python -m pip install --upgrade pip
    python -m pip install -e ".[pdf,images,dev]"

Start with `--workers 1` and `--dry-run`. Lower `--render-scale` and `--memory-limit` if the machine is under pressure. OCR is not installed by default. The scheduler checks resources before dispatching each new paper: default `--min-free-disk-mb 256` pauses below 256 MiB free disk, and `--min-free-memory-mb 512` pauses below 512 MiB available RAM. Increase either threshold on constrained systems; use a value of `0` only when explicitly disabling that guard. The `--temp-disk-limit 2048` value separately bounds each paper's evidence/context-index storage and the run-scoped SFD scratch directory; the two budgets are not combined. Series CSVs and version backups are included in returned paper-output byte accounting and remain subject to the free-disk guard. The scheduler redirects worker `TEMP`, `TMP` and `TMPDIR` to a unique directory under `OUTPUT_ROOT/.sfd-runtime-tmp`, samples its peak file bytes, and removes it after worker shutdown.

Example low-resource run:

    sfd run --resume --input-root INPUT_ROOT --output-root OUTPUT_ROOT --workers 1 --render-scale 1.0 --memory-limit 1536 --temp-disk-limit 1024 --min-free-disk-mb 512 --min-free-memory-mb 1024

The worker initializer clamps common native thread pools to one thread. The default scheduler uses a spawned worker process with a bounded number of active paper jobs. Large image arrays are never sent over multiprocessing pipes; results are written as canonical files and only compact metadata is returned.

For the lowest memory mode, process sequentially, use a render scale of 1.0 or lower, keep caches small, and leave OCR disabled. A corrupted PDF or native backend crash should fail/isolate one paper and permit the run to continue or resume. If free disk or available RAM falls below its configured threshold, no additional paper is started; already running papers are allowed to finish, and `run_report.json` records `paused_for_resource_pressure`, the reason, and observed disk/memory values. After freeing disk space, rerun with `--resume`. This guard does not replace the per-paper evidence/context budget or worker memory limit. The report also records parent/worker CPU seconds, average CPU cores, sampled peak RSS, per-paper evidence/context-index/output footprint, `sfd_temp_peak_bytes`, the temp limit, worker temp-isolation verification, and cleanup status. This is run-scoped application temp accounting, not a scan of other applications' global OS temporary directories.

The input and output root trees must be disjoint: do not use the same directory, do not put output inside input, and do not put input inside output. The command rejects each overlapping layout before it writes. The upstream tree is read-only by contract.


## Target Windows resource measurement

The hosted Windows CI matrix is a software regression check, not a substitute for a measurement on the target 8 GB / 4-core computer. The repository provides a local sampler:

    powershell -ExecutionPolicy Bypass -File scripts/measure_windows_resource.ps1 -InputRoot "D:\\chem-literature-outputs\runs\preprocessed" -OutputRoot "D:\\figure-data-output"

The script runs the default one-worker pipeline with conservative rendering, samples the sfd parent/child process tree, records peak sampled working set, CPU time/utilization, available physical memory, free disk space, output-directory growth, and samples `OUTPUT_ROOT/.sfd-runtime-tmp`. It embeds the pipeline run_report.json, which records the scheduler's internal per-run TEMP/TMP/TMPDIR peak and cleanup result. Add -Resume to measure a resume run. The source root is checked to be disjoint from the output root.

It writes a timestamped JSON result plus stdout/stderr logs inside the output directory. The sampler is local-only: it does not upload papers, artifacts, or metrics. RSS, output-directory size, and SFD scratch-directory size are sampled and can miss very short-lived spikes. The scheduler removes its run-scoped scratch folder after worker shutdown; a failed cleanup is reported by `sfd_temp_cleanup_succeeded` and leaves the relative path in the run report. The embedded pipeline report supplies additional per-paper evidence/context/output footprint fields. Keep the actual benchmark corpus small and representative for the first run, and retain its input manifest and machine specification with the result.


The Windows measurement harness validates canonicalized input/output paths, including existing junction/symlink parents, before creating the output directory. Invalid overlapping roots therefore do not create folders inside the upstream tree.
