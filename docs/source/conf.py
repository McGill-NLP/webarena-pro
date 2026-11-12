from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version as package_version
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "webarena-pro-core" / "src"))
sys.path.insert(0, str(REPO_ROOT / "webarena-pro-bgym" / "src"))

sys.path.insert(0, str(REPO_ROOT / "webarena-pro-media" / "src"))

project = "WebArena-Pro"
author = "WebArena-Pro contributors"

try:
    release = package_version("webarena-pro-core")
except PackageNotFoundError:
    release = "0.1.0"

version = release

extensions = [
    "myst_parser",
    "sphinx.ext.autodoc",
    "sphinx.ext.autosummary",
    "sphinx.ext.napoleon",
]

source_suffix = {
    ".rst": "restructuredtext",
    ".md": "markdown",
}

root_doc = "index"
exclude_patterns = []

html_theme = "sphinx_rtd_theme"
html_title = "WebArena-Pro Documentation"

myst_enable_extensions = [
    "colon_fence",
    "deflist",
]
# Resolve Markdown section links in both GitHub and the generated docs.
myst_heading_anchors = 3

autoclass_content = "both"
autodoc_typehints = "description"
autodoc_default_options = {
    "members": True,
    "undoc-members": True,
    "show-inheritance": True,
}
autodoc_mock_imports = [
    "icalendar",
    "openai",
    "playwright",
    "requests",
    "vobject",
    "webdav4",
    "webdav4.fsspec",
]
