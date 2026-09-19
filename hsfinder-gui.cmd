@echo off
rem hsfinder-gui - open the Hearthstone art finder GUI
rem
rem Usage:
rem   hsfinder-gui                    just open the window
rem   hsfinder-gui "Timethief Rafaam" open and search right away
rem
rem NOTE: keep this file pure ASCII. cmd.exe reads .cmd files using the
rem system ANSI code page (cp936 here), so UTF-8 text would break parsing.
rem
rem NOTE: we deliberately use python.exe (not pythonw.exe) and hide the
rem console window ourselves. pythonw.exe has no console, and in that state
rem CPython mis-decodes non-ASCII command line arguments, so Chinese card
rem names would arrive as mojibake. Keep this whole file ASCII-only.
setlocal
set "APP=%~dp0hsfinder_app.py"
if not exist "%APP%" (
  echo [hsfinder] not found: %APP%
  exit /b 1
)

set "PY="
for %%P in (python.exe) do if not defined PY set "PY=%%~$PATH:P"
if not defined PY (
  echo [hsfinder] python.exe not found in PATH.
  echo [hsfinder] install Python 3 from https://www.python.org/downloads/
  exit /b 1
)

if /i "%~1"=="--console" (
  shift
  "%PY%" -X utf8 "%APP%" %*
  exit /b %ERRORLEVEL%
)

rem Hide our own console window; the GUI then runs as a normal window.
if /i "%~1"=="" (
  start "" /min "%PY%" -X utf8 "%APP%"
) else (
  start "" /min "%PY%" -X utf8 "%APP%" %*
)
exit /b 0
