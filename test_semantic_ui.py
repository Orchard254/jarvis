import os
import sys
import subprocess
import time

# Ensure current directory is in path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from tools.adapters import list_elements, click_element, type_in_element, focus_window


def run_tests():
    if sys.platform == 'win32':
        try:
            sys.stdout.reconfigure(encoding='utf-8')
            sys.stderr.reconfigure(encoding='utf-8')
        except AttributeError:
            pass
            
    print("==================================================")
    print("               RUNNING SEMANTIC UI TESTS          ")
    print("==================================================")
    
    proc = None
    try:
        print("\nStep 1: Launching notepad.exe...")
        proc = subprocess.Popen(["notepad.exe"])
        time.sleep(2.0)  # Wait for it to open and focus
        
        # Ensure Notepad is in focus
        print("Step 2: Focusing Notepad window...")
        focus_res = focus_window(title="Notepad")
        print(f"  Focus result: {focus_res}")
        time.sleep(0.5)

        print("\nStep 3: Listing accessible elements in active window...")
        list_res = list_elements()
        assert list_res.get("success"), f"list_elements failed: {list_res.get('error')}"
        
        elements = list_res.get("elements", [])
        print(f"  Successfully listed elements. Found {len(elements)} elements.")
        print(f"  Active Window Title: '{list_res.get('window_title')}'")
        
        # Print first 5 elements for inspection
        for el in elements[:5]:
            print(f"    - Type: {el['control_type']}, Name: '{el['name']}', AutoId: '{el['automation_id']}'")
            
        # Notepad on Windows 11 has a Text Editor control type "Document" or "Edit" (Document name is usually 'Text Editor' or similar)
        # Notepad on older Windows has an "Edit" control.
        # Let's search if any Edit or Document control exists
        has_editor = False
        for el in elements:
            if el["control_type"] in ("Edit", "Document"):
                has_editor = True
                print(f"  Found Editor element: {el}")
                break
        
        print("\nStep 4: Typing text into editor using type_in_element...")
        # We can target by Name 'Text Editor' or control type 'Document' or 'Edit'.
        # Since Notepad's edit control is usually named 'Text Editor' or empty, let's target by a common name or a broad substring.
        # Let's find the best target string. If elements have name 'Text Editor' or 'Edit', we use that.
        target_editor_name = "Text Editor"
        for el in elements:
            if el["control_type"] in ("Edit", "Document"):
                if el["name"]:
                    target_editor_name = el["name"]
                    break
                elif el["automation_id"]:
                    target_editor_name = el["automation_id"]
                    break
        
        print(f"  Target editor identifier: '{target_editor_name}'")
        type_res = type_in_element(text=target_editor_name, content="Hello from JARVIS Closed-Loop Visual-Semantic Engine!")
        print(f"  Type result: {type_res}")
        assert type_res.get("success"), f"type_in_element failed: {type_res.get('error')}"
        
        print("\nStep 5: Clicking the 'File' menu...")
        # Click the "File" menu item
        click_res = click_element(text="File", control_type="MenuItem")
        print(f"  Click result: {click_res}")
        assert click_res.get("success"), f"click_element 'File' failed: {click_res.get('error')}"
        time.sleep(1.0)
        
        # Escape to dismiss the menu
        import pyautogui
        pyautogui.press("esc")
        print("  Dismissed Notepad file menu.")

        print("\n==================================================")
        print("        ALL SEMANTIC UI TESTS PASSED SUCCESSFULLY! ")
        print("==================================================")
        
    except Exception as e:
        print(f"\n❌ Test Failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        if proc:
            print("\nCleaning up: Closing notepad.exe...")
            # Use taskkill to cleanly abort notepad without asking for save confirmation
            try:
                subprocess.run(["taskkill", "/PID", str(proc.pid), "/F"], capture_output=True)
                print("  Notepad closed.")
            except Exception as e:
                print(f"  Error closing notepad: {e}")


if __name__ == "__main__":
    run_tests()
