"""
Auto-register DLL search directories for ISCE2 native extensions on Windows.

Python 3.8+ no longer uses PATH for DLL dependency resolution.  This module
is placed on PYTHONPATH (via _get_stack_env) so that it executes during
interpreter startup in *both* the main SentinelWrapper subprocess and every
multiprocessing worker spawned by it.

Activated only when the env var INSAR_DLL_DIRS is set (semicolon-separated
list of directories).  The desktop .venv process does not set this variable,
so there is no side-effect on the UI process.
"""
import os as _os

_dirs = _os.environ.get("INSAR_DLL_DIRS", "")
if _dirs and hasattr(_os, "add_dll_directory"):
    for _d in _dirs.split(_os.pathsep):
        _d = _d.strip()
        if _d and _os.path.isdir(_d):
            try:
                _os.add_dll_directory(_d)
            except OSError:
                pass
