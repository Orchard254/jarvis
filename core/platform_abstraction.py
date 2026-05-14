"""
Cross-Platform Abstraction Layer

Provides unified interfaces for OS-specific operations across Windows, Linux, and macOS.
Automatically detects platform and routes to appropriate native implementations.
"""

import logging
import os
import platform
import sys
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Detect current platform
CURRENT_PLATFORM = sys.platform
IS_WINDOWS = CURRENT_PLATFORM == "win32"
IS_LINUX = CURRENT_PLATFORM.startswith("linux")
IS_MACOS = CURRENT_PLATFORM == "darwin"

logger.info(f"Platform detected: {CURRENT_PLATFORM} ({platform.release()})")


class PlatformAbstraction:
    """
    Unified interface for platform-specific operations.
    
    Usage:
        platform_lib = PlatformAbstraction()
        
        # Window management
        windows = platform_lib.get_windows()
        platform_lib.focus_window("Notepad")
        
        # Process management
        processes = platform_lib.list_processes()
        platform_lib.kill_process(pid)
        
        # File system
        apps = platform_lib.find_installed_apps()
    """
    
    def __init__(self):
        self._backend = self._init_backend()
    
    def _init_backend(self):
        """Initialize appropriate backend based on platform."""
        if IS_WINDOWS:
            logger.info("Using Windows backend (pywin32, pygetwindow)")
            return WindowsBackend()
        elif IS_LINUX:
            logger.info("Using Linux backend (X11, subprocess)")
            return LinuxBackend()
        elif IS_MACOS:
            logger.info("Using macOS backend (AppKit, subprocess)")
            return MacOSBackend()
        else:
            logger.warning(f"Unknown platform {CURRENT_PLATFORM}, using fallback")
            return FallbackBackend()
    
    # === Window Management ===
    
    def get_windows(self) -> list[dict]:
        """Get list of all open windows with metadata."""
        return self._backend.get_windows()
    
    def get_focused_window(self) -> Optional[dict]:
        """Get currently focused window."""
        return self._backend.get_focused_window()
    
    def focus_window(self, title_pattern: str) -> bool:
        """Bring window matching pattern to focus."""
        return self._backend.focus_window(title_pattern)
    
    def minimize_window(self, title_pattern: str) -> bool:
        """Minimize window matching pattern."""
        return self._backend.minimize_window(title_pattern)
    
    def maximize_window(self, title_pattern: str) -> bool:
        """Maximize window matching pattern."""
        return self._backend.maximize_window(title_pattern)
    
    def close_window(self, title_pattern: str) -> bool:
        """Close window matching pattern."""
        return self._backend.close_window(title_pattern)
    
    def set_window_position(self, title_pattern: str, x: int, y: int, width: int, height: int) -> bool:
        """Set window position and size."""
        return self._backend.set_window_position(title_pattern, x, y, width, height)
    
    # === Process Management ===
    
    def list_processes(self) -> list[dict]:
        """Get list of running processes."""
        return self._backend.list_processes()
    
    def get_process_by_name(self, name: str) -> Optional[dict]:
        """Get process by name."""
        return self._backend.get_process_by_name(name)
    
    def kill_process(self, pid: int) -> bool:
        """Kill process by PID."""
        return self._backend.kill_process(pid)
    
    def start_process(self, command: str) -> Optional[int]:
        """Start a new process, return PID or None."""
        return self._backend.start_process(command)
    
    # === Application Discovery ===
    
    def find_installed_apps(self) -> list[dict]:
        """Find installed applications."""
        return self._backend.find_installed_apps()
    
    def get_app_path(self, app_name: str) -> Optional[str]:
        """Get path to application executable."""
        return self._backend.get_app_path(app_name)
    
    # === Input Control ===
    
    def send_keys(self, keys: str) -> bool:
        """Send keyboard input."""
        return self._backend.send_keys(keys)
    
    def send_mouse_click(self, x: int, y: int, button: str = "left") -> bool:
        """Send mouse click at coordinates."""
        return self._backend.send_mouse_click(x, y, button)
    
    def send_mouse_move(self, x: int, y: int) -> bool:
        """Move mouse to coordinates."""
        return self._backend.send_mouse_move(x, y)
    
    # === System Information ===
    
    def get_screen_resolution(self) -> tuple[int, int]:
        """Get screen resolution (width, height)."""
        return self._backend.get_screen_resolution()
    
    def get_os_version(self) -> str:
        """Get OS version string."""
        return self._backend.get_os_version()
    
    def get_username(self) -> str:
        """Get current username."""
        return self._backend.get_username()
    
    def get_home_dir(self) -> str:
        """Get user home directory."""
        return self._backend.get_home_dir()


