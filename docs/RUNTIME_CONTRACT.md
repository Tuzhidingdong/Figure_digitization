# V2.1 runtime contract

The V2.1 defaults are conservative Windows worker limits. These are resource safeguards, not scientific accuracy claims.

## Worker memory

- Soft RSS threshold: **1,434 MiB** (approximately 1.4 GiB).
- Hard RSS limit: **1,843 MiB** (approximately 1.8 GiB).
- At the soft threshold, the worker performs best-effort `gc.collect()` and records pre/post collection RSS. A soft-threshold observation does not itself discard the current paper.
- The hard limit raises `MemoryError`; the scheduler may retry the paper in a fresh worker within its existing retry budget.
- The process pool uses `max_tasks_per_child=1`: a worker handles one paper, returns its paper-level checkpoint/artifacts, and is then recycled. This process recycle is authoritative for releasing allocator fragmentation; garbage collection is only best-effort.
- Parent-side RSS sampling remains a separate run-level metric. Worker checkpoint RSS observations are not mislabeled as true peak RSS.

CLI controls: `--memory-soft-limit` and `--memory-limit` (the legacy option name now means hard limit).

## Page rendering

- Full-page overview render long edge is capped at **3,200 pixels**.
- Overview decode is also capped at **10,240,000 pixels**.
- The render scale is the minimum of requested scale, area cap and long-edge cap.
- High-resolution detail is taken from bounded figure/panel crops; the pipeline must not decode an unbounded full-page raster to recover detail.

CLI controls: `--max-render-long-edge` and `--max-render-pixels`.

## SQLite and filesystem writes

- SQLite uses WAL mode, `synchronous=NORMAL`, and a 10,000 ms busy timeout.
- A whole paper-index transaction retries only `SQLITE_BUSY` / `SQLITE_LOCKED`, at most five attempts, with bounded exponential backoff.
- Atomic file replacement retries transient Windows sharing violations at most five times (50 ms exponential base, capped at 500 ms).
- New artifacts are written to a same-directory temporary file and flushed before replacement. If replacement still fails, the previous valid destination remains untouched and the temporary file is removed.

The limits are part of the processing-stage fingerprint. Changing them invalidates an otherwise cached stage rather than silently reusing outputs generated under different resource constraints.
