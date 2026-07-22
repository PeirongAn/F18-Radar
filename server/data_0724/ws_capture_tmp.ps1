param(
  [string]$Repo = "D:\codes\F18-Radar",
  [int]$Seconds = 600
)

$log = Join-Path $Repo "server\logs\radar_system_2026-05-28.log"
$outDir = Join-Path $Repo "server\data\ws-captures"
New-Item -ItemType Directory -Force -Path $outDir | Out-Null

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$out = Join-Path $outDir "ws-capture-$stamp.log"
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)

function Write-CaptureLine {
  param([AllowNull()][string]$Line)
  if ($null -eq $Line) {
    return
  }
  Write-Output $Line
  [System.IO.File]::AppendAllText($out, "$Line`r`n", $utf8NoBom)
}

function Write-CaptureLines {
  param($Lines)
  foreach ($line in $Lines) {
    Write-CaptureLine $line
  }
}

$patterns = @(
  "NET WS",
  "RAW platform",
  "REMOTE_TASK_COUNT",
  "tobii_hand",
  "tobii_marker",
  "marker recorded",
  "bbox",
  "attention_feedback",
  "task_run",
  "task_id="
)

[System.IO.File]::WriteAllText($out, "", $utf8NoBom)
Write-CaptureLine "capture_start=$(Get-Date -Format o)"
Write-CaptureLine "source_log=$log"
Write-CaptureLine "duration_seconds=$Seconds"
Write-CaptureLine "---"

$job = Start-Job -ScriptBlock {
  param($log, $patterns)
  Get-Content $log -Encoding UTF8 -Tail 0 -Wait |
    Where-Object {
      $line = $_
      foreach ($p in $patterns) {
        if ($line -like "*$p*") { return $true }
      }
      return $false
    }
} -ArgumentList $log, $patterns

$deadline = (Get-Date).AddSeconds($Seconds)
try {
  while ((Get-Date) -lt $deadline) {
    Write-CaptureLines (Receive-Job $job)
    Start-Sleep -Milliseconds 300
  }
}
finally {
  Write-CaptureLines (Receive-Job $job)
  Stop-Job $job -ErrorAction SilentlyContinue | Out-Null
  Remove-Job $job -ErrorAction SilentlyContinue | Out-Null
  Write-CaptureLine "---"
  Write-CaptureLine "capture_end=$(Get-Date -Format o)"
  Write-CaptureLine "capture_file=$out"
  Write-Host "WS capture saved to: $out"
}
