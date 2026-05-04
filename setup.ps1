# setup.ps1 - One-click setup for Personal Assistant on Windows

Write-Host "=============================================="
Write-Host "  Personal Assistant Setup"
Write-Host "==============================================" -ForegroundColor Cyan

# Step 1: Create virtual environment
Write-Host ""
Write-Host "[1/5] Creating virtual environment..." -ForegroundColor Yellow

if (Test-Path "venv") {
    Write-Host "venv already exists, skipping..." -ForegroundColor Gray
}
else {
    python -m venv venv
    Write-Host "Virtual environment created" -ForegroundColor Green
}

# Step 2: Activate virtual environment
Write-Host ""
Write-Host "[2/5] Activating virtual environment..." -ForegroundColor Yellow

& ".\venv\Scripts\Activate.ps1"

Write-Host "Virtual environment activated" -ForegroundColor Green

# Step 3: Install package in development mode
Write-Host ""
Write-Host "[3/5] Installing package (pip install -e .)..." -ForegroundColor Yellow

pip install -e .

Write-Host "Package installed" -ForegroundColor Green

# Step 4: Install dependencies
Write-Host ""
Write-Host "[4/5] Installing dependencies..." -ForegroundColor Yellow

pip install -r requirements.txt

Write-Host "Dependencies installed" -ForegroundColor Green

# Step 5: Setup pre-commit hooks
Write-Host ""
Write-Host "[5/5] Setting up pre-commit hooks..." -ForegroundColor Yellow

pip install pre-commit
pre-commit install

Write-Host "Pre-commit hooks configured" -ForegroundColor Green

# Summary
Write-Host ""
Write-Host "=============================================="
Write-Host "  Setup Complete!"
Write-Host "==============================================" -ForegroundColor Green

Write-Host ""
Write-Host "You can now run:" -ForegroundColor Cyan
Write-Host "  personal-assistant"
Write-Host "  personal-assistant --mode text"
Write-Host "  personal-assistant --help"

Write-Host ""
Write-Host "Make sure Ollama is running:" -ForegroundColor Yellow
Write-Host "  ollama serve"