@echo off
rem  Stop Memory Cleaner: only kills the python/pythonw process running memclean.py.
rem  Keep this file ASCII-only - cmd.exe reads .cmd files with the OEM code page.
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -Command "$p = Get-CimInstance Win32_Process | Where-Object { ($_.Name -eq 'pythonw.exe' -or $_.Name -eq 'python.exe') -and $_.CommandLine -like '*memclean.py*' }; if ($p) { $p | ForEach-Object { Write-Host ('stopped PID ' + $_.ProcessId); Stop-Process -Id $_.ProcessId -Force } } else { Write-Host 'Memory Cleaner is not running.' }"
echo.
pause
