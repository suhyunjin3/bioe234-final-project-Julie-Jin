"""
Auto-discovery and MCP registration for tools and resources.

Scanning order for each .py tool file
--------------------------------------
1. Look for a companion  <n>.json  file (C9 JSON wrapper — preferred).
2. Fall back to a  TOOL_META  dict inside the .py file (legacy / backward compat).
3. If neither exists, skip the file with a warning.

Class vs plain-function detection
-----------------------------------
For each imported module the register tries:
  a. Find a class that has a  run()  method (Python Function Object Pattern).
     Instantiate it, call initiate(), wrap run() for MCP.
  b. Fall back to a plain function whose name matches the file stem.

Students can write either pattern and it will just work.
"""

from __future__ import annotations

import importlib
import inspect
import json
import sys
from functools import wraps
from pathlib import Path
from typing import Any, Callable, Optional

from Bio import SeqIO

from .resolve import resolve_to_seq, register_resource


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------

def register_tools(mcp, tools_dir: Path) -> None:
    """Auto-discover and register all tools in tools_dir with the MCP server."""

    for py_file in sorted(tools_dir.glob("*.py")):
        if py_file.name.startswith("_") or py_file.name == "__init__.py":
            continue

        module_name = py_file.stem
        import_path = _build_import_path(tools_dir, module_name)

        # --- Import the module ---
        try:
            module = importlib.import_module(import_path)
        except Exception as e:
            print(f"[register] WARNING: Could not import {import_path}: {e}", file=sys.stderr)
            continue

        # Primary source is now a companion .json file following the
        # C9 JSON schema (Function_Development_Specification.md).
        # TOOL_META inside the .py file is still accepted for backward compat.
        meta = _load_json_wrapper(py_file)
        if meta is None:
            if hasattr(module, "TOOL_META"):
                meta = module.TOOL_META
                print(
                    f"[register] NOTE: {py_file.name} uses TOOL_META (legacy). "
                    f"Consider adding a {module_name}.json wrapper.",
                    file=sys.stderr,
                )
            else:
                print(
                    f"[register] WARNING: {py_file.name} has no .json wrapper and no "
                    f"TOOL_META — skipping. Add a {module_name}.json file.",
                    file=sys.stderr,
                )
                continue

        # Class pattern (initiate/run) is now detected and handled first,
        # then falls back to plain function matching the file stem.
        callable_fn = _resolve_callable(module, module_name, py_file.name)
        if callable_fn is None:
            continue  # warning already printed inside _resolve_callable

        _register_tool(mcp, callable_fn, meta)

        display_name = _get_mcp_name(meta)
        print(f"[register] ✓ Tool registered:    {display_name}", file=sys.stderr)


def register_resources(mcp, data_dir: Path, module_name: str) -> None:
    """Auto-discover and register all sequence files in data_dir."""

    sequence_extensions = {".gb", ".gbk", ".genbank", ".fa", ".fasta", ".fna"}

    for data_file in sorted(data_dir.iterdir()):
        if data_file.is_dir():
            continue
        if data_file.suffix.lower() not in sequence_extensions:
            continue
        if data_file.name.startswith("_"):
            continue

        resource_name = data_file.stem
        register_resource(resource_name, data_file)

        resource_meta = _load_resource_metadata(data_file)
        _register_resource(mcp, data_file, resource_name, module_name, resource_meta)

        print(
            f"[register] ✓ Resource registered: {resource_name}"
            f"  ({resource_meta.get('description', data_file.name)})",
            file=sys.stderr,
        )


# ---------------------------------------------------------------------------
# Tool loading helpers
# ---------------------------------------------------------------------------

def _load_json_wrapper(py_file: Path) -> Optional[dict]:
    """[CHANGE] Load the companion C9 JSON wrapper file if it exists.

    The JSON file must sit next to the .py file and share its stem:
        reverse_complement.py  →  reverse_complement.json

    Returns the parsed dict, or None if the JSON file is absent.
    Prints a warning and returns None if the JSON is malformed.
    """
    json_file = py_file.with_suffix(".json")
    if not json_file.exists():
        return None
    try:
        return json.loads(json_file.read_text())
    except json.JSONDecodeError as e:
        print(
            f"[register] WARNING: Could not parse {json_file.name}: {e} — skipping.",
            file=sys.stderr,
        )
        return None


