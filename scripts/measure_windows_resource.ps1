param(
    [Parameter(Mandatory = $true)][string]$InputRoot,
    [Parameter(Mandatory = $true)][string]$OutputRoot,
    [string]$SfdCommand = "sfd",
    [int]$SampleIntervalSeconds = 1,
    [int]$MemoryLimitMb = 1536,
    [int]$MinFreeDiskMb = 512,
    [int]$MinFreeMemoryMb = 1024,
    [double]$RenderScale = 1.0,
    [switch]$Resume
)

$ErrorActionPreference = "Stop"

function ConvertTo-NativeArgument([string]$Value) {
    $escaped = $Value.Replace('"', '\"')
    $trailing = [regex]::Match($escaped, '\\+$')
    if ($trailing.Success) {
        $escaped = $escaped.Substring(0, $escaped.Length - $trailing.Length) +
                   ($trailing.Value + $trailing.Value)
    }
    return '"' + $escaped + '"'
}

function Get-DirectoryBytes([string]$Path) {
    [Int64]$total = 0
    if (Test-Path -LiteralPath $Path) {
        Get-ChildItem -LiteralPath $Path -File -Recurse -Force -ErrorAction SilentlyContinue |
            ForEach-Object { $total += [Int64]$_.Length }
    }
    return $total
}

function Get-SystemMemoryBytes {
    $os = Get-CimInstance Win32_OperatingSystem
    return [Int64]$os.FreePhysicalMemory * 1024
}

