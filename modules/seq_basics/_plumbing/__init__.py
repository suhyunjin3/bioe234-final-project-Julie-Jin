"""Package marker and convenience re-export.
 
server.py contains:
    from modules.seq_basics._plumbing import resolve
 
For that import to work, Python needs:
  1. This __init__.py to mark _plumbing/ as a package.
  2. The `resolve` name to be importable from this namespace.
 
We expose `resolve` as a submodule reference so server.py can call
    resolve.list_resources()
just as the commented-out line in server.py expects.
 
Students: you do not need to edit this file.
"""

from modules.seq_basics._plumbing import resolve  # noqa: F401