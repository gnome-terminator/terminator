# make-offline-bundle.ps1
# ---------------------------------------------------------------------------
# Snapshot a WORKING MSYS2 + Terminator install into a portable, self-contained
# `bundle/` directory. Distribute bundle.zip to other Windows machines; they
# run install-offline.bat (written into the bundle) -- zero network, seconds.
#
# Prerequisite: run install-windows.bat FIRST on this machine so MSYS2 + GTK +
# PyGObject + pyte are already installed and working.
#
#   powershell -ExecutionPolicy Bypass -File make-offline-bundle.ps1
#   powershell -ExecutionPolicy Bypass -File make-offline-bundle.ps1 -Mode pyinstaller
#
# Modes:
#   copy         (default) brute-copy C:\msys64\mingw64 (large, ~600MB-1GB,
#                but guaranteed complete). Simplest and most robust.
#   pyinstaller  run build-windows-package.ps1 to produce dist\terminator\
#                (smaller, cleaner) and use THAT as the bundle. RECOMMENDED
#                for distribution if PyInstaller succeeds.
# ---------------------------------------------------------------------------

[CmdletBinding()]
param(
    [ValidateSet('copy','pyinstaller')] [string]$Mode = 'copy',
    [string]$MsysRoot = 'C:\msys64',
    [string]$BundleDir = 'bundle'
)

$ErrorActionPreference = 'Stop'
$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
function Step($m){ Write-Host "`n==> $m" -ForegroundColor Cyan }
function Ok($m){ Write-Host "    ok: $m" -ForegroundColor Green }
function Warn2($m){ Write-Host "    ! : $m" -ForegroundColor Yellow }
function Die($m){ Write-Host "    X : $m" -ForegroundColor Red; exit 1 }

$Bundle = Join-Path $RepoRoot $BundleDir
if (Test-Path $Bundle) { Remove-Item -Recurse -Force $Bundle }
New-Item -ItemType Directory -Path $Bundle | Out-Null

# ---------------------------------------------------------------------------
if ($Mode -eq 'pyinstaller') {
    Step "Build self-contained PyInstaller dist (recommended offline artifact)"
    & (Join-Path $RepoRoot 'build-windows-package.ps1') -MsysRoot $MsysRoot
    if ($LASTEXITCODE -ne 0) { Die "PyInstaller build failed." }
    $Src = Join-Path $RepoRoot 'dist\terminator'
    if (-not (Test-Path $Src)) { Die "dist\terminator not found after build." }
    Step "Copy PyInstaller output into $Bundle"
    & robocopy $Src (Join-Path $Bundle 'app') /E /NFL /NDL /NJH /NJS | Out-Null
    Ok "copied dist\terminator -> bundle\app"
}
else {
    Step "Snapshot MSYS2 mingw64 runtime -> bundle\runtime (this is large)"
    if (-not (Test-Path "$MsysRoot\mingw64\bin")) {
        Die "C:\msys64\mingw64 not found. Run install-windows.bat first."
    }
    # Whole-tree copy of mingw64: contains GTK DLLs, mingw python3.exe,
    # PyGObject (gi) + typelibs (lib\girepository-1.0) + pip pure-python deps
    # already in lib\python3.x\site-packages. Brute but complete.
    & robocopy "$MsysRoot\mingw64" (Join-Path $Bundle 'runtime') /E `
        /XD '__pycache__' 'pkgconfig' 'cmake' `
        /XF '*.pyc' '*.pyo' '*.a' '*.la' /NFL /NDL /NJH /NJS | Out-Null
    Ok "snapshotted mingw64 -> bundle\runtime"

    Step "Copy Terminator source -> bundle\app"
    & robocopy $RepoRoot (Join-Path $Bundle 'app') /E `
        /XD '.git' 'build' 'dist' 'bundle' '.claude' '__pycache__' 'po' `
        /XF '*.pyc' '*.pyo' /NFL /NDL /NJH /NJS | Out-Null
    Ok "copied source -> bundle\app"
}

