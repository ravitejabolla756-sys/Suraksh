$ErrorActionPreference = "Stop"

Write-Warning "This removes the SURAKSH demo PostgreSQL volume and all local demo state."
$confirmation = Read-Host "Type RESET to continue"
if ($confirmation -ne "RESET") {
    Write-Host "Reset cancelled."
    exit 0
}
docker compose down --volumes --remove-orphans
