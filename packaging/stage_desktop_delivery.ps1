# Copy backend + scripts into dist\InSAR Desktop\ (next to exe).
# MintPy and ISCE2 run in WSL conda only - do NOT copy lib/MintPy-main or lib/isce2-main.
param(
    [string]$ProjectRoot = "",
    [string]$DesktopDir = ""
)

$ErrorActionPreference = "Stop"
if (-not $ProjectRoot -or $ProjectRoot.Trim() -eq "") {
    $ProjectRoot = if ($PSScriptRoot) { (Resolve-Path (Join-Path $PSScriptRoot "..")).Path } else { (Get-Location).Path }
}
if (-not $DesktopDir -or $DesktopDir.Trim() -eq "") {
    $DesktopDir = Join-Path $ProjectRoot "dist\InSAR Desktop"
}
$DesktopDir = (Resolve-Path -LiteralPath $DesktopDir).Path

if (-not (Test-Path (Join-Path $DesktopDir "InSAR Desktop.exe"))) {
    Write-Error "InSAR Desktop.exe not found. Run packaging\build_desktop_only.bat first."
}

Write-Host "Stage delivery into: $DesktopDir"
Write-Host "From project:      $ProjectRoot"
Write-Host ""

function Copy-Tree {
    param([string]$Src, [string]$Dst, [string]$Label)
    if (-not (Test-Path -LiteralPath $Src)) {
        Write-Host "[SKIP] $Label - missing: $Src" -ForegroundColor Yellow
        return
    }
    if (Test-Path -LiteralPath $Dst) {
        Remove-Item -LiteralPath $Dst -Recurse -Force
    }
    $parent = Split-Path $Dst -Parent
    if (-not (Test-Path -LiteralPath $parent)) {
        New-Item -ItemType Directory -Path $parent -Force | Out-Null
    }
    & robocopy $Src $Dst /E /XD __pycache__ .pytest_cache .git .mypy_cache node_modules `
        /XF *.pyc *.pyo /NFL /NDL /NJH /NJS /NC /NS | Out-Null
    if ($LASTEXITCODE -ge 8) {
        Write-Error "robocopy 失败 ($Label): exit $LASTEXITCODE"
    }
    Write-Host "[OK] $Label -> $Dst"
}

Copy-Tree (Join-Path $ProjectRoot "backend") (Join-Path $DesktopDir "backend") "backend"
Copy-Tree (Join-Path $ProjectRoot "scripts") (Join-Path $DesktopDir "scripts") "scripts"

# Remove stale lib/ from older packages (MintPy/ISCE2 live in WSL image only)
$libDir = Join-Path $DesktopDir "lib"
if (Test-Path -LiteralPath $libDir) {
    Remove-Item -LiteralPath $libDir -Recurse -Force
    Write-Host "[OK] Removed lib/ (MintPy/ISCE2 use WSL conda, not copied)"
}

foreach ($file in @("shared_models.py", "wsl_config_path.py", "cds_wsl_bridge.py")) {
    $src = Join-Path $ProjectRoot $file
    if (Test-Path -LiteralPath $src) {
        Copy-Item -LiteralPath $src -Destination (Join-Path $DesktopDir $file) -Force
        Write-Host "[OK] $file"
    }
}

$marker = Join-Path $DesktopDir "backend\scripts\run_mintpy_init_wsl.py"
if (-not (Test-Path -LiteralPath $marker)) {
    Write-Error "Delivery check failed: missing $marker"
}

Write-Host ""
Write-Host "[DONE] Staged backend + scripts (MintPy/ISCE2 in WSL only, no lib/)." -ForegroundColor Green
