# Windows Git Checkout Fix Guide

## Problem
Git checkout fails with "invalid path" errors due to OneDrive interference and/or NTFS path issues.

## Solution Steps (Run in PowerShell as Administrator)

### Step 1: Remove the problematic OneDrive folder
```powershell
Remove-Item -Recurse -Force "C:\Users\macha\OneDrive\Desktop\Ai\jarvis"
```

### Step 2: Remove the incomplete clone in C:\dev
```powershell
Remove-Item -Recurse -Force "C:\dev\jarvis"
```

### Step 3: Clone fresh with proper settings
```powershell
cd C:\dev
git clone --config core.longpaths=true --config core.protectNTFS=false https://github.com/Orchard254/jarvis.git
cd jarvis
```

### Step 4: If still having issues, try alternative location
```powershell
# Clone to a non-OneDrive, short path location
cd C:\
git clone https://github.com/Orchard254/jarvis.git
cd jarvis
```

## Why This Happens
- OneDrive syncs files and can lock them, preventing git operations
- Windows has a 260-character path limit by default
- NTFS filename protection can block certain characters

## Prevention
- Keep development projects OUT of OneDrive folders
- Use short, simple paths like `C:\dev\` or `C:\projects\`
- Enable long paths: `git config --global core.longpaths true`
