@echo off
setlocal
pushd "%~dp0"
if errorlevel 1 exit /b 1
set "SPEECH_PYTHON=%~dp0.venv-speech\Scripts\python.exe"
if not exist "%SPEECH_PYTHON%" (
  echo The prepared .venv-speech environment is missing. No fallback interpreter will be used.
  popd
  exit /b 1
)
"%SPEECH_PYTHON%" scripts\diagnose_transcription.py --load-model --offline
if errorlevel 1 (
  echo Speech preparation failed. Startup stopped before requesting credentials.
  popd
  exit /b 1
)
if /I "%~1"=="--check" (
  popd
  exit /b 0
)
"%SPEECH_PYTHON%" start.py
set "SPEECH_EXIT_CODE=%ERRORLEVEL%"
popd
exit /b %SPEECH_EXIT_CODE%