class WindowsBackend:
    """Windows-specific implementation using pywin32 and pygetwindow."""
    
    def __init__(self):
        try:
            import win32gui
            import win32process
            import win32con
            import win32api
            import pygetwindow as gw
            self.gw = gw
            self.win32gui = win32gui
            self.win32process = win32process
            self.win32con = win32con
            self.win32api = win32api
            self._available = True
        except ImportError as e:
            logger.error(f"Windows backend unavailable: {e}")
            self._available = False
    
    def get_windows(self) -> list[dict]:
        if not self._available:
            return []
        
        windows = []
        try:
            for w in self.gw.getAllWindows():
                if w.title and w.visible:
                    windows.append({
                        "title": w.title,
                        "hwnd": w._hWnd,
                        "x": w.left,
                        "y": w.top,
                        "width": w.width,
                        "height": w.height,
                        "focused": w.isActive,
                        "minimized": w.isMinimized,
                        "maximized": w.isMaximized,
                    })
        except Exception as e:
            logger.error(f"Error getting windows: {e}")
        return windows
    
    def get_focused_window(self) -> Optional[dict]:
        if not self._available:
            return None
        try:
            w = self.gw.getActiveWindow()
            if w:
                return {
                    "title": w.title,
                    "hwnd": w._hWnd,
                    "x": w.left,
                    "y": w.top,
                    "width": w.width,
                    "height": w.height,
                }
        except Exception as e:
            logger.debug(f"getActiveWindow failed: {e}")
        return None
    
    def focus_window(self, title_pattern: str) -> bool:
        if not self._available:
            return False
        try:
            for w in self.gw.getAllWindows():
                if title_pattern.lower() in w.title.lower():
                    w.activate()
                    return True
        except Exception as e:
            logger.error(f"Error focusing window: {e}")
        return False
    
    def minimize_window(self, title_pattern: str) -> bool:
        if not self._available:
            return False
        try:
            for w in self.gw.getAllWindows():
                if title_pattern.lower() in w.title.lower():
                    w.minimize()
                    return True
        except Exception as e:
            logger.error(f"Error minimizing window: {e}")
        return False
    
    def maximize_window(self, title_pattern: str) -> bool:
        if not self._available:
            return False
        try:
            for w in self.gw.getAllWindows():
                if title_pattern.lower() in w.title.lower():
                    w.maximize()
                    return True
        except Exception as e:
            logger.error(f"Error maximizing window: {e}")
        return False
    
    def close_window(self, title_pattern: str) -> bool:
        if not self._available:
            return False
        try:
            for w in self.gw.getAllWindows():
                if title_pattern.lower() in w.title.lower():
                    w.close()
                    return True
        except Exception as e:
            logger.error(f"Error closing window: {e}")
        return False
    
    def set_window_position(self, title_pattern: str, x: int, y: int, width: int, height: int) -> bool:
        if not self._available:
            return False
        try:
            for w in self.gw.getAllWindows():
                if title_pattern.lower() in w.title.lower():
                    w.moveTo(x, y, width, height)
                    return True
        except Exception as e:
            logger.error(f"Error setting window position: {e}")
        return False
    
    def list_processes(self) -> list[dict]:
        if not self._available:
            return []
        
        import psutil
        processes = []
        try:
            for proc in psutil.process_iter(['pid', 'name', 'username']):
                processes.append({
                    "pid": proc.info['pid'],
                    "name": proc.info['name'],
                    "username": proc.info['username'],
                })
        except Exception as e:
            logger.error(f"Error listing processes: {e}")
        return processes
    
    def get_process_by_name(self, name: str) -> Optional[dict]:
        processes = self.list_processes()
        for proc in processes:
            if name.lower() in proc['name'].lower():
                return proc
        return None
    
    def kill_process(self, pid: int) -> bool:
        try:
            import psutil
            psutil.Process(pid).kill()
            return True
        except Exception as e:
            logger.error(f"Error killing process: {e}")
        return False
    
    def start_process(self, command: str) -> Optional[int]:
        try:
            import subprocess
            proc = subprocess.Popen(command, shell=True)
            return proc.pid
        except Exception as e:
            logger.error(f"Error starting process: {e}")
        return None
    
    def find_installed_apps(self) -> list[dict]:
        apps = []
        try:
            import winreg
            # Check common registry locations
            paths = [
                r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
                r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"
            ]
            for path in paths:
                try:
                    key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path)
                    i = 0
                    while True:
                        try:
                            subkey_name = winreg.EnumKey(key, i)
                            subkey = winreg.OpenKey(key, subkey_name)
                            try:
                                display_name = winreg.QueryValueEx(subkey, "DisplayName")[0]
                                try:
                                    install_location = winreg.QueryValueEx(subkey, "InstallLocation")[0]
                                except FileNotFoundError:
                                    install_location = ""
                                apps.append({
                                    "name": display_name,
                                    "path": install_location,
                                    "source": "registry"
                                })
                            except FileNotFoundError:
                                pass
                            finally:
                                winreg.CloseKey(subkey)
                            i += 1
                        except OSError:
                            break
                    winreg.CloseKey(key)
                except OSError:
                    pass
        except Exception as e:
            logger.error(f"Error finding installed apps: {e}")
        return apps
    
    def get_app_path(self, app_name: str) -> Optional[str]:
        apps = self.find_installed_apps()
        for app in apps:
            if app_name.lower() in app['name'].lower():
                return app['path']
        return None
    
    def send_keys(self, keys: str) -> bool:
        try:
            import pyautogui
            pyautogui.write(keys)
            return True
        except Exception as e:
            logger.error(f"Error sending keys: {e}")
        return False
    
    def send_mouse_click(self, x: int, y: int, button: str = "left") -> bool:
        try:
            import pyautogui
            pyautogui.click(x, y, button=button)
            return True
        except Exception as e:
            logger.error(f"Error clicking mouse: {e}")
        return False
    
    def send_mouse_move(self, x: int, y: int) -> bool:
        try:
            import pyautogui
            pyautogui.moveTo(x, y)
            return True
        except Exception as e:
            logger.error(f"Error moving mouse: {e}")
        return False
    
    def get_screen_resolution(self) -> tuple[int, int]:
        try:
            import pyautogui
            return pyautogui.size()
        except Exception:
            return (1920, 1080)
    
    def get_os_version(self) -> str:
        return f"Windows {platform.release()}"
    
    def get_username(self) -> str:
        try:
            return os.getlogin()
        except (OSError, FileNotFoundError):
            return os.getenv("USER", os.getenv("USERNAME", "unknown"))
    
    def get_home_dir(self) -> str:
        return os.path.expanduser("~")


