# Only export current dev WSL distro. No checks, no install, no change to WSL.
# Usage: .\packaging\export_current_wsl.ps1  [uses INSAR_WSL_DISTRO or Ubuntu]
#        .\packaging\export_current_wsl.ps1 -Distro "Ubuntu-24.04"
# Output: dist\insar-wsl.tar

param(
    [string]$Distro = ""
)

$ErrorActionPreference = "Stop"
$ProjectRoot = if ($PSScriptRoot) { (Resolve-Path (Join-Path $PSScriptRoot "..")).Path } else { (Get-Location).Path }
$DistDir = Join-Path $ProjectRoot "dist"
$OutTar = Join-Path $DistDir "insar-wsl.tar"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Export current WSL image (pack only, no modify)" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Project: $ProjectRoot"
Write-Host "Output:  $OutTar"
Write-Host ""

$name = $null
if ($Distro -ne "") {
    $name = $Distro
    Write-Host "[OK] Using -Distro: $name"
} else {
    $envDistro = [System.Environment]::GetEnvironmentVariable("INSAR_WSL_DISTRO", "Process")
    if (-not $envDistro) { $envDistro = [System.Environment]::GetEnvironmentVariable("INSAR_WSL_DISTRO", "User") }
    if (-not $envDistro) { $envDistro = [System.Environment]::GetEnvironmentVariable("INSAR_WSL_DISTRO", "Machine") }
    if ($envDistro) { $envDistro = $envDistro.Trim() }
    if ($envDistro -and $envDistro -ne "" -and $envDistro.ToLower() -ne "default") {
        $name = $envDistro
        Write-Host "[OK] Using INSAR_WSL_DISTRO: $name"
    }
}
if (-not $name) {
    foreach ($d in @("Ubuntu", "Ubuntu-24.04", "Ubuntu-22.04")) {
        & wsl -d $d -e true 2>$null
        if ($LASTEXITCODE -eq 0) { $name = $d; Write-Host "[OK] Using distro: $name"; break }
    }
}
if (-not $name) {
    Write-Host "[ERROR] No distro. Set INSAR_WSL_DISTRO or use -Distro." -ForegroundColor Red
    wsl --list --verbose
    exit 1
}

if (-not (Test-Path $DistDir)) { New-Item -ItemType Directory -Path $DistDir -Force | Out-Null }
if (Test-Path $OutTar) { Remove-Item $OutTar -Force; Write-Host "[OK] Overwritten existing file" }
Write-Host ""
Write-Host "Exporting (wsl --export only)..." -ForegroundColor Yellow
& wsl --export $name $OutTar
if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] wsl --export failed" -ForegroundColor Red
    exit 1
}
Write-Host ""
Write-Host "Done: $OutTar" -ForegroundColor Green
$size = (Get-Item $OutTar).Length / 1GB
Write-Host "Size: $([math]::Round($size, 2)) GB"
