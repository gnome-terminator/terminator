# build-windows-package.ps1
# ---------------------------------------------------------------------------
# Build a self-contained Terminator package using PyInstaller, bundling the
# GTK3 DLLs from the MSYS2 install. Run AFTER install-windows.ps1 has
# succeeded (so MSYS2 + GTK + deps are present).
#
#   powershell -ExecutionPolicy Bypass -File build-windows-package.ps1
#
# Output: dist\terminator\  (copy this folder anywhere; run terminator.exe)
# ---------------------------------------------------------------------------

[CmdletBinding()]
param(
    [string] $MsysRoot = "C:\msys64"
)

$ErrorActionPreference = 'Stop'
$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$MingwBin = "$MsysRoot\mingw64\bin"

function Write-Step($m){ Write-Host "`n==> $m" -ForegroundColor Cyan }
function Die($m){ Write-Host "    X : $m" -ForegroundColor Red; exit 1 }

Write-Step "Check prerequisites"
if (-not (Test-Path "$MingwBin\python3.exe")) {
    Die "MSYS2 MinGW64 python not found at $MingwBin. Run install-windows.ps1 first."
}
if (-not (Test-Path "$MingwBin\libgtk-3-0.dll")) {
    Die "GTK3 not found in $MingwBin. Re-run install-windows.ps1."
}
Write-Host "    GTK3 + python3 present"

Write-Step "Install PyInstaller (MSYS2 python3)"
& "$MsysRoot\usr\bin\bash.exe" -lc "python3 -m pip install --no-input pyinstaller"
if ($LASTEXITCODE -ne 0) { Die "pip install pyinstaller failed." }

Write-Step "Run PyInstaller (bundling GTK DLLs from $MingwBin)"
$env:GTK_BIN = $MingwBin
$drive = $RepoRoot.Substring(0,1).ToLower()
$MsysRepo = '/' + $drive + ($RepoRoot.Substring(2) -replace '\\','/')
$MsysGtkBin = '/' + $MingwBin.Substring(0,1).ToLower() + ($MingwBin.Substring(2) -replace '\\','/')
Push-Location $RepoRoot
& "$MsysRoot\usr\bin\bash.exe" -lc "cd '$MsysRepo' && GTK_BIN='$MsysGtkBin' pyinstaller packaging/terminator.spec --noconfirm"
$rc = $LASTEXITCODE
Pop-Location
if ($rc -ne 0) { Die "PyInstaller failed (exit $rc)." }

$Out = Join-Path $RepoRoot 'dist\terminator\terminator.exe'
if (Test-Path $Out) {
    Write-Host "`nDone. Self-contained package:" -ForegroundColor Green
    Write-Host "  $Out" -ForegroundColor Green
    Write-Host "Copy the whole dist\terminator\ folder to distribute.`n" -ForegroundColor Green
} else {
    Die "Build finished but $Out not found -- check output above."
}
