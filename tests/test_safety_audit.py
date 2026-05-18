"""Safety audit — verify no false positives for legitimate code."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from safety.tool_guard import check_imports, check_paths
from safety.plan_validator import validate

PYTHON_SAFE = [
    ("Create directory", "import os\nos.makedirs('C:/Users/Test/Documents/new_folder', exist_ok=True)"),
    ("Read file", "with open('C:/Users/Test/Documents/file.txt', 'r') as f:\n    content = f.read()"),
    ("Write file", "with open('C:/Users/Test/Documents/output.txt', 'w') as f:\n    f.write('Hello World')"),
    ("List directory", "import os\nfiles = os.listdir('C:/Users/Test/Documents')"),
    ("Move file", "import shutil\nshutil.move('C:/Users/Test/Documents/old.txt', 'C:/Users/Test/Documents/new.txt')"),
    ("Copy file", "import shutil\nshutil.copy('C:/Users/Test/Documents/source.txt', 'C:/Users/Test/Documents/dest.txt')"),
    ("System info", "import platform\nprint(platform.system())"),
    ("List processes", "import psutil\nfor proc in psutil.process_iter(['pid', 'name']):\n    print(proc)"),
    ("HTTP request", "import requests\nresponse = requests.get('https://api.example.com/data')"),
    ("JSON parse", "import json\ndata = json.loads('{\"key\": \"value\"}')"),
    ("Regex", "import re\nmatches = re.findall(r'\\d+', 'abc123def456')"),
    ("DateTime", "from datetime import datetime\nnow = datetime.now()"),
    # subprocess is not in ALLOWED_IMPORTS — blocked intentionally
    ("Threading", "import threading\ndef worker():\n    print('Working')\nt = threading.Thread(target=worker)"),
    ("SQLite", "import sqlite3\nconn = sqlite3.connect('test.db')"),
    ("Hashlib", "import hashlib\nhashlib.sha256(b'data').hexdigest()"),
    ("Base64", "import base64\nbase64.b64encode(b'data')"),
    ("Win32GUI window list", "import win32gui\nwin32gui.EnumWindows(lambda h, _: None, None)"),
    ("PyAutoGUI screenshot", "import pyautogui\npyautogui.screenshot(region=(0, 0, 100, 100))"),
    ("PIL image", "from PIL import Image\nImage.open('test.jpg')"),
    # ctypes is not in ALLOWED_IMPORTS — blocked intentionally
    ("socket hostname", "import socket\nsocket.gethostname()"),
    ("urllib parse", "from urllib.parse import urlparse\nurlparse('https://example.com/path')"),
    ("logging", "import logging\nlogging.basicConfig(level=logging.INFO)"),
    ("collections Counter", "from collections import Counter\nCounter(['a', 'b', 'a', 'c'])"),
    ("Temp cleanup with tempfile", "import tempfile\nimport shutil\ntemp_dir = tempfile.gettempdir()\nshutil.rmtree(temp_dir + '/cache', ignore_errors=True)"),
    ("Delete single file", "import os\nos.remove('C:/Users/Test/Documents/old_file.txt')"),
    ("Remove empty dir", "import os\nos.rmdir('C:/Users/Test/Documents/empty_folder')"),
    ("Rename file", "import os\nos.rename('C:/Users/Test/Documents/old.txt', 'C:/Users/Test/Documents/new.txt')"),
    ("Get file stats", "import os\nos.stat('C:/Users/Test/Documents/file.txt')"),
    ("pathlib operations", "from pathlib import Path\nPath('C:/Users/Test/Documents').exists()"),
]

POWERSHELL_SAFE = [
    ("Get-ChildItem", "Get-ChildItem -Path C:\\Users\\Test\\Documents"),
    ("Copy-Item", "Copy-Item -Path 'C:\\Users\\Test\\file.txt' -Destination 'C:\\Users\\Test\\backup.txt'"),
    ("Move-Item", "Move-Item -Path 'C:\\Users\\Test\\old.txt' -Destination 'C:\\Users\\Test\\new.txt'"),
    ("New-Item directory", "New-Item -Path 'C:\\Users\\Test\\Documents\\new_folder' -ItemType Directory"),
    ("Get-Content", "Get-Content -Path 'C:\\Users\\Test\\file.txt'"),
    ("Set-Content", "Set-Content -Path 'C:\\Users\\Test\\output.txt' -Value 'Hello World'"),
    ("Get-Process", "Get-Process | Select-Object Name, Id"),
    ("Get-Service", "Get-Service -Name Spooler"),
    ("Select-String", "Select-String -Path 'C:\\Users\\Test\\file.txt' -Pattern 'error'"),
    ("Where-Object", "Get-Process | Where-Object { $_.CPU -gt 10 }"),
    ("ForEach-Object", "Get-ChildItem | ForEach-Object { Write-Host $_.Name }"),
    ("Invoke-WebRequest", "Invoke-WebRequest -Uri 'https://api.example.com/data' -OutFile 'data.json'"),
    ("ConvertTo-Json", "$data = @{Name='Test'; Value=123}\n$data | ConvertTo-Json"),
    ("Import-Csv", "Import-Csv -Path 'C:\\Users\\Test\\data.csv'"),
    ("Export-Csv", "$data | Export-Csv -Path 'C:\\Users\\Test\\output.csv' -NoTypeInformation"),
    ("Clear-RecycleBin", "Clear-RecycleBin -Force"),
    ("Get-Volume", "Get-Volume | Select-Object DriveLetter, SizeRemaining"),
    ("Get-NetIPAddress", "Get-NetIPAddress | Where-Object AddressFamily -eq IPv4"),
    ("Test-Connection", "Test-Connection -ComputerName google.com -Count 2"),
]


@pytest.mark.parametrize("desc,code", PYTHON_SAFE)
def test_python_safe_passes_imports(desc, code):
    ok, reason = check_imports(code)
    assert ok, f"{desc}: import check failed — {reason}"


@pytest.mark.parametrize("desc,code", PYTHON_SAFE)
def test_python_safe_passes_paths(desc, code):
    ok, reason = check_paths({"code": code, "language": "python"})
    assert ok, f"{desc}: path check failed — {reason}"


@pytest.mark.parametrize("desc,code", PYTHON_SAFE)
def test_python_safe_passes_plan(desc, code):
    ok, reason = validate({"code": code, "language": "python"})
    assert ok, f"{desc}: plan validator failed — {reason}"


@pytest.mark.parametrize("desc,code", POWERSHELL_SAFE)
def test_powershell_safe_passes_paths(desc, code):
    ok, reason = check_paths({"code": code, "language": "powershell"})
    assert ok, f"{desc}: path check failed — {reason}"


@pytest.mark.parametrize("desc,code", POWERSHELL_SAFE)
def test_powershell_safe_passes_plan(desc, code):
    ok, reason = validate({"code": code, "language": "powershell"})
    assert ok, f"{desc}: plan validator failed — {reason}"
