# 在**有网络的 Windows 构建机**上运行，用于导出 WSL 镜像 insar-wsl.tar，便于拷贝到离线环境部署。
# 用法：在项目根目录执行 .\packaging\export_wsl_image.ps1  [-Force]
# 或： cd d:\coding\insar-system; .\packaging\export_wsl_image.ps1 -Force
# 前置：已安装 WSL2 与 Ubuntu（如 Microsoft Store 安装 Ubuntu 24.04）。
# 输出：dist\insar-wsl.tar（与 Desktop/向导 同级的交付物，整份 dist 可拷贝到离线机）。

param([switch]$Force)

$ErrorActionPreference = "Stop"
$ProjectRoot = if ($PSScriptRoot) { (Resolve-Path (Join-Path $PSScriptRoot "..")).Path } else { Get-Location }
$DistDir = Join-Path $ProjectRoot "dist"
$OutTar = Join-Path $DistDir "insar-wsl.tar"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "InSAR WSL 镜像导出（供离线部署）" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "项目根: $ProjectRoot"
Write-Host "输出:   $OutTar"
Write-Host ""

# 1. 检查 wsl
try {
    $null = wsl --list --quiet 2>&1
} catch {
    Write-Host "[ERROR] 未找到 wsl 命令。请先启用「适用于 Linux 的 Windows 子系统」并安装 Ubuntu。" -ForegroundColor Red
    exit 1
}

# 2. 确定要使用的发行版（Ubuntu / Ubuntu-24.04 / Ubuntu-22.04）
$Distro = $null
foreach ($d in @("Ubuntu", "Ubuntu-24.04", "Ubuntu-22.04")) {
    $r = & wsl -d $d -e true 2>$null
    if ($LASTEXITCODE -eq 0) { $Distro = $d; break }
}
if (-not $Distro) {
    Write-Host "[ERROR] 未找到可用的 Ubuntu 发行版。请从 Microsoft Store 安装 Ubuntu 或 Ubuntu 24.04。" -ForegroundColor Red
    exit 1
}
Write-Host "[OK] 使用 WSL 发行版: $Distro"

# 3. 将项目根转为 WSL 路径，供 WSL 内执行脚本
$WslProjectRoot = (wsl -d $Distro -e wslpath -a $ProjectRoot 2>$null) | Where-Object { $_ }
if (-not $WslProjectRoot) {
    Write-Host "[ERROR] 无法将项目路径转为 WSL 路径: $ProjectRoot" -ForegroundColor Red
    exit 1
}
Write-Host "[OK] WSL 项目路径: $WslProjectRoot"

# 4. 在 WSL 内检查/安装 ISCE2+MintPy 环境（需要网络）
Write-Host ""
Write-Host "在 WSL 内检查并配置 ISCE2 + MintPy（若未配置将自动安装，需联网）..." -ForegroundColor Yellow
$Cmd = "cd '$WslProjectRoot' && bash scripts/wsl/ensure_env.sh"
$r = & wsl -d $Distro -e bash -c $Cmd 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "[WARN] WSL 内环境检查/安装返回非零，继续尝试导出。若导入后无法使用，请在 WSL 内手动运行: bash scripts/wsl/setup_isce2_ubuntu24.sh" -ForegroundColor Yellow
} else {
    Write-Host "[OK] WSL 环境就绪"
}

# 5. 导出
if (-not (Test-Path $DistDir)) { New-Item -ItemType Directory -Path $DistDir -Force | Out-Null }
if (Test-Path $OutTar) {
    if (-not $Force) {
        Write-Host ""
        $overwrite = Read-Host "已存在 $OutTar，是否覆盖? (y/N)"
        if ($overwrite -ne "y" -and $overwrite -ne "Y") {
            Write-Host "已取消。"
            exit 0
        }
    }
    Remove-Item $OutTar -Force
    Write-Host "[OK] 已删除旧文件，将重新导出"
}
Write-Host ""
Write-Host "正在导出 WSL 镜像（可能需数分钟）..." -ForegroundColor Yellow
& wsl --export $Distro $OutTar
if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] wsl --export 失败" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "导出完成: $OutTar" -ForegroundColor Green
Write-Host "可将 dist 目录整份拷贝到离线环境："
Write-Host "  - dist\InSAR Desktop\          (主程序)"
Write-Host "  - dist\InSAR WSL Deploy Wizard\ (部署向导)"
Write-Host "  - dist\insar-wsl.tar            (WSL 镜像)"
Write-Host "离线机上先运行「InSAR WSL Deploy Wizard」选择 insar-wsl.tar 导入，再运行 Desktop。"
