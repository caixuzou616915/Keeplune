@echo off
setlocal
set SCRIPT_DIR=%~dp0
python "%SCRIPT_DIR%ms_traceability_html.py" %*
endlocal
