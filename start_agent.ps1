# Voice Agent Startup Script
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "   🎙️  VOICE AGENT LAUNCHER" -ForegroundColor Yellow
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Check if Python is installed
try {
    $pythonVersion = python --version 2>&1
    Write-Host "✅ Python found: $pythonVersion" -ForegroundColor Green
} catch {
    Write-Host "❌ Python not found. Please install Python 3.8+" -ForegroundColor Red
    exit 1
}

# Check if .env file exists
if (Test-Path ".env") {
    Write-Host "✅ Environment file found" -ForegroundColor Green
} else {
    Write-Host "❌ .env file not found" -ForegroundColor Red
    Write-Host "Creating .env file with API keys..." -ForegroundColor Yellow
    @"
MURF_API_KEY=ap2_b69c992b-1779-4427-bf08-ee4e76443cbd
ASSEMBLYAI_API_KEY=8aa0cbddb25b4f9491b744b6be88287d
GEMINI_API_KEY=AIzaSyAcFN3LyMPJUmciIH8bTNnL3BR0wV9YvuQ
"@ | Out-File -FilePath .env -Encoding UTF8
    Write-Host "✅ .env file created" -ForegroundColor Green
}

# Check if virtual environment exists
if (Test-Path ".venv") {
    Write-Host "✅ Virtual environment found" -ForegroundColor Green
} else {
    Write-Host "⚠️  Virtual environment not found" -ForegroundColor Yellow
    Write-Host "Creating virtual environment..." -ForegroundColor Yellow
    python -m venv .venv
    Write-Host "✅ Virtual environment created" -ForegroundColor Green
}

# Activate virtual environment
Write-Host "Activating virtual environment..." -ForegroundColor Yellow
& .\.venv\Scripts\Activate.ps1

# Install requirements
Write-Host "Installing/updating dependencies..." -ForegroundColor Yellow
pip install -q --upgrade pip
pip install -q -r requirements.txt
Write-Host "✅ Dependencies installed" -ForegroundColor Green

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "   🚀 STARTING VOICE AGENT SERVER" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "📍 Server will start at: " -NoNewline -ForegroundColor Yellow
Write-Host "http://127.0.0.1:8000" -ForegroundColor Cyan
Write-Host ""
Write-Host "🎤 Instructions:" -ForegroundColor Yellow
Write-Host "   1. Wait for server to start" -ForegroundColor White
Write-Host "   2. Open browser to http://127.0.0.1:8000" -ForegroundColor White
Write-Host "   3. Click 'Start Talking' button" -ForegroundColor White
Write-Host "   4. Allow microphone access" -ForegroundColor White
Write-Host "   5. Speak naturally to the agent" -ForegroundColor White
Write-Host ""
Write-Host "Press Ctrl+C to stop the server" -ForegroundColor Yellow
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Start the server
python main.py
