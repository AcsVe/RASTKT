@echo off
cd /d "%~dp0"
net session >nul 2>nul || (echo [X] Run as administrator. & pause & exit /b 1)
schtasks /end /tn "RASTKT Website" >nul 2>nul
schtasks /delete /f /tn "RASTKT Website" >nul 2>nul
schtasks /delete /f /tn "RASTKT Hourly Backup" >nul 2>nul
schtasks /delete /f /tn "RASTKT Failover Watchdog" >nul 2>nul
echo Stopped and removed the RASTKT tasks.
pause