def _resolve_callable(module, module_name: str, filename: str) -> Optional[Callable]:
    """[CHANGE] Return the tool callable from a module.

    Tries in order:
      1. A class defined in this module that has a run() method
         (Python Function Object Pattern — initiate() called once here).
      2. A plain function whose name matches the file stem (legacy pattern).

    Returns None (and prints a warning) if neither is found.
    """
    # --- Try class pattern ---
    tool_class = _find_tool_class(module)
    if tool_class is not None:
        try:
            instance = tool_class()
            if hasattr(instance, "initiate") and callable(instance.initiate):
                instance.initiate()
            return instance.run
        except Exception as e:
            print(
                f"[register] WARNING: Could not instantiate {tool_class.__name__} "
                f"from {filename}: {e}",
                file=sys.stderr,
            )
            return None

    # --- Fall back to plain function ---
    if hasattr(module, module_name):
        return getattr(module, module_name)

    print(
        f"[register] WARNING: {filename} has no class with run() and no function "
        f"named '{module_name}'.\n"
        f"           Class pattern : define a class with initiate() and run().\n"
        f"           Plain function: def {module_name}(...):",
        file=sys.stderr,
    )
    return None


def _find_tool_class(module) -> Optional[type]:
    """[CHANGE] Return the first class defined in module that has a run() method.

    Only considers classes whose __module__ matches the module being scanned
    (i.e. defined here, not imported from elsewhere).
    """
    for _name, obj in inspect.getmembers(module, inspect.isclass):
        if obj.__module__ != module.__name__:
            continue
        if callable(getattr(obj, "run", None)):
            return obj
    return None


# ---------------------------------------------------------------------------
# MCP registration
# ---------------------------------------------------------------------------

def _get_mcp_name(meta: dict) -> str:
    """[CHANGE] Extract the MCP tool name from metadata.

    Checks in order:
      1. meta["execution_details"]["mcp_name"]  — C9 JSON wrapper (framework extension)
      2. meta["name"]                           — TOOL_META legacy or C9 display name
    """
    exec_details = meta.get("execution_details", {})
    if isinstance(exec_details, dict) and "mcp_name" in exec_details:
        return exec_details["mcp_name"]
    return meta.get("name", "unknown_tool")


def _get_seq_params(meta: dict) -> set[str]:
    """[CHANGE] Collect all parameter names that need sequence resolution.

    Checks:
      1. meta["execution_details"]["seq_params"]  — C9 JSON wrapper (framework extension)
      2. meta["seq_params"]                       — TOOL_META multi-sequence legacy
      3. meta["seq_param"]                        — TOOL_META single-sequence legacy
    """
    params: set[str] = set()

    exec_details = meta.get("execution_details", {})
    if isinstance(exec_details, dict):
        for p in exec_details.get("seq_params", []):
            params.add(p)

    for p in meta.get("seq_params", []):
        params.add(p)

    single = meta.get("seq_param")
    if single:
        params.add(single)

    return params


