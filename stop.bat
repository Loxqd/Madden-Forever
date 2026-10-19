@echo off
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\stop.ps1"
if "%~1"=="" pause
