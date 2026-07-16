#!/bin/bash

# Terminate existing services on our ports (8000, 8001, 8002)
echo "Cleaning up existing processes on ports 8000, 8001, 8002..."
kill -9 $(lsof -t -i:8000) 2>/dev/null
kill -9 $(lsof -t -i:8001) 2>/dev/null
kill -9 $(lsof -t -i:8002) 2>/dev/null

# Activate Virtual Environment
if [ -d ".venv" ]; then
    echo "Activating virtual environment..."
    PYTHON_BIN=".venv/bin/python3"
    UVICORN_BIN=".venv/bin/uvicorn"
else
    echo "Error: .venv virtual environment not found. Please run installation first."
    exit 1
fi

echo "Starting digital twin simulator service on port 8000..."
$UVICORN_BIN simulator.app:app --host 0.0.0.0 --port 8000 > simulator.log 2>&1 &
SIM_PID=$!

echo "Starting agent inference service on port 8001..."
$UVICORN_BIN agent.app:app --host 0.0.0.0 --port 8001 > agent.log 2>&1 &
AGENT_PID=$!

echo "Starting evaluator scoring service on port 8002..."
$UVICORN_BIN evaluator.app:app --host 0.0.0.0 --port 8002 > evaluator.log 2>&1 &
EVAL_PID=$!

# Give them a moment to start up
sleep 2

# Verify they are running
if ps -p $SIM_PID > /dev/null; then
   echo "✓ Simulator service started successfully (PID: $SIM_PID)"
else
   echo "✗ Error: Simulator service failed to start. Check simulator.log for details."
fi

if ps -p $AGENT_PID > /dev/null; then
   echo "✓ Agent service started successfully (PID: $AGENT_PID)"
   # Start the agent polling loop
   curl -X POST http://localhost:8001/agent/start >/dev/null 2>&1
else
   echo "✗ Error: Agent service failed to start. Check agent.log for details."
fi

if ps -p $EVAL_PID > /dev/null; then
   echo "✓ Evaluator service started successfully (PID: $EVAL_PID)"
else
   echo "✗ Error: Evaluator service failed to start. Check evaluator.log for details."
fi

echo ""
echo "=========================================================="
echo " Sphere Sports Autonomous Observability Portal"
echo "=========================================================="
echo " Dashboard Portal:  http://localhost:8000"
echo " Simulator API:     http://localhost:8000"
echo " Agent API:         http://localhost:8001"
echo " Evaluator API:     http://localhost:8002"
echo "=========================================================="
echo "Press Ctrl+C to terminate all services."

# Wait for Ctrl+C to clean up processes
trap "echo 'Terminating services...'; kill $SIM_PID $AGENT_PID $EVAL_PID 2>/dev/null; exit" INT
wait
