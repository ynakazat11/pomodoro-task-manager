#!/bin/bash
# Pomodoro Menu Bar App Launcher
# Run this from terminal: ./start_menubar.sh

cd "$(dirname "$0")"
python3 menubar_app.py &
echo "🍅 Pomodoro Menu Bar App started!"
echo "Look for the tomato icon in your menu bar (top-right)"