class LinuxBackend:
    """Linux-specific implementation using X11 and subprocess."""
    
    def __init__(self):
        self._available = True
        self._xlib_available = False
        self.pyautogui = None
        
        # Lazy-load X11 dependencies only when needed
        try:
            from Xlib import X, display, Xatom
            self.Xlib_display = display
            self.Xlib_X = X
            self.Xlib_Xatom = Xatom
            # Test if we can actually connect to X server
            try:
                d = display.Display()
                d.close()
                self._xlib_available = True
            except Exception:
                logger.warning("Cannot connect to X server, limited window support")
        except ImportError:
            logger.warning("python-xlib not available, limited window support")
        
        # Lazy-load pyautogui only when needed
        try:
            import pyautogui
            # Test if pyautogui can initialize
            pyautogui.size()
            self.pyautogui = pyautogui
        except ImportError:
            logger.warning("pyautogui not available, limited input control")
        except Exception as e:
            logger.warning(f"pyautogui initialization failed: {e}")
    
    def get_windows(self) -> list[dict]:
        if not self._xlib_available:
            return []
        
        windows = []
        try:
            d = self.Xlib_display.Display()
            root = d.screen().root
            # Get WM_CLIENT_LIST property
            wm_client_list = root.get_full_property(self.Xlib_Xatom.WM_CLIENT_LIST, self.Xlib_Xatom.WINDOW)
            if wm_client_list and wm_client_list.value:
                for wid in wm_client_list.value:
                    win = d.create_resource_object('window', wid)
                    name_prop = win.get_full_property(self.Xlib_Xatom.WM_NAME, self.Xlib_Xatom.STRING)
                    if name_prop:
                        name = name_prop.value.decode('utf-8', errors='ignore')
                        geom = win.get_geometry()
                        windows.append({
                            "title": name,
                            "wid": wid,
                            "x": geom.x,
                            "y": geom.y,
                            "width": geom.width,
                            "height": geom.height,
                            "focused": False,  # Would need additional checks
                        })
        except Exception as e:
            logger.error(f"Error getting windows on Linux: {e}")
        return windows
    
    def get_focused_window(self) -> Optional[dict]:
        if not self._xlib_available:
            return None
        try:
            d = self.Xlib_display.Display()
            focus = d.get_input_focus().focus
            name_prop = focus.get_full_property(self.Xlib_Xatom.WM_NAME, self.Xlib_Xatom.STRING)
            if name_prop:
                name = name_prop.value.decode('utf-8', errors='ignore')
                geom = focus.get_geometry()
                return {
                    "title": name,
                    "wid": focus.id,
                    "x": geom.x,
                    "y": geom.y,
                    "width": geom.width,
                    "height": geom.height,
                }
        except Exception as e:
            logger.debug(f"get_geometry failed: {e}")
        return None
    
    def focus_window(self, title_pattern: str) -> bool:
        if not self._xlib_available:
            return False
        try:
            d = self.Xlib_display.Display()
            root = d.screen().root
            wm_client_list = root.get_full_property(self.Xlib_Xatom.WM_CLIENT_LIST, self.Xlib_Xatom.WINDOW)
            if wm_client_list and wm_client_list.value:
                for wid in wm_client_list.value:
                    win = d.create_resource_object('window', wid)
                    name_prop = win.get_full_property(self.Xlib_Xatom.WM_NAME, self.Xlib_Xatom.STRING)
                    if name_prop and title_pattern.lower() in name_prop.value.decode('utf-8', errors='ignore').lower():
                        win.set_input_focus(self.Xlib_X.RevertToNone, self.Xlib_X.CurrentTime)
                        win.configure(stack_mode=self.Xlib_X.Above)
                        d.sync()
                        return True
        except Exception as e:
            logger.error(f"Error focusing window on Linux: {e}")
        return False
    
    def minimize_window(self, title_pattern: str) -> bool:
        # Requires EWMH support - simplified implementation
        logger.warning("Window minimization on Linux requires EWMH support")
        return False
    
    def maximize_window(self, title_pattern: str) -> bool:
        logger.warning("Window maximization on Linux requires EWMH support")
        return False
    
    def close_window(self, title_pattern: str) -> bool:
        if not self._xlib_available:
            return False
        try:
            d = self.Xlib_display.Display()
            root = d.screen().root
            wm_client_list = root.get_full_property(self.Xlib_Xatom.WM_CLIENT_LIST, self.Xlib_Xatom.WINDOW)
            if wm_client_list and wm_client_list.value:
                for wid in wm_client_list.value:
                    win = d.create_resource_object('window', wid)
                    name_prop = win.get_full_property(self.Xlib_Xatom.WM_NAME, self.Xlib_Xatom.STRING)
                    if name_prop and title_pattern.lower() in name_prop.value.decode('utf-8', errors='ignore').lower():
                        # Send WM_DELETE_WINDOW message
                        wm_delete = d.intern_atom('WM_DELETE_WINDOW')
                        win.send_event(wm_delete, 0)
                        d.sync()
                        return True
        except Exception as e:
            logger.error(f"Error closing window on Linux: {e}")
        return False
    
    def set_window_position(self, title_pattern: str, x: int, y: int, width: int, height: int) -> bool:
        if not self._xlib_available:
            return False
        try:
            d = self.Xlib_display.Display()
            root = d.screen().root
            wm_client_list = root.get_full_property(self.Xlib_Xatom.WM_CLIENT_LIST, self.Xlib_Xatom.WINDOW)
            if wm_client_list and wm_client_list.value:
                for wid in wm_client_list.value:
                    win = d.create_resource_object('window', wid)
                    name_prop = win.get_full_property(self.Xlib_Xatom.WM_NAME, self.Xlib_Xatom.STRING)
                    if name_prop and title_pattern.lower() in name_prop.value.decode('utf-8', errors='ignore').lower():
                        win.configure(x=x, y=y, width=width, height=height)
                        d.sync()
                        return True
        except Exception as e:
            logger.error(f"Error setting window position on Linux: {e}")
        return False
    
    def list_processes(self) -> list[dict]:
        import psutil
        processes = []
        try:
            for proc in psutil.process_iter(['pid', 'name', 'username']):
                processes.append({
                    "pid": proc.info['pid'],
                    "name": proc.info['name'],
                    "username": proc.info['username'],
                })
        except Exception as e:
            logger.error(f"Error listing processes: {e}")
        return processes
    
    def get_process_by_name(self, name: str) -> Optional[dict]:
        processes = self.list_processes()
        for proc in processes:
            if name.lower() in proc['name'].lower():
                return proc
        return None
    
    def kill_process(self, pid: int) -> bool:
        try:
            import psutil
            psutil.Process(pid).kill()
            return True
        except Exception as e:
            logger.error(f"Error killing process: {e}")
        return False
    
    def start_process(self, command: str) -> Optional[int]:
        try:
            import subprocess
            proc = subprocess.Popen(command, shell=True)
            return proc.pid
        except Exception as e:
            logger.error(f"Error starting process: {e}")
        return None
    
    def find_installed_apps(self) -> list[dict]:
        apps = []
        # Search common Linux locations
        import subprocess
        try:
            # Check .desktop files
            desktop_dirs = [
                "/usr/share/applications",
                "/usr/local/share/applications",
                os.path.expanduser("~/.local/share/applications")
            ]
            for desk_dir in desktop_dirs:
                if os.path.exists(desk_dir):
                    for f in os.listdir(desk_dir):
                        if f.endswith('.desktop'):
                            apps.append({
                                "name": f.replace('.desktop', ''),
                                "path": os.path.join(desk_dir, f),
                                "source": "desktop_file"
                            })
        except Exception as e:
            logger.error(f"Error finding installed apps on Linux: {e}")
        return apps
    
    def get_app_path(self, app_name: str) -> Optional[str]:
        # Try which command
        try:
            import subprocess
            result = subprocess.run(['which', app_name], capture_output=True, text=True)
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception as e:
            logger.debug(f"strip failed: {e}")
        
        # Search installed apps
        apps = self.find_installed_apps()
        for app in apps:
            if app_name.lower() in app['name'].lower():
                return app['path']
        return None
    
    def send_keys(self, keys: str) -> bool:
        if self.pyautogui:
            try:
                self.pyautogui.write(keys)
                return True
            except Exception as e:
                logger.error(f"Error sending keys: {e}")
        return False
    
    def send_mouse_click(self, x: int, y: int, button: str = "left") -> bool:
        if self.pyautogui:
            try:
                self.pyautogui.click(x, y, button=button)
                return True
            except Exception as e:
                logger.error(f"Error clicking mouse: {e}")
        return False
    
    def send_mouse_move(self, x: int, y: int) -> bool:
        if self.pyautogui:
            try:
                self.pyautogui.moveTo(x, y)
                return True
            except Exception as e:
                logger.error(f"Error moving mouse: {e}")
        return False
    
    def get_screen_resolution(self) -> tuple[int, int]:
        if self.pyautogui:
            try:
                return self.pyautogui.size()
            except Exception as e:
                logger.debug(f"size failed: {e}")
        # Fallback: use xrandr
        try:
            import subprocess
            result = subprocess.run(['xrandr'], capture_output=True, text=True)
            for line in result.stdout.split('\n'):
                if ' connected' in line:
                    parts = line.split()
                    for part in parts:
                        if 'x' in part and '+' in part:
                            res = part.split('+')[0]
                            w, h = map(int, res.split('x'))
                            return (w, h)
        except Exception as e:
            logger.debug(f"return failed: {e}")
        return (1920, 1080)
    
    def get_os_version(self) -> str:
        try:
            with open('/etc/os-release') as f:
                for line in f:
                    if line.startswith('PRETTY_NAME='):
                        return line.split('=')[1].strip().strip('"')
        except Exception as e:
            logger.debug(f"split failed: {e}")
        return f"Linux {platform.release()}"
    
    def get_username(self) -> str:
        try:
            return os.getlogin()
        except (OSError, FileNotFoundError):
            return os.getenv("USER", os.getenv("USERNAME", "unknown"))
    
    def get_home_dir(self) -> str:
        return os.path.expanduser("~")


