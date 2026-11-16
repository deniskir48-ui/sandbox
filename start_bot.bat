@echo off
rem Telegram bot for Video Agents. Keep this window open (it can be minimized).
cd /d "%~dp0"
title Video Agents bot
".venv\Scripts\python.exe" -m video_agents bot
