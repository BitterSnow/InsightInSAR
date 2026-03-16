# 推送 insar-system 到 GitHub（建议在「非 Cursor」的 PowerShell 中运行，避免 index.lock 冲突）
# 用法：在资源管理器中右键「使用 PowerShell 打开」到项目根目录，或：
#   cd d:\coding\insar-system
#   .\scripts\push_to_github.ps1

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\..

$lockPath = ".git\index.lock"
if (Test-Path $lockPath) {
    Write-Host "Removing .git\index.lock ..." -ForegroundColor Yellow
    Remove-Item $lockPath -Force -ErrorAction SilentlyContinue
    if (Test-Path $lockPath) {
        Write-Host "Lock file in use. Please close Cursor (or Source Control view), delete .git\index.lock manually, then run this script again from Explorer." -ForegroundColor Red
        exit 1
    }
}

Write-Host "git add -A ..." -ForegroundColor Cyan
git add -A
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$status = git status -s
if (-not $status) {
    Write-Host "没有需要提交的变更；若尚未有过提交，请检查 .gitignore。" -ForegroundColor Yellow
    exit 0
}

Write-Host "git commit ..." -ForegroundColor Cyan
git commit -m 'Initial commit: InSAR system (backend, desktop, ISCE2 install)'
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$branch = git rev-parse --abbrev-ref HEAD
if ($branch -eq "master") {
    Write-Host "重命名分支 master -> main ..." -ForegroundColor Cyan
    git branch -m main
}

$remote = git remote get-url origin 2>$null
if (-not $remote) {
    Write-Host ""
    Write-Host "尚未添加远程仓库。请先在 GitHub 创建私有空仓库，然后执行：" -ForegroundColor Green
    Write-Host "  git remote add origin https://github.com/你的用户名/insar-system.git" -ForegroundColor White
    Write-Host "  git push -u origin main" -ForegroundColor White
    exit 0
}

Write-Host "git push -u origin main ..." -ForegroundColor Cyan
git push -u origin main
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host "Push done." -ForegroundColor Green
