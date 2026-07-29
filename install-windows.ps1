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
$MingwBin = "$MsysRoot\mingw64\bin"

# ---- 4. GTK3 + bindings via pacman ----------------------------------------
# A fresh winget MSYS2 has NEVER synced its package DB, so every package is
# "target not found" until we run -Sy. MSYS2 also renamed python3-* -> python-*,
# so we try both names and take whichever resolves.
Write-Step "Sync MSYS2 package database (pacman -Sy)"
& $Bash -lc "pacman -Sy --noconfirm --overwrite '*'"
if ($LASTEXITCODE -ne 0) { Write-Warn2 "pacman -Sy had a non-zero exit; continuing anyway." }

function Install-Pkg([string[]]$candidates) {
    foreach ($name in $candidates) {
        & $Bash -lc "pacman -S --noconfirm --needed --overwrite '*' $name" 2>$null
        if ($LASTEXITCODE -eq 0) { Write-Ok $name; return $true }
    }
    Write-Warn2 ("not found (tried: " + ($candidates -join ', ') + ")")
    return $false
}

Write-Step "Install GTK3 + PyGObject via pacman (this can take a few minutes)"
[void](Install-Pkg @('mingw-w64-x86_64-gtk3'))
[void](Install-Pkg @('mingw-w64-x86_64-gobject-introspection','mingw-w64-x86_64-gobject-introspection-runtime'))
$pyOk     = Install-Pkg @('mingw-w64-x86_64-python','mingw-w64-x86_64-python3')
$gobjOk   = Install-Pkg @('mingw-w64-x86_64-python-gobject','mingw-w64-x86_64-python3-gobject')
$cairoOk  = Install-Pkg @('mingw-w64-x86_64-python-cairo','mingw-w64-x86_64-python3-cairo')
$psutilOk = Install-Pkg @('mingw-w64-x86_64-python-psutil','mingw-w64-x86_64-python3-psutil')
[void](Install-Pkg @('mingw-w64-x86_64-python-pip','mingw-w64-x86_64-python3-pip'))

# Detect which python executable the install produced (python3.exe or python.exe).
$PyExe = $null
if (Test-Path "$MingwBin\python3.exe")      { $PyExe = 'python3' }
elseif (Test-Path "$MingwBin\python.exe")   { $PyExe = 'python' }
else {
    Die "No mingw python found in $MingwBin after pacman install (python package failed)."
}
Write-Ok "python executable: $PyExe"

if (-not $gobjOk) {
    Die "python-gobject (PyGObject / 'gi') could not be installed -- the GUI cannot start. " + `
        "Open the MSYS2 'MinGW64' shell, run: pacman -Syu, then pacman -S mingw-w64-x86_64-python-gobject, then re-run this script."
}

# ---- 5. Python deps (pure-Python ones via pip) ----------------------------
# NOTE: PyPI binary wheels (psutil, pycairo) do NOT work with MSYS2's mingw
# python (ABI mismatch) -- those must come from pacman (step 4). Only
# pure-Python packages are pip-installed here.
Write-Step "pip install pure-Python Terminator deps (pyte, configobj)"
& $Bash -lc "$PyExe -m pip install --no-input --upgrade pip pyte configobj"
if ($LASTEXITCODE -ne 0) { Write-Warn2 "pip deps install had issues; continuing." }
if (-not $psutilOk) {
    Write-Warn2 "python-psutil not installed from pacman; trying pip (may fail to build)."
    & $Bash -lc "$PyExe -m pip install --no-input psutil" 2>$null
}
# pywin32 has no MSYS2 wheel -- named-pipe single-instance IPC degrades.
Write-Warn2 "pywin32 unavailable under MSYS2 -> single-instance IPC disabled (app still runs)"

# ---- 6. setup.py install (best-effort; run-windows.bat runs from source) --
Write-Step "Install Terminator (setup.py --without-gettext)"
# Convert the Windows repo path to an MSYS2 path (C:\a\b -> /c/a/b).
$drive = $RepoRoot.Substring(0,1).ToLower()
$MsysRepo = '/' + $drive + ($RepoRoot.Substring(2) -replace '\\','/')
& $Bash -lc "cd '$MsysRepo' && $PyExe setup.py --without-gettext install"
if ($LASTEXITCODE -ne 0) {
    Write-Warn2 "setup.py install failed (Python 3.12+ removed distutils). Trying pip install."
    & $Bash -lc "cd '$MsysRepo' && $PyExe -m pip install . --no-build-isolation"
    if ($LASTEXITCODE -ne 0) {
        Write-Warn2 "pip install also failed; will run from source via run-windows.bat."
    }
}
Write-Ok "install step done (or running from source)"

# ---- 7. Write run-windows.bat ---------------------------------------------
Write-Step "Write run-windows.bat"
$RunBat = Join-Path $RepoRoot 'run-windows.bat'
$PyExePath = "$MingwBin\$PyExe.exe"
$bat = @(
    "@echo off",
    "set PATH=$MingwBin;%PATH%",
    "cd /d `"$RepoRoot`"",
    "`"$PyExePath`" terminator",
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
