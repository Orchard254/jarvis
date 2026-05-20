import uiautomation as auto

def read_ui_tree(window_title: str = "") -> dict:
    """
    Reads the native UI element tree of a window using Windows UIAutomation.
    Provides perfect coordinates and text for all interactable elements without OCR.
    """
    try:
        if window_title:
            win = auto.WindowControl(searchDepth=2, Name=window_title)
            if not win.Exists(0, 0):
                # Fallback to substring match
                win = auto.WindowControl(searchDepth=2, SubName=window_title)
        else:
            win = auto.GetForegroundControl()
            if win:
                win = win.GetTopLevelControl()

        if not win or not win.Exists(0, 0):
            return {"success": False, "error": "Could not find target window."}

        elements = []
        # Types of controls we actually care about
        target_types = {
            auto.ControlType.ButtonControl: "button",
            auto.ControlType.TextControl: "text",
            auto.ControlType.EditControl: "input",
            auto.ControlType.ListItemControl: "item",
            auto.ControlType.TabItemControl: "tab",
            auto.ControlType.MenuItemControl: "menu_item",
            auto.ControlType.DocumentControl: "document",
            auto.ControlType.HyperlinkControl: "link",
            auto.ControlType.CheckBoxControl: "checkbox",
            auto.ControlType.RadioButtonControl: "radio",
            auto.ControlType.ComboBoxControl: "dropdown"
        }

        # Fast traversal
        auto.SetGlobalSearchTimeout(1)
        for control, depth in auto.WalkControl(win):
            if control.ControlType in target_types:
                try:
                    rect = control.BoundingRectangle
                    if rect and rect.width() > 0 and rect.height() > 0:
                        name = control.Name or ""
                        elements.append({
                            "type": target_types[control.ControlType],
                            "text": name,
                            "bounds": {
                                "left": rect.left, 
                                "top": rect.top, 
                                "right": rect.right, 
                                "bottom": rect.bottom,
                                "center_x": rect.left + (rect.width() // 2),
                                "center_y": rect.top + (rect.height() // 2)
                            }
                        })
                except Exception:
                    # Ignore inaccessible individual elements
                    pass
                    
        return {"success": True, "window_title": win.Name, "elements": elements}
    except Exception as e:
        return {"success": False, "error": str(e)}


def register():
    return {"read_ui_tree": read_ui_tree}


def schema():
    return {
        "type": "function",
        "function": {
            "name": "read_ui_tree",
            "description": "Reads the exact native UI element tree of a window using accessibility APIs. Returns precise bounds and text.",
            "parameters": {
                "type": "object",
                "properties": {
                    "window_title": {
                        "type": "string",
                        "description": "Optional title of the window. If empty, uses the active foreground window."
                    }
                }
            }
        }
    }
