param(
  [string]$MediaDir = "$PSScriptRoot\..\demo-media"
)

$ErrorActionPreference = "Stop"
$python = Join-Path $PSScriptRoot "..\.venv-ai\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) { $python = "python" }

foreach ($name in @("vms-a.mp4", "vms-b.mp4")) {
  $path = Join-Path $MediaDir $name
  if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
    throw "Missing $name. Place a rights-cleared vehicle video at: $path"
  }
  $probe = @'
import cv2, sys
path = sys.argv[1]
capture = cv2.VideoCapture(path)
if not capture.isOpened(): raise SystemExit(f"UNREADABLE: {path}")
frames = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
fps = float(capture.get(cv2.CAP_PROP_FPS))
ok, frame = capture.read()
capture.release()
if not ok or frame is None or frames <= 0 or width <= 0 or height <= 0 or fps <= 0:
    raise SystemExit(f"INVALID: {path} frames={frames} size={width}x{height} fps={fps}")
print(f"PASS: {path} frames={frames} size={width}x{height} fps={fps:.3f}")
'@
  $probe | & $python - $path
  if ($LASTEXITCODE -ne 0) { throw "OpenCV validation failed for $path" }
}
