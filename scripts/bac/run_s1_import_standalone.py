"""
Run S1 import in a subprocess. Reads one JSON line from stdin (InSARTaskRequest),
prints PROGRESS\t<pct>\t<msg> per update and RESULT\t<json> at end.
Called by desktop with isce2-build Python + PATH/PYTHONPATH for ISCE2.
"""
from __future__ import annotations

import os
import sys

# Add DLL search paths for ISCE2 .pyd before any isce2 import (Windows)
_env_bin = os.path.join(os.path.dirname(sys.executable), "Library", "bin")
if os.path.isdir(_env_bin):
    os.add_dll_directory(_env_bin)
_script_dir = os.path.dirname(os.path.abspath(__file__))
_ucrt = os.path.abspath(os.path.join(_script_dir, "..", "tools", "msys64", "ucrt64", "bin"))
if os.path.isdir(_ucrt):
    os.add_dll_directory(_ucrt)

import json

def main() -> None:
    try:
        if len(sys.argv) >= 2:
            with open(sys.argv[1], "r", encoding="utf-8") as f:
                line = f.readline()
        else:
            line = sys.stdin.readline()
        if not line:
            print("RESULT\t" + json.dumps({"success": False, "error_message": "No input"}))
            return
        request_dict = json.loads(line.strip())
    except Exception as e:
        print("RESULT\t" + json.dumps({"success": False, "error_message": str(e)}))
        return

    def progress_cb(pct: float, msg: str) -> None:
        print("PROGRESS\t" + str(pct) + "\t" + msg.replace("\t", " "), flush=True)

    try:
        from shared_models import InSARTaskRequest
        from backend.services.s1_processing_service import run_s1_import_from_request
        request = InSARTaskRequest.model_validate(request_dict)
        result = run_s1_import_from_request(request, progress_callback=progress_cb)
        print("RESULT\t" + json.dumps(result), flush=True)
    except Exception as e:
        print("RESULT\t" + json.dumps({
            "success": False,
            "slc_vrt_paths": [],
            "metadata": {},
            "error_message": str(e),
        }), flush=True)


if __name__ == "__main__":
    main()
