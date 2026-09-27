@echo off
echo Setting up Attendance Auto Sync...
echo NOTE: Edit the PROJECT_DIR and PYTHON_EXE paths below to match your machine before running.

set PROJECT_DIR=C:\Path\To\attendance_system
set PYTHON_EXE=C:\Path\To\python.exe

schtasks /create /tn "AttendanceAutoSync" /tr "cmd.exe /c cd /d %PROJECT_DIR% && %PYTHON_EXE% main.py >> logs\scheduler.log 2>&1" /sc minute /mo 5 /f

echo.
echo ============================================
echo  Task created! Attendance will sync every
echo  5 minutes automatically.
echo ============================================
echo.
pause
