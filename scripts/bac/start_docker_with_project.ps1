# 按「当前项目路径」启动 Docker，将该项目目录挂载为容器内 /app/project。
# 使用方式：在项目根目录执行 .\scripts\start_docker_with_project.ps1
# 当前项目路径来自：新建项目后由 API 写入的 .insar_current_project，或侧边栏选择项目后的 API 更新。

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$ConfigFile = Join-Path $ProjectRoot ".insar_current_project"

if (-not (Test-Path $ConfigFile)) {
    Write-Host "未找到当前项目配置。请先在前端「新建工程」或选择已有项目后再运行本脚本。" -ForegroundColor Yellow
    Write-Host "配置文件路径: $ConfigFile" -ForegroundColor Gray
    exit 1
}

$ProjectPath = (Get-Content $ConfigFile -Raw -Encoding UTF8).Trim()
if ([string]::IsNullOrWhiteSpace($ProjectPath)) {
    Write-Host "当前项目路径为空。请先新建或选择项目。" -ForegroundColor Yellow
    exit 1
}

if (-not (Test-Path $ProjectPath)) {
    Write-Host "项目路径不存在: $ProjectPath" -ForegroundColor Yellow
    Write-Host "请确认路径正确或重新选择项目。" -ForegroundColor Gray
    exit 1
}

Write-Host "当前项目路径: $ProjectPath" -ForegroundColor Cyan
Write-Host "正在启动 Docker（该项目将挂载为容器内 /app/project）..." -ForegroundColor Cyan

$env:PROJECT_PATH = $ProjectPath
Set-Location $ProjectRoot
docker-compose --profile full up -d

if ($LASTEXITCODE -ne 0) {
    Write-Host "Docker 启动失败。" -ForegroundColor Red
    exit $LASTEXITCODE
}

Write-Host "Docker 已启动。项目目录在容器内为 /app/project" -ForegroundColor Green
