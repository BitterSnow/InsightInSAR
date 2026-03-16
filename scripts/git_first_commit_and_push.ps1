# 在「删除 .git\index.lock 且没有其他 git 进程」时运行此脚本
# 用法: 在项目根目录执行: .\scripts\git_first_commit_and_push.ps1
# 或: cd d:\coding\insar-system; .\scripts\git_first_commit_and_push.ps1

Set-Location $PSScriptRoot\..

if (Test-Path ".git\index.lock") {
    Write-Host "请先关闭所有使用本仓库的 Git 操作（如 Cursor 的 Git、其他终端），然后删除 .git\index.lock 再运行此脚本。" -ForegroundColor Yellow
    exit 1
}

Write-Host "Staging all files (git add -A)..." -ForegroundColor Cyan
git add -A
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "Creating initial commit..." -ForegroundColor Cyan
git commit -m "Initial commit: InSAR system (backend, desktop, ISCE2/MintPy integration)"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "Renaming branch to main..." -ForegroundColor Cyan
git branch -m main

Write-Host "Done. Next: create a Private repo on https://github.com/new, then run:" -ForegroundColor Green
Write-Host "  git remote add origin https://github.com/YOUR_USERNAME/insar-system.git" -ForegroundColor White
Write-Host "  git push -u origin main" -ForegroundColor White
Write-Host "See docs/GITHUB_PRIVATE_PUSH.md for full steps." -ForegroundColor Gray
