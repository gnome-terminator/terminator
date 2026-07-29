# install-windows.ps1
# ---------------------------------------------------------------------------
# One-click bootstrap for Terminator on Windows.
#
# Run by double-clicking install-windows.bat (which calls this script with
# execution policy bypassed), or from PowerShell:
#     powershell -ExecutionPolicy Bypass -File install-windows.ps1
#
# What it does:
#   1. Ensures winget is available.
#   2. Installs Python 3.10 (if missing) via winget.
#   3. Installs MSYS2 (if missing) via winget -- to C:\msys64.
#   4. Uses MSYS2 pacman to install GTK3 + PyGObject bindings.
#   5. pip-installs Terminator's Python deps inside MSYS2's python3.
#   6. Runs `python setup.py --without-gettext install`.
#   7. Writes run-windows.bat (with the detected paths baked in).
#   8. Creates a desktop shortcut "Terminator" that launches it.
#   9. Optionally launches (-Launch).
#
# Notes / honesty:
#   * winget / pacman run with --noconfirm-style flags but the FIRST winget
#     call may still show a one-time source-agreement prompt.
#   * pywin32 has no MSYS2 wheel; the named-pipe single-instance IPC will
#     degrade (the app still runs -- see docs/WINDOWS-安装使用指南.md).
#   * Building a fully self-contained, zero-dependency .exe needs a second
#     step: build-windows-package.ps1 (run AFTER this one succeeds).
# ---------------------------------------------------------------------------

[CmdletBinding()]
param(
    [switch] $Launch,
    [string] $MsysRoot = "C:\msys64"
)

$ErrorActionPreference = 'Stop'
$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path

function Write-Step($msg)  { Write-Host "`n==> $msg" -ForegroundColor Cyan }
function Write-Ok($msg)    { Write-Host "    ok: $msg" -ForegroundColor Green }
function Write-Warn2($msg) { Write-Host "    ! : $msg" -ForegroundColor Yellow }
function Die($msg)         { Write-Host "    X : $msg" -ForegroundColor Red; exit 1 }

function Ensure-Command($name) {
    return [bool](Get-Command $name -ErrorAction SilentlyContinue)
}

function Winget-Install($id) {
    Write-Host "    winget install --id $id -e --silent"
    winget install --id $id -e --silent --accept-source-agreements --accept-package-agreements 2>$null
}

# ---- 1. winget -------------------------------------------------------------
Write-Step "Check winget (App Installer)"
if (-not (Ensure-Command 'winget')) {
    Die "winget not found. Open Microsoft Store, update 'App Installer', then re-run."
}
Write-Ok "winget available"

