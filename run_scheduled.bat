@echo off
rem Scheduled run: makes a video (from the idea queue or a new one) and publishes it.
rem Created by "python -m video_agents schedule add"; output goes to workspace\schedule.log
cd /d "%~dp0"
if not exist workspace mkdir workspace
echo ===== %date% %time% ===== >> workspace\schedule.log
".venv\Scripts\python.exe" -m video_agents run --publish %* >> workspace\schedule.log 2>&1
