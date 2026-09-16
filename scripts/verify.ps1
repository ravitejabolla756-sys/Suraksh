$ErrorActionPreference = "Stop"

$env:VISIONGUARD_JWT_SECRET = "local-test-secret-only"
$env:SURAKSH_EDGE_INGEST_KEY = [guid]::NewGuid().ToString("N")
$env:VISIONGUARD_EDGE_INGEST_KEY = (([Security.Cryptography.SHA256]::Create().ComputeHash([Text.Encoding]::UTF8.GetBytes($env:SURAKSH_EDGE_INGEST_KEY)) | ForEach-Object { $_.ToString("x2") }) -join "")
$env:VISIONGUARD_EDGE_INGEST_KEY_HASH = $env:VISIONGUARD_EDGE_INGEST_KEY

Push-Location "$PSScriptRoot\.."
docker compose config --quiet
Pop-Location

Push-Location "$PSScriptRoot\..\backend"
alembic upgrade head
python -m pytest
Pop-Location

Push-Location "$PSScriptRoot\..\edge-ai"
python -m compileall app
Pop-Location

Push-Location "$PSScriptRoot\..\frontend"
npm run typecheck
npm run lint
npm run build
Pop-Location
