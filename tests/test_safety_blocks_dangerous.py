"""Verify genuinely dangerous code is still blocked."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from safety.tool_guard import check_imports, check_paths
from safety.plan_validator import validate

SHOULD_BLOCK = [
    ("rm -rf in subprocess", "import subprocess\nsubprocess.run(['rm', '-rf', '/'])", "python"),
    ("del /s command", "import subprocess\nsubprocess.run('del /s /q C:\\\\*.*', shell=True)", "python"),
    ("rd /s command", "import subprocess\nsubprocess.run('rd /s /q C:\\\\Users', shell=True)", "python"),
    ("format C:", "import subprocess\nsubprocess.run('format C: /y', shell=True)", "python"),
    ("shutdown", "import subprocess\nsubprocess.run('shutdown /s /t 0', shell=True)", "python"),
    ("reg delete", "import subprocess\nsubprocess.run('reg delete HKLM\\\\SOFTWARE /f', shell=True)", "python"),
    ("diskpart", "import subprocess\nsubprocess.run('diskpart /s script.txt', shell=True)", "python"),
    ("bcdedit", "import subprocess\nsubprocess.run('bcdedit /delete {current}', shell=True)", "python"),
    ("shutil.rmtree system dir", "import shutil\nshutil.rmtree('C:\\\\Users\\\\Documents')", "python"),
    ("System32 path", "{'path': 'C:/Windows/System32/drivers'}", "python"),
    ("SSH key path", "{'file': 'C:/Users/Test/.ssh/id_rsa'}", "python"),
]

SHOULD_PASS = [
    ("os.rmdir single dir", "import os\nos.rmdir('C:/Users/Test/Documents/empty_folder')", "python"),
    ("shutil.rmtree with temp context", "import shutil\nimport tempfile\ntemp = tempfile.gettempdir()\nshutil.rmtree(temp + '/cache', ignore_errors=True)", "python"),
]


def _overall_blocked(code, lang):
    ok_i = True
    if lang == "python":
        ok_i, _ = check_imports(code)
    ok_p, _ = check_paths({"code": code, "language": lang})
    ok_v, _ = validate({"code": code, "language": lang})
    return not (ok_i and ok_p and ok_v)


@pytest.mark.parametrize("desc,code,lang", SHOULD_BLOCK)
def test_dangerous_is_blocked(desc, code, lang):
    assert _overall_blocked(code, lang), f"{desc}: should have been blocked but passed"


@pytest.mark.parametrize("desc,code,lang", SHOULD_PASS)
def test_safe_is_allowed(desc, code, lang):
    assert not _overall_blocked(code, lang), f"{desc}: should have passed but was blocked"
