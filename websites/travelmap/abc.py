"""Compatibility shim so a local abc.py does not shadow Python's stdlib abc module."""

from __future__ import annotations

import importlib.util
import sysconfig
from pathlib import Path


_stdlib_abc = Path(sysconfig.get_path("stdlib")) / "abc.py"
_spec = importlib.util.spec_from_file_location("_stdlib_abc", _stdlib_abc)
if _spec is None or _spec.loader is None:
    raise RuntimeError("Unable to load stdlib abc module.")

_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)

__doc__ = _module.__doc__
__all__ = getattr(_module, "__all__", [])

for _name in dir(_module):
    if _name.startswith("__") and _name not in {"__doc__", "__all__"}:
        continue
    globals()[_name] = getattr(_module, _name)
