# Windows low-resource operation

Target baseline: Windows 10/11, 8 GB RAM, four logical CPU cores, no GPU.

Recommended initial setup:

    py -3.11 -m venv .venv
    .venv\Scripts\activate
    python -m pip install --upgrade pip
    python -m pip install -e ".[pdf,images,dev]"

Start with `--workers 1` and `--dry-run`. Lower `--render-scale` and `--memory-limit` if the machine is under pressure. OCR is not installed by default. The scheduler checks resources before dispatching each new paper: default `--min-free-disk-mb 256` pauses below 256 MiB free disk, and `--min-free-memory-mb 512` pauses below 512 MiB available RAM. Increase either threshold on constrained systems; use a value of `0` only when explicitly disabling that guard.

Example low-resource run:

    sfd run --resume --input-root INPUT_ROOT --output-root OUTPUT_ROOT --workers 1 --render-scale 1.0 --memory-limit 1536 --min-free-disk-mb 512 --min-free-memory-mb 1024

The worker initializer clamps common native thread pools to one thread. The default scheduler uses a spawned worker process with a bounded number of active paper jobs. Large image arrays are never sent over multiprocessing pipes; results are written as canonical files and only compact metadata is returned.

For the lowest memory mode, process sequentially, use a render scale of 1.0 or lower, keep caches small, and leave OCR disabled. A corrupted PDF or native backend crash should fail/isolate one paper and permit the run to continue or resume. If free disk or available RAM falls below its configured threshold, no additional paper is started; already running papers are allowed to finish, and `run_report.json` records `paused_for_resource_pressure`, the reason, and observed disk/memory values. After freeing disk space, rerun with `--resume`. This disk guard does not replace the per-paper evidence budget or worker memory limit.

Do not run the output root inside the upstream input tree. The upstream tree is read-only by contract.