# ---------------------------------------------------------------------------
# Write the per-bundle launcher (run.bat) and offline installer.
Step "Write bundle\run.bat and bundle\install-offline.bat"
$AppDir = Join-Path $Bundle 'app'

if ($Mode -eq 'pyinstaller') {
    # PyInstaller dist: single exe, self-contained.
    $runBat = @"
@echo off
cd /d "%~dp0app"
terminator.exe
pause
"@
}
else {
    # copy mode: run bundled mingw python against bundled source.
    $runBat = @"
@echo off
set PATH=%~dp0runtime\bin;%PATH%
set GI_TYPELIB_PATH=%~dp0runtime\lib\girepository-1.0
cd /d "%~dp0app"
runtime\bin\python3.exe terminator
pause
"@
}
Set-Content -Path (Join-Path $Bundle 'run.bat') -Value $runBat -Encoding ASCII

# install-offline.bat: copies this bundle to %LOCALAPPDATA%\Terminator and
# creates a desktop + start-menu shortcut. Zero network.
$installBat = @"
@echo off
setlocal
set DEST=%LOCALAPPDATA%\Terminator
echo Installing Terminator to %DEST% ...
if not exist "%DEST%" mkdir "%DEST%"
xcopy "%~dp0*" "%DEST%\" /E /I /Y /Q
rem --- Install bundled DejaVu Sans Mono (Ubuntu-like monospace) into the
rem --- per-user font dir; fontconfig scans WINDOWSUSERFONTDIR, no admin needed.
set FONTDIR=%LOCALAPPDATA%\Microsoft\Windows\Fonts
if not exist "%FONTDIR%" mkdir "%FONTDIR%"
copy /Y "%DEST%\app\data\fonts\DejaVuSansMono.ttf" "%FONTDIR%\" >nul 2>nul
copy /Y "%DEST%\app\data\fonts\DejaVuSansMono-Bold.ttf" "%FONTDIR%\" >nul 2>nul
if exist "%DEST%\runtime\bin\fc-cache.exe" "%DEST%\runtime\bin\fc-cache.exe" -f >nul 2>nul
powershell -NoProfile -Command ^
  "$$ws = New-Object -ComObject WScript.Shell; " ^
  "$$lnk = $$ws.CreateShortcut([Environment]::GetFolderPath('Desktop') + '\Terminator.lnk'); " ^
  "$$lnk.TargetPath = '%DEST%\run.bat'; " ^
  "$$lnk.WorkingDirectory = '%DEST%'; " ^
  "$$lnk.IconLocation = '%DEST%\app\data\icons\hicolor\48x48\apps\terminator.png'; " ^
  "$$lnk.Save(); " ^
  "$$sm = [Environment]::GetFolderPath('Programs'); " ^
  "$$lnk2 = $$ws.CreateShortcut($$sm + '\Terminator.lnk'); " ^
  "$$lnk2.TargetPath = '%DEST%\run.bat'; " ^
  "$$lnk2.WorkingDirectory = '%DEST%'; " ^
  "$$lnk2.Save()"
echo Done. Use the desktop "Terminator" icon.
pause
endlocal
"@
Set-Content -Path (Join-Path $Bundle 'install-offline.bat') -Value $installBat -Encoding ASCII
Ok "wrote bundle\run.bat and bundle\install-offline.bat"

Write-Host "`nBundle ready: $Bundle" -ForegroundColor Green
if ($Mode -eq 'pyinstaller') {
    Write-Host "Distribute bundle\ (small). Users run install-offline.bat." -ForegroundColor Green
} else {
    Write-Host "Distribute bundle.zip (~hundreds of MB). Users run install-offline.bat." -ForegroundColor Green
    Write-Host "(For a smaller bundle, re-run with -Mode pyinstaller once PyInstaller works.)" -ForegroundColor Yellow
}
