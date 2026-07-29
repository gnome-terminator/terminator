@echo off
REM Double-click this file to install Terminator on Windows.
REM It runs install-windows.ps1 with execution policy bypassed.
REM Requires Windows 10 1809+ (winget / App Installer).

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install-windows.ps1" %*
echo.
pause