function Get-VolumeFreeBytes([string]$Path) {
    $root = [IO.Path]::GetPathRoot($Path)
    if (-not $root -or $root.StartsWith("\\")) { return $null }
    $device = $root.TrimEnd('\')
    $volume = Get-CimInstance Win32_LogicalDisk -Filter ("DeviceID='{0}'" -f $device) |
        Select-Object -First 1
    if ($null -eq $volume) { return $null }
    return [Int64]$volume.FreeSpace
}

function Get-DescendantProcessIds([int]$RootPid) {
    $rows = Get-CimInstance Win32_Process
    $ids = New-Object 'System.Collections.Generic.HashSet[int]'
    [void]$ids.Add($RootPid)
    $changed = $true
    while ($changed) {
        $changed = $false
        foreach ($row in $rows) {
            $pidValue = [int]$row.ProcessId
            $parentValue = [int]$row.ParentProcessId
            if ($ids.Contains($parentValue) -and -not $ids.Contains($pidValue)) {
                [void]$ids.Add($pidValue)
                $changed = $true
            }
        }
    }
    return @($ids)
}

$inputPath = (Resolve-Path -LiteralPath $InputRoot).Path
if (-not (Test-Path -LiteralPath $OutputRoot)) {
    New-Item -ItemType Directory -Path $OutputRoot -Force | Out-Null
}
$outputPath = (Resolve-Path -LiteralPath $OutputRoot).Path
$inputFull = [IO.Path]::GetFullPath($inputPath).TrimEnd('\')
$outputFull = [IO.Path]::GetFullPath($outputPath).TrimEnd('\')
if ($inputFull -ieq $outputFull -or
    $inputFull.StartsWith($outputFull + '\', [StringComparison]::OrdinalIgnoreCase) -or
    $outputFull.StartsWith($inputFull + '\', [StringComparison]::OrdinalIgnoreCase)) {
    throw "InputRoot and OutputRoot must be disjoint directory trees."
}
if ($SampleIntervalSeconds -lt 1) { throw "SampleIntervalSeconds must be at least 1." }

$command = Get-Command $SfdCommand -ErrorAction Stop
$resolvedCommand = $command.Source
if (-not $resolvedCommand) { $resolvedCommand = $command.Definition }

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$stdoutPath = Join-Path $outputPath "resource_benchmark_stdout_$stamp.log"
$stderrPath = Join-Path $outputPath "resource_benchmark_stderr_$stamp.log"
$resultPath = Join-Path $outputPath "resource_benchmark_$stamp.json"

$arguments = @(
    "run", "--all",
    "--input-root", $inputPath,
    "--output-root", $outputPath,
    "--workers", "1",
    "--max-open-pdfs", "1",
    "--render-scale", "$RenderScale",
    "--memory-limit", "$MemoryLimitMb",
    "--min-free-disk-mb", "$MinFreeDiskMb",
    "--min-free-memory-mb", "$MinFreeMemoryMb"
)
if ($Resume) { $arguments += "--resume" }
$argumentLine = ($arguments | ForEach-Object { ConvertTo-NativeArgument $_ }) -join " "

$logicalProcessors = [int](Get-CimInstance Win32_ComputerSystem).NumberOfLogicalProcessors
$startedAt = Get-Date
$outputBytesAtStart = Get-DirectoryBytes $outputPath
$freeDiskAtStart = Get-VolumeFreeBytes $outputPath
$freeMemoryAtStart = Get-SystemMemoryBytes
$previousTemp = $env:TEMP
$previousTmp = $env:TMP
$tempBase = if ($previousTemp) { $previousTemp } else { [IO.Path]::GetTempPath() }
$benchmarkTempRoot = Join-Path $tempBase "sfd-resource-benchmark-$stamp"
New-Item -ItemType Directory -Path $benchmarkTempRoot -Force | Out-Null
$temporaryBytesAtStart = Get-DirectoryBytes $benchmarkTempRoot
$temporaryFreeDiskAtStart = Get-VolumeFreeBytes $benchmarkTempRoot
try {
    # The sfd child process and its descendants inherit this isolated temp location.
    $env:TEMP = $benchmarkTempRoot
    $env:TMP = $benchmarkTempRoot
    $process = Start-Process -FilePath $resolvedCommand -ArgumentList $argumentLine -PassThru -NoNewWindow -RedirectStandardOutput $stdoutPath -RedirectStandardError $stderrPath
} finally {
    if ($null -eq $previousTemp) { Remove-Item Env:TEMP -ErrorAction SilentlyContinue } else { $env:TEMP = $previousTemp }
    if ($null -eq $previousTmp) { Remove-Item Env:TMP -ErrorAction SilentlyContinue } else { $env:TMP = $previousTmp }
}

$peakWorkingSetBytes = [Int64]0
$minimumFreeDiskBytes = $freeDiskAtStart
$minimumTemporaryFreeDiskBytes = $temporaryFreeDiskAtStart
$minimumFreeMemoryBytes = $freeMemoryAtStart
$cpuByPid = @{}
$observedPids = New-Object 'System.Collections.Generic.HashSet[int]'
$outputBytesPeak = $outputBytesAtStart
$temporaryBytesPeak = $temporaryBytesAtStart
$sampleCount = 0

while (-not $process.HasExited) {
    $processIds = Get-DescendantProcessIds -RootPid $process.Id
    [Int64]$workingSet = 0
    foreach ($pidValue in $processIds) {
        [void]$observedPids.Add([int]$pidValue)
        try {
            $sample = Get-Process -Id $pidValue -ErrorAction Stop
            $workingSet += [Int64]$sample.WorkingSet64
            if ($null -ne $sample.CPU) {
                $cpu = [double]$sample.CPU
                if (-not $cpuByPid.ContainsKey([int]$pidValue) -or $cpu -gt $cpuByPid[[int]$pidValue]) {
                    $cpuByPid[[int]$pidValue] = $cpu
                }
            }
        } catch {
            # Short-lived child may exit between process enumeration and sampling.
        }
    }
    if ($workingSet -gt $peakWorkingSetBytes) { $peakWorkingSetBytes = $workingSet }

    $freeDisk = Get-VolumeFreeBytes $outputPath
    if ($null -ne $freeDisk -and
        ($null -eq $minimumFreeDiskBytes -or $freeDisk -lt $minimumFreeDiskBytes)) {
        $minimumFreeDiskBytes = $freeDisk
    }
    $temporaryFreeDisk = Get-VolumeFreeBytes $benchmarkTempRoot
    if ($null -ne $temporaryFreeDisk -and
        ($null -eq $minimumTemporaryFreeDiskBytes -or $temporaryFreeDisk -lt $minimumTemporaryFreeDiskBytes)) {
        $minimumTemporaryFreeDiskBytes = $temporaryFreeDisk
    }
    $freeMemory = Get-SystemMemoryBytes
    if ($null -ne $freeMemory -and
        ($null -eq $minimumFreeMemoryBytes -or $freeMemory -lt $minimumFreeMemoryBytes)) {
        $minimumFreeMemoryBytes = $freeMemory
    }

    $sampleCount++
    if (($sampleCount % 5) -eq 0) {
        $outputBytes = Get-DirectoryBytes $outputPath
        if ($outputBytes -gt $outputBytesPeak) { $outputBytesPeak = $outputBytes }
        $temporaryBytes = Get-DirectoryBytes $benchmarkTempRoot
        if ($temporaryBytes -gt $temporaryBytesPeak) { $temporaryBytesPeak = $temporaryBytes }
    }
    Start-Sleep -Seconds $SampleIntervalSeconds
    $process.Refresh()
}
$process.WaitForExit()
$endedAt = Get-Date
$outputBytesAtEnd = Get-DirectoryBytes $outputPath
if ($outputBytesAtEnd -gt $outputBytesPeak) { $outputBytesPeak = $outputBytesAtEnd }
$freeDiskAtEnd = Get-VolumeFreeBytes $outputPath
$temporaryBytesAtEnd = Get-DirectoryBytes $benchmarkTempRoot
if ($temporaryBytesAtEnd -gt $temporaryBytesPeak) { $temporaryBytesPeak = $temporaryBytesAtEnd }
$temporaryFreeDiskAtEnd = Get-VolumeFreeBytes $benchmarkTempRoot
$freeMemoryAtEnd = Get-SystemMemoryBytes
$elapsedSeconds = [Math]::Max(0.001, ($endedAt - $startedAt).TotalSeconds)
$cpuSeconds = [double](($cpuByPid.Values | Measure-Object -Sum).Sum)
$cpuPercent = if ($logicalProcessors -gt 0) {
    [Math]::Round(($cpuSeconds / ($elapsedSeconds * $logicalProcessors)) * 100, 2)
} else { $null }

$pipelineReportPath = Join-Path $outputPath "run_report.json"
$pipelineReport = $null
if (Test-Path -LiteralPath $pipelineReportPath) {
    try {
        $pipelineReport = Get-Content -LiteralPath $pipelineReportPath -Raw | ConvertFrom-Json
    } catch {
        $pipelineReport = @{ parse_error = $_.Exception.Message }
    }
}

$result = [ordered]@{
    schema_version = "1.0"
    benchmark_type = "LOCAL_WINDOWS_PROCESS_TREE_SAMPLE"
    started_at = $startedAt.ToString("o")
    ended_at = $endedAt.ToString("o")
    elapsed_seconds = [Math]::Round($elapsedSeconds, 3)
    exit_code = $process.ExitCode
    process_id = $process.Id
    observed_process_ids = @($observedPids)
    sample_interval_seconds = $SampleIntervalSeconds
    sample_count = $sampleCount
    logical_processors = $logicalProcessors
    peak_process_tree_working_set_bytes = $peakWorkingSetBytes
    summed_process_cpu_seconds = [Math]::Round($cpuSeconds, 3)
    average_cpu_percent_of_logical_capacity = $cpuPercent
    free_disk_bytes_at_start = $freeDiskAtStart
    minimum_free_disk_bytes_observed = $minimumFreeDiskBytes
    free_disk_bytes_at_end = $freeDiskAtEnd
    isolated_temp_directory = $benchmarkTempRoot
    temporary_directory_bytes_at_start = $temporaryBytesAtStart
    temporary_directory_bytes_peak_sampled = $temporaryBytesPeak
    temporary_directory_bytes_at_end = $temporaryBytesAtEnd
    temporary_volume_free_bytes_at_start = $temporaryFreeDiskAtStart
    minimum_temporary_volume_free_bytes_observed = $minimumTemporaryFreeDiskBytes
    temporary_volume_free_bytes_at_end = $temporaryFreeDiskAtEnd
    output_directory_bytes_at_start = $outputBytesAtStart
    output_directory_bytes_peak_sampled = $outputBytesPeak
    output_directory_bytes_at_end = $outputBytesAtEnd
    output_directory_growth_bytes = [Int64]$outputBytesAtEnd - [Int64]$outputBytesAtStart
    free_memory_bytes_at_start = $freeMemoryAtStart
    minimum_free_memory_bytes_observed = $minimumFreeMemoryBytes
    free_memory_bytes_at_end = $freeMemoryAtEnd
    stdout_log = [IO.Path]::GetFileName($stdoutPath)
    stderr_log = [IO.Path]::GetFileName($stderrPath)
    pipeline_run_report = $pipelineReport
    measurement_notes = @(
        "Process-tree RSS is sampled; very short-lived spikes between samples may be missed.",
        "Output-directory bytes are sampled separately from the isolated TEMP/TMP directory.",
        "The isolated TEMP/TMP directory is retained for inspection and is not automatically deleted.",
        "Temporary-directory byte counts are sampled and may miss very short-lived peaks.",
        "The embedded run_report.json supplies per-paper and scheduler resource telemetry.",
        "This is a local engineering measurement, not scientific extraction-accuracy evidence."
    )
}
$result | ConvertTo-Json -Depth 100 | Set-Content -LiteralPath $resultPath -Encoding UTF8
Write-Host ("Resource benchmark report: {0}" -f $resultPath)
Write-Host ("sfd exit code: {0}" -f $process.ExitCode)
exit $process.ExitCode