class MacOSBackend:
    """macOS-specific implementation using AppKit and subprocess."""
    
    def __init__(self):
        self._available = True
        try:
            from AppKit import NSWorkspace
            self.NSWorkspace = NSWorkspace
        except ImportError:
            logger.warning("AppKit not available, limited app discovery")
            self.NSWorkspace = None
        
        try:
            import pyautogui
            self.pyautogui = pyautogui
        except ImportError:
            logger.warning("pyautogui not available, limited input control")
            self.pyautogui = None
    
    def get_windows(self) -> list[dict]:
        # macOS window access requires Accessibility permissions
        logger.warning("Window enumeration on macOS requires Accessibility permissions")
        return []
    
    def get_focused_window(self) -> Optional[dict]:
        logger.warning("Focused window detection on macOS requires Accessibility permissions")
        return None
    
    def focus_window(self, title_pattern: str) -> bool:
        logger.warning("Window focusing on macOS requires Accessibility permissions")
        return False
    
    def minimize_window(self, title_pattern: str) -> bool:
        return False
    
    def maximize_window(self, title_pattern: str) -> bool:
        return False
    
    def close_window(self, title_pattern: str) -> bool:
        return False
    
    def set_window_position(self, title_pattern: str, x: int, y: int, width: int, height: int) -> bool:
        return False
    
    def list_processes(self) -> list[dict]:
        import psutil
        processes = []
        try:
            for proc in psutil.process_iter(['pid', 'name', 'username']):
                processes.append({
                    "pid": proc.info['pid'],
                    "name": proc.info['name'],
                    "username": proc.info['username'],
                })
        except Exception as e:
            logger.error(f"Error listing processes: {e}")
        return processes
    
    def get_process_by_name(self, name: str) -> Optional[dict]:
        processes = self.list_processes()
        for proc in processes:
            if name.lower() in proc['name'].lower():
                return proc
        return None
    
    def kill_process(self, pid: int) -> bool:
        try:
            import psutil
            psutil.Process(pid).kill()
            return True
        except Exception as e:
            logger.error(f"Error killing process: {e}")
        return False
    
    def start_process(self, command: str) -> Optional[int]:
        try:
            import subprocess
            proc = subprocess.Popen(command, shell=True)
            return proc.pid
        except Exception as e:
            logger.error(f"Error starting process: {e}")
        return None
    
    def find_installed_apps(self) -> list[dict]:
        apps = []
        if self.NSWorkspace:
            try:
                workspace = self.NSWorkspace.sharedWorkspace()
                running_apps = workspace.runningApplications()
                for app in running_apps:
                    apps.append({
                        "name": app.localizedName(),
                        "path": app.bundlePath(),
                        "source": "running"
                    })
            except Exception as e:
                logger.error(f"Error finding running apps: {e}")
        
        # Also check Applications folder
        apps_dir = "/Applications"
        if os.path.exists(apps_dir):
            for item in os.listdir(apps_dir):
                if item.endswith('.app'):
                    apps.append({
                        "name": item.replace('.app', ''),
                        "path": os.path.join(apps_dir, item),
                        "source": "applications_folder"
                    })
        return apps
    
    def get_app_path(self, app_name: str) -> Optional[str]:
        apps = self.find_installed_apps()
        for app in apps:
            if app_name.lower() in app['name'].lower():
                return app['path']
        return None
    
    def send_keys(self, keys: str) -> bool:
        if self.pyautogui:
            try:
                self.pyautogui.write(keys)
                return True
            except Exception as e:
                logger.error(f"Error sending keys: {e}")
        return False
    
    def send_mouse_click(self, x: int, y: int, button: str = "left") -> bool:
        if self.pyautogui:
            try:
                self.pyautogui.click(x, y, button=button)
                return True
            except Exception as e:
                logger.error(f"Error clicking mouse: {e}")
        return False
    
    def send_mouse_move(self, x: int, y: int) -> bool:
        if self.pyautogui:
            try:
                self.pyautogui.moveTo(x, y)
                return True
            except Exception as e:
                logger.error(f"Error moving mouse: {e}")
        return False
    
    def get_screen_resolution(self) -> tuple[int, int]:
        if self.pyautogui:
            try:
                return self.pyautogui.size()
            except Exception as e:
                logger.debug(f"size failed: {e}")
        return (1920, 1080)
    
    def get_os_version(self) -> str:
        return f"macOS {platform.release()}"
    
    def get_username(self) -> str:
        try:
            return os.getlogin()
        except (OSError, FileNotFoundError):
            return os.getenv("USER", os.getenv("USERNAME", "unknown"))
    
    def get_home_dir(self) -> str:
        return os.path.expanduser("~")


