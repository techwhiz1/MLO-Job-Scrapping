#!/bin/bash

echo "Starting Job Scraping Tool..."
echo

echo "Installing backend dependencies..."
pip install -r requirements.txt

echo
echo "Installing frontend dependencies..."
cd frontend
npm install
cd ..

echo
echo "Starting backend server..."
cd backend
python main.py &
BACKEND_PID=$!
cd ..

echo
echo "Waiting for backend to start..."
sleep 5

echo "Starting frontend server..."
cd frontend
npm start &
FRONTEND_PID=$!
cd ..

echo
echo "Job Scraping Tool is starting..."
echo "Backend is available at: http://localhost:8000"
echo "Frontend is available at: http://localhost:3000"
echo
echo "Press Ctrl+C to stop both servers..."

# Wait for user to stop
trap "kill $BACKEND_PID $FRONTEND_PID; exit" SIGINT
wait
