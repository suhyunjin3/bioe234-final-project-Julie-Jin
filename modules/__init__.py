"""This module auto-discovers every sub-package inside modules/ (like seq_basics,
crispr, cloning) and registers their tools and resources with the MCP server.
 
To add a new module:
    1. Create  modules/<your_module>/
    2. Add     modules/<your_module>/tools/    ← your .py tool files go here
    3. Add     modules/<your_module>/data/     ← your .gb / .fasta files go here
    4. Follow the same __init__.py / SKILL.md / _utils.py conventions as seq_basics
    register_all() will pick it up automatically on next server restart.
"""

from __future__ import annotations

import sys
from pathlib import Path

from modules.seq_basics._plumbing.register import register_tools, register_resources

def register_all(mcp) -> None:
    """
    Walk every sub-folder of modules/ and register its tools + resources.
 
    Expected layout per module
    --------------------------
    modules/<name>/tools/   — Python files each defining one tool function
    modules/<name>/data/    — Sequence files (.gb, .fasta, …)
 
    Folders that start with '_' (like __pycache__) are skipped automatically.
    """
    modules_dir = Path(__file__).parent  # .../modules/
 
    for module_dir in sorted(modules_dir.iterdir()):
        # [NEW] Skip non-directories and internal/private folders
        if not module_dir.is_dir() or module_dir.name.startswith("_"):
            continue
 
        module_name = module_dir.name
        tools_dir = module_dir / "tools"
        data_dir = module_dir / "data"
 
        # [NEW] Print to stderr so students can see which modules loaded.
        #       stderr is safe here — MCP stdio transport uses stdout only.
        print(f"[modules] Scanning module: {module_name}", file=sys.stderr)
 
        if tools_dir.exists():
            register_tools(mcp, tools_dir)
        else:
            print(f"[modules]   No tools/ folder found in {module_name}, skipping tools.", file=sys.stderr)
 
        if data_dir.exists():
            register_resources(mcp, data_dir, module_name=module_name)
        else:
            print(f"[modules]   No data/ folder found in {module_name}, skipping resources.", file=sys.stderr)
