@echo off
echo Spousteni Flexi-Bee AI (Refactored)...
if exist "venv\Scripts\python.exe" (
    .\venv\Scripts\python.exe run.py
) else (
    python run.py
)
pause
