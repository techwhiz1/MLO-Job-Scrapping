@echo off
echo Starting Job Scraping Tool...
echo.

echo Installing backend dependencies...
pip install -r requirements.txt

echo.
echo Installing frontend dependencies...
cd frontend
npm install
cd ..

echo.
echo Starting backend server...
start cmd /k "cd backend && python main.py"

echo.
echo Waiting for backend to start...
timeout /t 5 /nobreak > nul

echo Starting frontend server...
start cmd /k "cd frontend && npm start"

echo.
echo Job Scraping Tool is starting...
echo Backend will be available at: http://localhost:8000
echo Frontend will be available at: http://localhost:3000
echo.
echo Press any key to exit...
pause > nul