class FallbackBackend:
    """Fallback implementation with minimal functionality."""
    
    def get_windows(self) -> list[dict]:
        return []
    
    def get_focused_window(self) -> Optional[dict]:
        return None
    
    def focus_window(self, title_pattern: str) -> bool:
        return False
    
    def minimize_window(self, title_pattern: str) -> bool:
        return False
    
    def maximize_window(self, title_pattern: str) -> bool:
        return False
    
    def close_window(self, title_pattern: str) -> bool:
        return False
    
    def set_window_position(self, title_pattern: str, x: int, y: int, width: int, height: int) -> bool:
        return False
    
    def list_processes(self) -> list[dict]:
        return []
    
    def get_process_by_name(self, name: str) -> Optional[dict]:
        return None
    
    def kill_process(self, pid: int) -> bool:
        return False
    
    def start_process(self, command: str) -> Optional[int]:
        return None
    
    def find_installed_apps(self) -> list[dict]:
        return []
    
    def get_app_path(self, app_name: str) -> Optional[str]:
        return None
    
    def send_keys(self, keys: str) -> bool:
        return False
    
    def send_mouse_click(self, x: int, y: int, button: str = "left") -> bool:
        return False
    
    def send_mouse_move(self, x: int, y: int) -> bool:
        return False
    
    def get_screen_resolution(self) -> tuple[int, int]:
        return (1920, 1080)
    
    def get_os_version(self) -> str:
        return f"Unknown ({platform.system()} {platform.release()})"
    
    def get_username(self) -> str:
        return os.getenv("USER", "unknown")
    
    def get_home_dir(self) -> str:
        return os.path.expanduser("~")


