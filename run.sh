#!/bin/bash

PROJECT_DIR="/home/pranavgn/Desktop/Air_Watch"
export GEMINI_API_KEY="API_KEY"

cd "$PROJECT_DIR" || exit

# Start servers
python3 -m http.server 8000 &
PID1=$!

python3 "./server.py" &
PID2=$!

# Kill both on Ctrl+C
trap "echo 'Stopping...'; kill $PID1 $PID2" SIGINT

wait
