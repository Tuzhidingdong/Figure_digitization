# Run2 stalled-run evidence (P3_02, adma.202001469)

- CLI wrapper PID 40032, started 2026-11-22 14:48:42, idle ~0.64 s CPU.
- Spawned worker PID 44692, started 2026-11-22 14:48:43, parent PID 9632 (exited), command:
  `python -c "from multiprocessing.spawn import spawn_main; spawn_main(parent_pid=9632, pipe_handle=668)" --multiprocessing-fork`
- CPU delta over 3 s: 0; 1 thread; WaitReason=UserRequest / ThreadState=Wait.
- Last substantive artifact write: 14:48:55 (canonical JSON + comparison sheet).
- `run_report.json`, `validate.log`, `export.log` were never produced; `catalog.sqlite` job state remained `RUNNING` with `last_error=None`.
- The background shell was cancelled by a server restart; PIDs 44692 and 40032 were subsequently confirmed gone. No kill was executed by the tester.
- Read-only snapshot backup: `E:\Zinc_batters_datas\Figure_digitization_p1_pixel_geometry_outputs_20261122\STALLED_BACKUP_run2_20261122T1711` (27 files), created after the restart. Key SHA256 values are recorded in the top-level `manifest.json`.
- This run's scientific status is FAILED / NEEDS_REVIEW: 1 whole-figure panel, 1 series, 0 data points, trace_spec `NEEDS_REVIEW / PLOT_REGION_UNRESOLVED`. `COMPLETED_WITH_REVIEW` in digitization.json is only a paper-level artifact status and does not mean recognition succeeded.
