
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tools.execute_code import execute_code

code = """import subprocess, time, os, sys
# Launch Notepad
subprocess.Popen(['notepad.exe'])
# Give it a moment to start
time.sleep(2)
print('Notepad launched')"""

print("Testing execute_code...")
result = execute_code(code=code, language="python")
print("execute_code result:", result)
