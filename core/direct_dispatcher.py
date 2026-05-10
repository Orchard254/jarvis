"""
Direct Function Dispatcher for JARVIS.
Bypasses code generation for known skills by calling functions directly.
Provides instant execution with zero subprocess overhead.
"""
import importlib
import inspect
from typing import Any, Dict, Optional, Callable
import logging

logger = logging.getLogger(__name__)

# Known skill modules and their exposed functions
SKILL_MODULES = {
    "system": "skills.stdlib.system",
    "filesystem": "skills.stdlib.filesystem",
    "web": "skills.stdlib.web",
    "ui": "skills.stdlib.ui",
    "messaging": "skills.stdlib.messaging",
    "network": "skills.stdlib.network",
    "time_cal": "skills.stdlib.time_cal",
}

class DirectDispatcher:
    def __init__(self):
        self._loaded_modules: Dict[str, Any] = {}
        self._function_cache: Dict[str, Callable] = {}
        # Lazy loading to avoid import errors at module init
        self._modules_loaded = False

    def _load_modules(self):
        """Load skill modules on first use"""
        if self._modules_loaded:
            return
            
        for name, module_path in SKILL_MODULES.items():
            try:
                module = importlib.import_module(module_path)
                self._loaded_modules[name] = module
                logger.debug(f"Loaded skill module: {name} from {module_path}")
            except ImportError as e:
                logger.warning(f"Failed to load skill module {name}: {e}")
        
        self._modules_loaded = True

    def get_function(self, function_name: str) -> Optional[Callable]:
        """Get a function by name from loaded modules"""
        self._load_modules()  # Ensure modules are loaded
        
        if function_name in self._function_cache:
            return self._function_cache[function_name]

        # Search in all loaded modules
        for module_name, module in self._loaded_modules.items():
            if hasattr(module, function_name):
                func = getattr(module, function_name)
                if callable(func):
                    self._function_cache[function_name] = func
                    logger.debug(f"Cached function: {function_name} from {module_name}")
                    return func

        return None

    def execute(self, function_name: str, *args, **kwargs) -> Any:
        """Execute a function directly with provided arguments"""
        func = self.get_function(function_name)
        if not func:
            raise ValueError(f"Function '{function_name}' not found in any skill module")

        # Validate arguments
        sig = inspect.signature(func)
        try:
            bound = sig.bind(*args, **kwargs)
            bound.apply_defaults()
        except TypeError as e:
            raise ValueError(f"Invalid arguments for {function_name}: {e}")

        logger.info(f"Direct dispatch: {function_name}({args}, {kwargs})")
        return func(*args, **kwargs)

    def list_available_functions(self) -> Dict[str, Dict[str, Any]]:
        """List all available functions with their signatures"""
        available = {}
        for module_name, module in self._loaded_modules.items():
            for name in dir(module):
                obj = getattr(module, name)
                if callable(obj) and not name.startswith('_'):
                    try:
                        sig = inspect.signature(obj)
                        doc = inspect.getdoc(obj) or ""
                        available[f"{module_name}.{name}"] = {
                            "signature": str(sig),
                            "docstring": doc.split('\n')[0] if doc else "",
                            "module": module_name
                        }
                    except (ValueError, TypeError):
                        continue
        return available

    def is_known_function(self, function_name: str) -> bool:
        """Check if a function exists in loaded modules"""
        return self.get_function(function_name) is not None

# Global instance
dispatcher = DirectDispatcher()
