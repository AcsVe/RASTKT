@echo off
chcp 65001 >nul
title RASTKT - Turn the ticket system OFF
net session >nul 2>nul || (echo [X] Right-click this file and choose "Run as administrator". & pause & exit /b 1)
REM Stops 1.iajaward.org only - the award website (iajaward.org) keeps running
schtasks /end /tn "RASTKT Website" >nul 2>nul
schtasks /change /tn "RASTKT Website" /disable >nul 2>nul
echo.
echo   1.iajaward.org (tickets) is OFF (also after restarting the PC).
echo   iajaward.org is still running.
echo   To turn it back on: tkt_on.bat (as administrator)
echo.
pause
