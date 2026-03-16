# Run topo for first burst only; then open geom_reference/IW1 in QGIS.
# Python env matches backend/Step1 (PATH, PYTHONPATH, ISCE2).
#
# Usage: .\scripts\run_topo_burst1_only.ps1
#        .\scripts\run_topo_burst1_only.ps1 -WorkDir "D:\processing\tianfu\processing"

param(
    [string]$WorkDir = "D:\processing\tianfu\processing"
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

# Python exe (same as backend _get_stack_python_exe)
$python = $env:ISCE2_PYTHON
if (-not $python -or -not (Test-Path -LiteralPath $python)) {
    $python = "D:\env\miniconda3\envs\isce2-build\python.exe"
}
if (-not (Test-Path -LiteralPath $python)) {
    $python = "C:\ProgramData\Anaconda3\envs\isce2-build\python.exe"
}
if (-not (Test-Path -LiteralPath $python)) {
    Write-Host "[ERROR] Python not found. Set ISCE2_PYTHON or use isce2-build conda env."
    exit 1
}

# Work dir and config
if (-not (Test-Path -LiteralPath $WorkDir)) {
    $alt = Join-Path $root "processing_check"
    if (Test-Path -LiteralPath $alt) { $WorkDir = $alt }
}
if (-not (Test-Path -LiteralPath $WorkDir)) {
    Write-Host "Work dir not found: $WorkDir"
    exit 1
}

$configPath = Join-Path $WorkDir "configs\config_reference"
if (-not (Test-Path -LiteralPath $configPath)) {
    Write-Host "config_reference not found: $configPath"
    exit 1
}

# Parse config: find topo block, get reference / dem / geom_referenceDir
$lines = Get-Content -LiteralPath $configPath -Encoding UTF8
$inSection = $false
$inTopo = $false
$reference = $dem = $geomRef = ""

foreach ($line in $lines) {
    if ($line -match '^\s*\[Function-\d+\]\s*$') {
        $inSection = $true
        $inTopo = $false
        continue
    }
    if (-not $inSection) { continue }
    if ($line -match '^\s*topo\s*:\s*') {
        $inTopo = $true
        continue
    }
    if (-not $inTopo) { continue }
    if ($line -match '^\s*reference\s*:\s*(.+)$') {
        $reference = $Matches[1].Trim()
        continue
    }
    if ($line -match '^\s*dem\s*:\s*(.+)$') {
        $dem = $Matches[1].Trim()
        continue
    }
    if ($line -match '^\s*geom_referenceDir\s*:\s*(.+)$') {
        $geomRef = $Matches[1].Trim()
        continue
    }
}

if (-not $reference -or -not $dem -or -not $geomRef) {
    Write-Host "config_reference topo block missing reference/dem/geom_referenceDir"
    exit 1
}

# Resolve relative paths against WorkDir
if (-not [System.IO.Path]::IsPathRooted($reference)) {
    $reference = Join-Path $WorkDir $reference
}
if (-not [System.IO.Path]::IsPathRooted($dem)) {
    $dem = Join-Path $WorkDir $dem
}
if (-not [System.IO.Path]::IsPathRooted($geomRef)) {
    $geomRef = Join-Path $WorkDir $geomRef
}

$reference = [System.IO.Path]::GetFullPath($reference)
if (-not (Test-Path -LiteralPath $reference) -or -not (Get-Item -LiteralPath $reference).PSIsContainer) {
    Write-Host "reference dir not found: $reference"
    exit 1
}
if (-not (Test-Path -LiteralPath $dem) -and -not (Test-Path -LiteralPath ($dem + ".xml"))) {
    Write-Host "dem not found: $dem"
    exit 1
}

# Build PATH / PYTHONPATH same as backend _get_stack_env
$isceRoot = Join-Path $root "lib\isce2-main"
$installPackages = Join-Path $isceRoot "install\packages"
$topsStack = Join-Path $isceRoot "contrib\stack\topsStack"
$contribStack = Join-Path $isceRoot "contrib\stack"
$topoPy = Join-Path $topsStack "topo.py"

if (-not (Test-Path -LiteralPath $topoPy)) {
    Write-Host "topo.py not found: $topoPy"
    exit 1
}

$condaBin = Split-Path -Parent $python
$condaLib = Join-Path $condaBin "Library\bin"
$ucrt64 = $env:INSAR_UCRT64_BIN
if (-not $ucrt64 -or -not (Test-Path -LiteralPath $ucrt64)) {
    $ucrt64 = Join-Path $root "tools\msys64\ucrt64\bin"
}
$pathParts = @()
if (Test-Path -LiteralPath $ucrt64) { $pathParts += $ucrt64 }
$pathParts += $condaLib
$pathParts += $condaBin

$isceDllDirs = @()
if (Test-Path -LiteralPath $installPackages) {
    $stdotel = Join-Path $installPackages "isce\components\iscesys\StdOEL"
    $pydDirs = [System.Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
    if (Test-Path -LiteralPath $stdotel) { [void]$pydDirs.Add($stdotel) }
    Get-ChildItem -Path $installPackages -Recurse -File -ErrorAction SilentlyContinue |
        Where-Object { $_.Extension -match '\.(pyd|dll)$' } |
        ForEach-Object { [void]$pydDirs.Add($_.DirectoryName) }
    $isceDllDirs = $pydDirs | Sort-Object
    $pathParts += $isceDllDirs
}
$sysRoot = $env:SystemRoot
if (-not $sysRoot) { $sysRoot = "C:\Windows" }
$pathParts += Join-Path $sysRoot "system32"
$pathParts += $sysRoot
$env:PATH = ($pathParts | Select-Object -Unique) -join [System.IO.Path]::PathSeparator

$isce2Env = Join-Path $root "backend\_isce2_env"
$pp = @()
if (Test-Path -LiteralPath $isce2Env) { $pp += $isce2Env }
$pp += $isceRoot
$pp += $root
if (Test-Path -LiteralPath $installPackages) { $pp += $installPackages }
$pp += $topsStack
$pp += $contribStack
$env:PYTHONPATH = ($pp | Select-Object -Unique) -join [System.IO.Path]::PathSeparator

$env:INSAR_PROJECT_ROOT = $root
$env:PYTHONUNBUFFERED = "1"
$env:PYTHONIOENCODING = "utf-8"
if (-not $env:INSAR_DLL_DIRS) {
    $dllDirs = @($ucrt64) + $isceDllDirs | Where-Object { $_ }
    $env:INSAR_DLL_DIRS = ($dllDirs | Select-Object -Unique) -join [System.IO.Path]::PathSeparator
}

# Run topo.py for burst 1 only
Write-Host "Running topo for first burst only (a few minutes)."
Write-Host "Python: $python"
Write-Host "WorkDir: $WorkDir"
Write-Host ""

& $python $topoPy -m $reference -d $dem -g $geomRef -b 1 -n 1
if ($LASTEXITCODE -ne 0) {
    Write-Host "topo exit code: $LASTEXITCODE"
    exit $LASTEXITCODE
}

$iw1 = Join-Path $geomRef "IW1"
Write-Host ""
Write-Host "Done. Open in QGIS:"
$vrtNames = @("hgt_01.rdr.vrt", "lat_01.rdr.vrt", "lon_01.rdr.vrt")
foreach ($name in $vrtNames) {
    $p = Join-Path $iw1 $name
    if (Test-Path -LiteralPath $p) { Write-Host "  $p" }
}