def _build_mcp_schema(meta: dict, func: Callable) -> Optional[dict]:
    """[CHANGE] Build a typed JSON schema for Gemini from the C9 inputs array.

    If the JSON wrapper has an "inputs" array (C9 spec), we construct an
    explicit typed schema so Gemini knows the exact type of each argument.
    Falls back to None (FastMCP then derives the schema from Python type hints)
    if no inputs array is present.

    C9 type  →  JSON Schema type
    --------------------------------
    string / str      →  string
    integer / int     →  integer
    number / float    →  number
    boolean / bool    →  boolean
    array / list      →  array
    object / dict     →  object
    """
    inputs = meta.get("inputs")
    if not inputs:
        return None  # let FastMCP use type-hint introspection

    type_map = {
        "string": "string",   "str": "string",
        "integer": "integer", "int": "integer",
        "number": "number",   "float": "number",
        "boolean": "boolean", "bool": "boolean",
        "array": "array",     "list": "array",
        "object": "object",   "dict": "object",
    }

    # Inspect the actual function signature to find which params have defaults
    try:
        sig = inspect.signature(func)
    except (ValueError, TypeError):
        sig = None

    properties: dict[str, Any] = {}
    required: list[str] = []

    for inp in inputs:
        name = inp.get("name", "")
        if not name:
            continue

        json_type = type_map.get(inp.get("type", "string").lower(), "string")
        prop: dict[str, Any] = {
            "type": json_type,
            "description": inp.get("description", ""),
        }
        properties[name] = prop

        # A param is required if the JSON doesn't mark it optional AND
        # the real function signature has no default for it.
        is_optional = inp.get("optional", False)
        has_default = False
        if sig and name in sig.parameters:
            has_default = sig.parameters[name].default is not inspect.Parameter.empty

        if not is_optional and not has_default:
            required.append(name)

    schema: dict[str, Any] = {"type": "object", "properties": properties}
    if required:
        schema["required"] = required
    return schema


def _register_tool(mcp, func: Callable, meta: dict) -> None:
    """Register a single tool callable with the MCP server."""

    mcp_name    = _get_mcp_name(meta)
    seq_params  = _get_seq_params(meta)
    description = meta.get("description", getattr(func, "__doc__", "") or "")
    schema      = _build_mcp_schema(meta, func)

    @wraps(func)
    def wrapped(**kwargs):
        for param in seq_params:
            if param in kwargs and kwargs[param] is not None:
                kwargs[param] = resolve_to_seq(kwargs[param])
        return func(**kwargs)

    wrapped.__name__ = mcp_name
    wrapped.__doc__  = description

    # Preserve type hints (FastMCP fallback schema generation)
    if hasattr(func, "__annotations__"):
        wrapped.__annotations__ = func.__annotations__

    # [CHANGE] Attach explicit schema when available so Gemini gets typed params
    if schema is not None:
        wrapped.__schema__ = schema

    mcp.tool(wrapped)


# ---------------------------------------------------------------------------
# Resource helpers
# ---------------------------------------------------------------------------

def _load_resource_metadata(data_file: Path) -> dict:
    """Load metadata from a .meta.json file if it exists."""
    meta_file = data_file.parent / f"{data_file.stem}.meta.json"
    if not meta_file.exists():
        meta_file = data_file.with_suffix(data_file.suffix + ".meta.json")
    if meta_file.exists():
        try:
            return json.loads(meta_file.read_text())
        except Exception:
            pass
    return {"description": _extract_description(data_file)}


def _extract_description(data_file: Path) -> str:
    """Extract a one-line description from a sequence file."""
    suffix = data_file.suffix.lower()
    try:
        if suffix in (".gb", ".gbk", ".genbank"):
            record = SeqIO.read(data_file, "genbank")
            definition = record.description or record.name or data_file.stem
            return f"{definition} ({len(record.seq)}bp, GenBank)"
        elif suffix in (".fa", ".fasta", ".fna"):
            record = SeqIO.read(data_file, "fasta")
            desc = record.description or data_file.stem
            return f"{desc} ({len(record.seq)}bp, FASTA)"
    except Exception:
        pass
    return f"Sequence file: {data_file.name}"


def _register_resource(
    mcp,
    data_file: Path,
    resource_name: str,
    module_name: str,
    meta: dict,
) -> None:
    """Register a single resource with MCP."""
    uri = f"resource://{module_name}/{resource_name}"
    description = meta.get("description", f"Sequence resource: {resource_name}")

    @mcp.resource(uri)
    def resource_reader() -> str:
        return data_file.read_text()

    resource_reader.__doc__  = description
    resource_reader.__name__ = resource_name


# ---------------------------------------------------------------------------
# Internal utility
# ---------------------------------------------------------------------------

def _build_import_path(tools_dir: Path, module_name: str) -> str:
    """Construct the dotted import path for a tool module."""
    parts = []
    current = tools_dir
    while current.name != "modules" and current.parent != current:
        parts.insert(0, current.name)
        current = current.parent
    parts.insert(0, "modules")
    return ".".join(parts) + f".{module_name}"