# ---- 2. Python -------------------------------------------------------------
Write-Step "Check Python 3"
$needPy = -not (Ensure-Command 'python') -and -not (Ensure-Command 'python3')
if ($needPy) {
    Winget-Install "Python.Python.3.10"
    # Refresh PATH for this session from the registry (machine + user).
    $env:Path = [System.Environment]::GetEnvironmentVariable('Path','Machine') + ';' + `
                [System.Environment]::GetEnvironmentVariable('Path','User')
}
Write-Ok "Python present"

# ---- 3. MSYS2 --------------------------------------------------------------
Write-Step "Check MSYS2 at $MsysRoot"
if (-not (Test-Path "$MsysRoot\usr\bin\bash.exe")) {
    Winget-Install "MSYS2.MSYS2"
    if (-not (Test-Path "$MsysRoot\usr\bin\bash.exe")) {
        Die "MSYS2 did not install to $MsysRoot. Install manually from https://www.msys2.org/ then re-run."
    }
}
$Bash = "$MsysRoot\usr\bin\bash.exe"
Write-Ok "MSYS2 bash: $Bash"

# ---- 4. GTK3 + bindings via pacman ----------------------------------------
Write-Step "Install GTK3 + PyGObject via MSYS2 pacman (this can take a few minutes)"
$pkgArgs = "pacman -S --noconfirm --needed " + `
    "mingw-w64-x86_64-gtk3 " + `
    "mingw-w64-x86_64-python3 " + `
    "mingw-w64-x86_64-python3-gobject " + `
    "mingw-w64-x86_64-cairo " + `
    "mingw-w64-x86_64-pango " + `
    "mingw-w64-x86_64-python3-pip " + `
    "mingw-w64-x86_64-python3-psutil"
& $Bash -lc $pkgArgs
if ($LASTEXITCODE -ne 0) { Die "pacman install failed (exit $LASTEXITCODE)." }
Write-Ok "GTK3 + bindings installed"

# ---- 5. Python deps (pyte, configobj, pytest) -----------------------------
Write-Step "pip install Terminator Python deps"
& $Bash -lc "python3 -m pip install --upgrade pip && python3 -m pip install --no-input pyte configobj pytest"
if ($LASTEXITCODE -ne 0) { Write-Warn2 "pip deps install had issues; continuing." }
# pywin32 has no MSYS2 wheel -- single-instance IPC degrades; not fatal.
Write-Warn2 "pywin32 unavailable under MSYS2 -> named-pipe single-instance disabled (app still runs)"

# ---- 6. setup.py install (best-effort; run-windows.bat runs from source) --
Write-Step "Install Terminator (setup.py --without-gettext)"
# Convert the Windows repo path to an MSYS2 path (C:\a\b -> /c/a/b).
$drive = $RepoRoot.Substring(0,1).ToLower()
$MsysRepo = '/' + $drive + ($RepoRoot.Substring(2) -replace '\\','/')
& $Bash -lc "cd '$MsysRepo' && python3 setup.py --without-gettext install"
if ($LASTEXITCODE -ne 0) {
    Write-Warn2 "setup.py install failed (Python 3.12+ removed distutils). Trying pip install."
    & $Bash -lc "cd '$MsysRepo' && python3 -m pip install . --no-build-isolation"
    if ($LASTEXITCODE -ne 0) {
        Write-Warn2 "pip install also failed; will run from source via run-windows.bat."
    }
}
Write-Ok "install step done (or running from source)"

# ---- 7. Write run-windows.bat ---------------------------------------------
Write-Step "Write run-windows.bat"
$RunBat = Join-Path $RepoRoot 'run-windows.bat'
$MingwBin = "$MsysRoot\mingw64\bin"
$PyExe = "$MingwBin\python3.exe"
$bat = @(
    "@echo off",
    "set PATH=$MingwBin;%PATH%",
    "cd /d `"$RepoRoot`"",
    "`"$PyExe`" terminator",
    "pause"
) -join "`r`n"
Set-Content -Path $RunBat -Value $bat -Encoding ASCII
Write-Ok "wrote $RunBat"

# ---- 8. Desktop shortcut ---------------------------------------------------
Write-Step "Create desktop shortcut"
try {
    $Desktop = [Environment]::GetFolderPath('Desktop')
    $Lnk = Join-Path $Desktop 'Terminator.lnk'
    $ws = New-Object -ComObject WScript.Shell
    $sc = $ws.CreateShortcut($Lnk)
    $sc.TargetPath = $RunBat
    $sc.WorkingDirectory = $RepoRoot
    $sc.IconLocation = Join-Path $RepoRoot 'data\icons\hicolor\48x48\apps\terminator.png'
    $sc.Description = 'Terminator terminal'
    $sc.Save()
    Write-Ok "shortcut: $Lnk"
} catch {
    Write-Warn2 "could not create desktop shortcut: $_"
}

# ---- done -----------------------------------------------------------------
Write-Host "`nDone. Launch with:" -ForegroundColor Green
Write-Host "  - Double-click the 'Terminator' desktop icon, or" -ForegroundColor Green
Write-Host "  - Double-click run-windows.bat in: $RepoRoot" -ForegroundColor Green
Write-Host "Default shell is PowerShell; set custom_command in %APPDATA%\terminator\config for cmd/wsl.`n" -ForegroundColor Green

if ($Launch) { & $RunBat }