# Singleton instance
_platform_instance: Optional[PlatformAbstraction] = None


def get_platform() -> PlatformAbstraction:
    """Get the global platform abstraction instance."""
    global _platform_instance
    if _platform_instance is None:
        _platform_instance = PlatformAbstraction()
    return _platform_instance


# Convenience functions for direct use
def get_windows() -> list[dict]:
    return get_platform().get_windows()


def get_focused_window() -> Optional[dict]:
    return get_platform().get_focused_window()


def focus_window(title_pattern: str) -> bool:
    return get_platform().focus_window(title_pattern)


def list_processes() -> list[dict]:
    return get_platform().list_processes()


def find_installed_apps() -> list[dict]:
    return get_platform().find_installed_apps()


def get_app_path(app_name: str) -> Optional[str]:
    return get_platform().get_app_path(app_name)


def get_screen_resolution() -> tuple[int, int]:
    return get_platform().get_screen_resolution()


def get_os_info() -> dict:
    """Get comprehensive OS information."""
    p = get_platform()
    return {
        "platform": CURRENT_PLATFORM,
        "os_version": p.get_os_version(),
        "username": p.get_username(),
        "home_dir": p.get_home_dir(),
        "screen_resolution": p.get_screen_resolution(),
        "is_windows": IS_WINDOWS,
        "is_linux": IS_LINUX,
        "is_macos": IS_MACOS,
    }
