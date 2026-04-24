from __future__ import annotations

import os
import sys


base_dir = getattr(sys, "_MEIPASS", None)
if base_dir:
    if base_dir not in sys.path:
        sys.path.insert(0, base_dir)
    os.environ.setdefault("TCL_LIBRARY", os.path.join(base_dir, "_tcl_data"))
    os.environ.setdefault("TK_LIBRARY", os.path.join(base_dir, "_tk_data"))
