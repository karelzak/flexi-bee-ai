#!/bin/bash
echo "Spousteni Flexi-Bee AI (Refactored)..."
if [ -d "venv" ]; then
    ./venv/bin/python run.py
else
    python3 run.py
fi
