param(
  [ValidateSet("Local", "Prerequisites")][string]$Mode = "Local",
  [string]$BackendUrl = "http://localhost:8000",
  [string]$VmsAUrl = "http://localhost:8091",
  [string]$VmsBUrl = "http://localhost:8092",
  [string]$VideoA = "$PSScriptRoot\..\demo-media\vms-a.mp4",
  [string]$VideoB = "$PSScriptRoot\..\demo-media\vms-b.mp4"
)

$ErrorActionPreference = "Stop"

if ($Mode -eq "Local") {
  Push-Location (Join-Path $PSScriptRoot "..")
  try {
    python -u scripts/phase4_e2e.py --backend $BackendUrl
    if ($LASTEXITCODE -ne 0) { throw "FAIL: real runtime E2E exited $LASTEXITCODE" }
  } finally { Pop-Location }
  exit 0
}

function Assert-Http($url, $label) {
  try { $response = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 8 }
  catch { throw "FAIL: $label unavailable at $url ($($_.Exception.Message))" }
  if ($response.StatusCode -lt 200 -or $response.StatusCode -ge 300) { throw "FAIL: $label returned HTTP $($response.StatusCode)" }
  Write-Host "PASS: $label ($($response.StatusCode))"
  return $response
}

function Assert-File($path, $label) {
  if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "FAIL: $label missing: $path" }
  if ((Get-Item -LiteralPath $path).Length -lt 1024) { throw "FAIL: $label is empty or too small: $path" }
  Write-Host "PASS: $label ($((Get-Item -LiteralPath $path).Length) bytes)"
}

Write-Host "SURAKSH runtime evidence gate"
Assert-Http "$BackendUrl/health" "backend health" | Out-Null
$vmsA = Assert-Http "$VmsAUrl/health" "VMS A simulator"
$vmsB = Assert-Http "$VmsBUrl/health" "VMS B simulator"
Assert-File $VideoA "VMS A recorded CCTV source"
Assert-File $VideoB "VMS B recorded CCTV source"

$health = (Invoke-WebRequest -Uri "$BackendUrl/health" -UseBasicParsing).Content | ConvertFrom-Json
if ($health.status -ne "ok") { throw "FAIL: backend health payload did not report status=ok" }

Write-Host "PASS: service and media prerequisites are available"
Write-Host "NEXT: run the edge worker with SURAKSH_YOLO_MODEL configured and capture its real detection IDs."
Write-Host "This script intentionally does not seed detections or claim AI success; persistence, search, watchlist, and alert checks require a live authenticated backend and real worker output."
