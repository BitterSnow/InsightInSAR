# Phase 3 verification: run backend S1 tests using ISCE2 install (Windows).
# Requires: Phase 2 done (lib/isce2-main/install/packages), MSYS2 UCRT64, conda isce2-build.
# Use the SAME conda env that was used to build ISCE2 (Anaconda or Miniconda3), else DLL load may fail.

$ProjectRoot = "d:\coding\insar-system"
$UCRT64     = "$ProjectRoot\tools\msys64\ucrt64\bin"
$CondaEnv   = "D:\env\miniconda3\envs\isce2-build"
if (-not (Test-Path "$CondaEnv\python.exe")) {
    $CondaEnv = "C:\ProgramData\Anaconda3\envs\isce2-build"
}
if (-not (Test-Path "$CondaEnv\python.exe")) {
    Write-Error "isce2-build not found. Create env with: tools\create-envs-miniconda3.bat or install to Anaconda isce2-build."
    exit 1
}

$env:Path = "$UCRT64;$CondaEnv\Library\bin;$CondaEnv\bin;" + $env:Path
$env:PYTHONPATH = "$ProjectRoot;$ProjectRoot\lib\isce2-main\install\packages"
$env:PYTHONIOENCODING = "utf-8"

Write-Host "Using Python: $CondaEnv\python.exe"
& "$CondaEnv\python.exe" -m backend.tests.test_s1_processing
exit $LASTEXITCODE
