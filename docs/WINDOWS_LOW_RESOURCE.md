# Windows low-resource operation

Target baseline: Windows 10/11, 8 GB RAM, four logical CPU cores, no GPU.

Recommended initial setup:

    py -3.11 -m venv .venv
    .venv\Scripts\activate
    python -m pip install --upgrade pip
    python -m pip install -e ".[pdf,images,dev]"

Start with --workers 1 and --dry-run. Lower --render-scale and --memory-limit if the machine is under pressure. OCR is not installed by default.

The worker initializer clamps common native thread pools to one thread. The default scheduler uses a spawned worker process with a bounded number of active paper jobs. Large image arrays are never sent over multiprocessing pipes; results are written as canonical files and only compact metadata is returned.

For the lowest memory mode, process sequentially, use a render scale of 1.0 or lower, keep caches small, and leave OCR disabled. A corrupted PDF or native backend crash should fail/isolate one paper and permit the run to continue or resume.

Do not run the output root inside the upstream input tree. The upstream tree is read-only by contract.
