@echo off
REM Start GridWise API on http://0.0.0.0:8000
cd /d "%~dp0"
if not exist .venv\Scripts\uvicorn.exe (
  echo Create the venv first: python -m venv .venv ^&^& .venv\Scripts\pip install -r requirements.txt
  exit /b 1
)
.venv\Scripts\uvicorn.exe app.main:app --host 0.0.0.0 --port 8000 --reload
