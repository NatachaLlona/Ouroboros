@echo off
setlocal
pushd "%~dp0"
if errorlevel 1 exit /b 1
rem Compatibility launcher only; Python workloads and native speech dependencies run in Docker.
python start.py %*
set "SPEECH_EXIT_CODE=%ERRORLEVEL%"
popd
exit /b %SPEECH_EXIT_CODE%
