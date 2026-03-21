#!/bin/bash
set -e

BACKEND_PORT=$(python3 -c "import socket; s=socket.socket(); s.bind(('',0)); p=s.getsockname()[1]; s.close(); print(p)")

echo "Backend → http://localhost:$BACKEND_PORT"
echo "Frontend → http://localhost:5173 (or next available)"
echo "$BACKEND_PORT" > "$(dirname "$0")/.backend_port"

cd backend
source venv/bin/activate
uvicorn main:app --reload --port "$BACKEND_PORT" &
BACKEND_PID=$!
cd ..

echo "Waiting for backend..."
until python3 -c "import socket; s=socket.socket(); s.connect(('127.0.0.1', $BACKEND_PORT)); s.close()" 2>/dev/null; do
  sleep 0.2
done
echo "Backend ready."

cd frontend
VITE_BACKEND_PORT="$BACKEND_PORT" npm run dev &
FRONTEND_PID=$!
cd ..

trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit" INT TERM
wait
