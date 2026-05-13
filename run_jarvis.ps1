# run_jarvis.ps1 — Launch JARVIS using the project venv.
# Right-click → "Run with PowerShell" or run from a terminal.

# Ensure we're in the script's directory
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptDir

# Activate project venv and launch Jarvis
$venvActivate = Join-Path $scriptDir "venv\Scripts\Activate.ps1"
if (Test-Path $venvActivate) {
    . $venvActivate
}

python jarvis.py

# Keep window open if launched interactively
if ($Host.Name -eq "ConsoleHost") {
    Read-Host "`nPress Enter to exit..."
}
