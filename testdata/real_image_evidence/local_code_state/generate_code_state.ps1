$dir = 'E:\Zinc_batters_datas\Figure_digitization_sync_evidence_20261122\testdata\real_image_evidence\local_code_state'
$repos = @(
  'E:\Zinc_batters_datas\Figure_digitization',
  'E:\Zinc_batters_datas\Figure_digitization_pr16_test',
  'E:\Zinc_batters_datas\Figure_digitization_p1_test_20261122',
  'E:\Zinc_batters_datas\Figure_digitization_p1_ocrfix_test_20261122',
  'E:\Zinc_batters_datas\Figure_digitization_p1_multicolor_test_20261122',
  'E:\Zinc_batters_datas\Figure_digitization_p1_pixel_geometry_test_20261122'
)

$lines = @()
foreach ($p in $repos) {
  $lines += "=== $p ==="
  $lines += "branch: $(git -C $p rev-parse --abbrev-ref HEAD)"
  $lines += "HEAD: $(git -C $p rev-parse HEAD)"
  $lines += "status:"
  $lines += (git -C $p status --short | ForEach-Object { "  $_" })
  $lines += "src_tracked_diff_lines: $((git -C $p diff -- src | Measure-Object -Line).Lines)"
  $lines += "unpushed_vs_upstream: $((git -C $p log --oneline '@{upstream}..HEAD' 2>$null | Measure-Object -Line).Lines)"
  $lines += ""
}
$lines | Out-File -FilePath "$dir\branch_head_status.txt" -Encoding utf8

$patch = @()
foreach ($p in $repos) {
  $patch += "=== $p ==="
  $patch += (git -C $p diff -- src)
}
$patch | Out-File -FilePath "$dir\uncommitted_source.patch" -Encoding utf8

$unpushed = @()
foreach ($p in $repos) {
  $unpushed += "=== $p ==="
  $unpushed += (git -C $p log --oneline '@{upstream}..HEAD' 2>$null)
}
$unpushed | Out-File -FilePath "$dir\unpushed_commits.txt" -Encoding utf8

$log = @()
foreach ($p in $repos) {
  $log += "=== $p ==="
  $log += (git -C $p log -20 --oneline --decorate)
}
$log | Out-File -FilePath "$dir\last_20_commits.txt" -Encoding utf8

$diff = @()
foreach ($p in $repos) {
  $diff += "=== $p ==="
  $diff += (git -C $p diff --stat HEAD..origin/main 2>$null)
}
$diff | Out-File -FilePath "$dir\local_remote_diff.txt" -Encoding utf8

Write-Output 'code state files written'
