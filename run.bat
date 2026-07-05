@echo off
REM run.bat - all-in-one launcher for the FastAPI backend + SvelteKit frontend.
REM Delegates to run.ps1 so we can kill both process trees on "exit".
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run.ps1" %*
