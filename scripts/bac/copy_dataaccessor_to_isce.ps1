# Copy the newly built DataAccessor.pyd from packages/isce2 to packages/isce
# so that "import isce" (used by topsStack/topo) loads the binary-mode fix.
# Run this after: cmake --install lib\isce2-main\build --prefix lib\isce2-main\install
# If destination is in use: copy to DataAccessor_new.pyd, then rename so new process loads the new .pyd.

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$dirIsce = Join-Path $root "lib\isce2-main\install\packages\isce\components\iscesys\ImageApi"
$src     = Join-Path $root "lib\isce2-main\install\packages\isce2\components\iscesys\ImageApi\DataAccessor.pyd"
$dst     = Join-Path $dirIsce "DataAccessor.pyd"
$dstNew  = Join-Path $dirIsce "DataAccessor_new.pyd"
$dstBak  = Join-Path $dirIsce "DataAccessor.pyd.bak"

if (-not (Test-Path $src)) {
    Write-Error "Source not found: $src"
}

# Copy to a new file (avoids "file in use" on destination)
Copy-Item -Path $src -Destination $dstNew -Force
Write-Host "Copied to DataAccessor_new.pyd."

# Replace: rename current .pyd to .bak (or .pyd.old if .bak in use), then rename _new to .pyd
# Remove existing .bak and .old so Rename-Item target does not exist (avoid "file already exists")
$dstOld = Join-Path $dirIsce "DataAccessor.pyd.old"
Remove-Item $dstBak -Force -ErrorAction SilentlyContinue
Remove-Item $dstOld -Force -ErrorAction SilentlyContinue

if (Test-Path $dst) {
    try {
        Rename-Item -Path $dst -NewName "DataAccessor.pyd.bak" -Force -ErrorAction Stop
        Write-Host "Renamed existing DataAccessor.pyd to DataAccessor.pyd.bak"
    } catch {
        try {
            Copy-Item -Path $src -Destination $dst -Force -ErrorAction Stop
            Remove-Item $dstNew -Force -ErrorAction SilentlyContinue
            Write-Host "Overwrote DataAccessor.pyd in place (old .pyd was in use, replace succeeded)."
        } catch {
            Write-Warning "Could not rename or overwrite DataAccessor.pyd (file in use). DataAccessor_new.pyd is the new build. Close all Python/IDE that use isce, then run this script again, or manually replace DataAccessor.pyd with DataAccessor_new.pyd after closing processes."
            exit 1
        }
    }
}
if (Test-Path $dstNew) {
    Rename-Item -Path $dstNew -NewName "DataAccessor.pyd" -Force
    Write-Host "Renamed DataAccessor_new.pyd to DataAccessor.pyd. Runtime will use the binary-mode fix."
}

# Also copy topozero.pyd so "import isce" loads the rebuilt topozero (Fortran debug, etc.)
$dirTopoIsce  = Join-Path $root "lib\isce2-main\install\packages\isce\components\zerodop\topozero"
$dirTopoIsce2 = Join-Path $root "lib\isce2-main\install\packages\isce2\components\zerodop\topozero"
$srcTopo      = Join-Path $dirTopoIsce2 "topozero.pyd"
$dstTopo     = Join-Path $dirTopoIsce "topozero.pyd"
if (Test-Path $srcTopo) {
    $dstTopoNew = Join-Path $dirTopoIsce "topozero_new.pyd"
    Copy-Item -Path $srcTopo -Destination $dstTopoNew -Force
    if (Test-Path $dstTopo) {
        $dstTopoBak = Join-Path $dirTopoIsce "topozero.pyd.bak"
        Remove-Item $dstTopoBak -Force -ErrorAction SilentlyContinue
        if (Test-Path $dstTopoBak) {
            $dstTopoOld = Join-Path $dirTopoIsce "topozero.pyd.old"
            Remove-Item $dstTopoOld -Force -ErrorAction SilentlyContinue
            Rename-Item -Path $dstTopo -NewName "topozero.pyd.old" -Force
        } else {
            Rename-Item -Path $dstTopo -NewName "topozero.pyd.bak" -Force
        }
    }
    Rename-Item -Path $dstTopoNew -NewName "topozero.pyd" -Force
    Write-Host "Copied topozero.pyd to packages/isce (Fortran debug prints will appear when topo runs)."
}
