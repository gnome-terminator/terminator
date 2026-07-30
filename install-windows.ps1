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
# so we try both names. The first run also initialises the pacman keyring,
# which on some systems can take a while with no output -- so we (a) init the
# keyring explicitly, (b) stream pacman output live, and (c) print a heartbeat
# so it never looks hung.
Write-Host "`nFirst MSYS2 use downloads package lists and may take several" -ForegroundColor Yellow
Write-Host "minutes. Dots print while it works; do not close this window." -ForegroundColor Yellow

function Invoke-BashStream([string]$cmd, [string]$label) {
    # Run `bash -l $script` sharing the console (so pacman output streams live)
    # and print a dot every 3s until it exits -- visible progress even when
    # pacman itself is quiet.
    #
    # WHY A TEMP FILE: `Start-Process -ArgumentList @('-lc', $cmd)` joins the
    # array with SPACES into one unquoted string, so bash's -c grabs only the
    # first token of $cmd as the command and drops the rest as positional
    # params -> e.g. `pacman` runs with NO args -> "no operation specified".
    # Writing $cmd to a script file sidesteps all quoting (single quotes,
    # glob '*', sed expressions) entirely.
    #
    # WHY .NET Process (not Start-Process): the Windows temp dir may contain
    # a space (C:\Users\Jane Doe\...); Start-Process would split the path arg
    # on that space. System.Diagnostics.Process passes the Arguments string
    # verbatim to CreateProcess, so the double-quoted path below stays one
    # token.
    $tmpWin = [IO.Path]::GetTempFileName() + '.sh'
    Set-Content -Path $tmpWin -Value $cmd -Encoding ASCII
    # C:\Users\...\tmpXX.sh -> /c/Users/.../tmpXX.sh  (MSYS2 path)
    $tmpMsys = '/' + $tmpWin.Substring(0,1).ToLower() + ($tmpWin.Substring(2) -replace '\\','/')
    Write-Host "    $label " -NoNewline -ForegroundColor Gray
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $Bash
    $psi.Arguments = '-l "' + $tmpMsys + '"'   # double-quote the path for bash
    $psi.UseShellExecute = $false
    $psi.RedirectStandardOutput = $false
    $psi.RedirectStandardError = $false
    $p = New-Object System.Diagnostics.Process
    $p.StartInfo = $psi
    [void]$p.Start()
    $n = 0
    while (-not $p.HasExited) {
        Write-Host -NoNewline "."
        $n++
        if ($n % 20 -eq 0) { Write-Host -NoNewline " ($($n*3)s elapsed) " }
        Start-Sleep -Seconds 3
    }
    Write-Host ""
    Remove-Item $tmpWin -ErrorAction SilentlyContinue
    return $p.ExitCode
}

Write-Step "Repair pacman keyring (MSYS2 key had rotated -> 'invalid signature')"
# The shipped keyring is often stale, so every package fails signature check
# with 'invalid signature from Christoph Reiter'. Fix: temporarily disable
# SigLevel, install the latest msys2-keyring package, then re-populate trust.
$nosigConf = '/etc/pacman-nosig.conf'
[void](Invoke-BashStream "sed 's|^[[:space:]]*SigLevel.*|SigLevel = Never|' /etc/pacman.conf > $nosigConf" "make nosig config")
[void](Invoke-BashStream "pacman --config $nosigConf -Sy --noconfirm" "nosig sync DB")
[void](Invoke-BashStream "pacman --config $nosigConf -S --noconfirm --needed msys2-keyring" "install latest msys2-keyring")
# Now rebuild trust from the freshly installed keyring.
[void](Invoke-BashStream "pacman-key --init" "keyring init")
[void](Invoke-BashStream "pacman-key --populate msys2" "keyring populate")
Write-Warn2 "if signatures still fail below, re-run; otherwise the repair worked."

Write-Step "Sync MSYS2 package database (pacman -Sy)"
$rc = Invoke-BashStream "pacman -Sy --noconfirm --overwrite '*'" "sync DB"
if ($rc -ne 0) { Write-Warn2 "pacman -Sync exited $rc; continuing anyway." }

function Install-Pkg([string[]]$candidates) {
    foreach ($name in $candidates) {
        $rc = Invoke-BashStream "pacman -S --noconfirm --needed --overwrite '*' $name" "install $name"
        if ($rc -eq 0) { Write-Ok $name; return $true }
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

# ---- 4b. Bundle DejaVu Sans Mono (Ubuntu-like monospace) -------------------
# DejaVu isn't an MSYS2 package and isn't on a stock Windows box, so the
# Ubuntu-looking monospace the config.py default asks for would otherwise be
# silently substituted by fontconfig. We ship the TTFs in the repo and install
# them into the per-user Windows font dir (fontconfig scans
# WINDOWSUSERFONTDIR, no admin needed), then refresh the cache so Pango
# resolves 'DejaVu Sans Mono' on first launch.
Write-Step "Install bundled DejaVu Sans Mono font"
$UserFonts = Join-Path $env:LOCALAPPDATA 'Microsoft\Windows\Fonts'
[void](New-Item -ItemType Directory -Force -Path $UserFonts)
foreach ($f in @('DejaVuSansMono.ttf','DejaVuSansMono-Bold.ttf')) {
    $src = Join-Path $RepoRoot "data\fonts\$f"
    if (Test-Path $src) {
        Copy-Item $src (Join-Path $UserFonts $f) -Force
        Write-Ok "copied $f"
    } else {
        Write-Warn2 "missing bundled font $src (will fall back to a generic mono)"
    }
}
[void](Invoke-BashStream "/mingw64/bin/fc-cache -f" "refresh font cache")

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
