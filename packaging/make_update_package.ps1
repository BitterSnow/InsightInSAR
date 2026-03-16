# 生成“少量更新包”ZIP：供 InSAR WSL Deploy Wizard 的「仅更新配置」一键覆盖 backend/lib/scripts。
# 输出：dist/insar-update-YYYYMMDD-HHMM.zip

param(
    # 输出目录（默认项目 dist）
    [string]$OutDir = "",
    # 仅打包 backend/scripts/lib（MintPy src + isce2 contrib + isce2 applications）
    [switch]$Minimal = $true
)

$ErrorActionPreference = "Stop"
$ProjectRoot = if ($PSScriptRoot) { (Resolve-Path (Join-Path $PSScriptRoot "..")).Path } else { (Get-Location).Path }
if (-not $OutDir -or $OutDir.Trim() -eq "") {
    $OutDir = Join-Path $ProjectRoot "dist"
}
$Stage = Join-Path $OutDir "insar-update"

if (Test-Path $Stage) { Remove-Item $Stage -Recurse -Force }
New-Item -ItemType Directory -Path $Stage | Out-Null

Write-Host "Project: $ProjectRoot"
Write-Host "Stage:   $Stage"
Write-Host ""

Copy-Item -Recurse -Force (Join-Path $ProjectRoot "backend") (Join-Path $Stage "backend")
Copy-Item -Recurse -Force (Join-Path $ProjectRoot "scripts") (Join-Path $Stage "scripts")

New-Item -ItemType Directory -Path (Join-Path $Stage "lib") | Out-Null

# MintPy（仅 src）
$mintpySrc = Join-Path $ProjectRoot "lib\MintPy-main\src"
if (Test-Path $mintpySrc) {
    New-Item -ItemType Directory -Path (Join-Path $Stage "lib\MintPy-main") -Force | Out-Null
    Copy-Item -Recurse -Force $mintpySrc (Join-Path $Stage "lib\MintPy-main\src")
    Write-Host "[OK] Added MintPy src"
} else {
    Write-Host "[WARN] Missing lib\\MintPy-main\\src (skip)"
}

# ISCE2（仅 contrib + applications）
$isceContrib = Join-Path $ProjectRoot "lib\isce2-main\contrib"
$isceApps = Join-Path $ProjectRoot "lib\isce2-main\applications"
if (Test-Path $isceContrib -or (Test-Path $isceApps)) {
    New-Item -ItemType Directory -Path (Join-Path $Stage "lib\isce2-main") -Force | Out-Null
    if (Test-Path $isceContrib) {
        Copy-Item -Recurse -Force $isceContrib (Join-Path $Stage "lib\isce2-main\contrib")
        Write-Host "[OK] Added ISCE2 contrib"
    } else {
        Write-Host "[WARN] Missing lib\\isce2-main\\contrib (skip)"
    }
    if (Test-Path $isceApps) {
        Copy-Item -Recurse -Force $isceApps (Join-Path $Stage "lib\isce2-main\applications")
        Write-Host "[OK] Added ISCE2 applications"
    } else {
        Write-Host "[WARN] Missing lib\\isce2-main\\applications (skip)"
    }
} else {
    Write-Host "[WARN] Missing lib\\isce2-main (skip)"
}

$zipName = "insar-update-" + (Get-Date -Format "yyyyMMdd-HHmm") + ".zip"
$zipPath = Join-Path $OutDir $zipName
if (Test-Path $zipPath) { Remove-Item $zipPath -Force }

Compress-Archive -Path (Join-Path $Stage "*") -DestinationPath $zipPath -Force
Write-Host ""
Write-Host ("[DONE] " + $zipPath) -ForegroundColor Green

