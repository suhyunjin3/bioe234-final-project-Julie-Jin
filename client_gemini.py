"""
Requires a .env file in the project root containing:
    GEMINI_API_KEY="your_key_here"
 
Get a free key at: https://aistudio.google.com/api-keys
"""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any, Dict, List

from dotenv import load_dotenv
from fastmcp import Client
from google import genai
from google.genai import types, errors

# Helpers: skill context + system prompt
# ---------------------------------------------------------------------------
def _load_skill_context(modules_dir: Path) -> str:
    """Load SKILL.md files from all modules and combine them."""
    skill_texts = []
    for module_dir in sorted(modules_dir.iterdir()):
        if not module_dir.is_dir() or module_dir.name.startswith("_"):
            continue

        skill_file = module_dir / "SKILL.md"
        if skill_file.exists():
            skill_texts.append(skill_file.read_text())

    return "\n\n---\n\n".join(skill_texts)


def _strip_ctx_from_schema(schema: dict) -> dict:
    schema = dict(schema or {})
    props = dict(schema.get("properties", {}))
    props.pop("ctx", None)
    schema["properties"] = props

    if "required" in schema:
        schema["required"] = [r for r in schema["required"] if r != "ctx"]

    return schema


def _build_system_content(mcp_tools, mcp_resources, skill_context: str = "") -> types.Content:
    """Serialize MCP tools and resources into a system message for Gemini."""
    tools_json = [
        {
            "name": t.name,
            "description": getattr(t, "description", ""),
            "input_schema": getattr(t, "inputSchema", None),
        }
        for t in mcp_tools
    ]
 
    resources_json = []
    for r in mcp_resources:
        uri_obj = getattr(r, "uri", None) or getattr(r, "name", None)
        uri_str = str(uri_obj) if uri_obj is not None else None
        resource_name = uri_str.split("/")[-1] if uri_str else None
        resources_json.append({
            "uri": uri_str,
            "name": resource_name,
            "description": getattr(r, "description", ""),
        })
 
    payload = {
        "mcp_tools": tools_json,
        "mcp_resources": resources_json,
        "instruction": (
            "You may call MCP tools using their schemas. "
            "Tools that operate on sequences accept either a resource name (e.g., 'pBR322') "
            "or a raw DNA sequence string. Prefer using resource names when available. "
            "The server will resolve resource names to their sequences automatically."
        ),
    }
 
    system_text = "SYSTEM CONTEXT (capabilities, not user input):\n" + json.dumps(payload, indent=2)
    if skill_context:
        system_text += "\n\n--- SKILL GUIDANCE ---\n\n" + skill_context
 
    return types.Content(
        role="model",
        parts=[types.Part.from_text(text=system_text)],
    )
 
 
def _mcp_tool_to_fn_declaration(tool: Any) -> types.FunctionDeclaration:
    """Convert a FastMCP tool definition into a Gemini FunctionDeclaration."""
    params: Dict[str, Any] = getattr(tool, "inputSchema", None) or {"type": "object", "properties": {}}
    params = _strip_ctx_from_schema(params)
    desc = (getattr(tool, "description", None) or "").strip() or f"MCP tool: {tool.name}"
    return types.FunctionDeclaration(
        name=tool.name,
        description=desc,
        parameters_json_schema=params,
    )
 
 
def _prompt_result_to_contents(prompt_result: Any) -> List[types.Content]:
    """Convert a FastMCP prompt render result into Gemini Content messages."""
    msgs = getattr(prompt_result, "messages", None) or getattr(prompt_result, "message", None) or []
    out: List[types.Content] = []
    for m in msgs:
        role = getattr(m, "role", "user") or "user"
        content = getattr(m, "content", None)
        texts: List[str] = []
        if isinstance(content, str):
            texts = [content]
        elif isinstance(content, list):
            for part in content:
                t = getattr(part, "text", None)
                if t is None and isinstance(part, str):
                    t = part
                if t is not None:
                    texts.append(str(t))
        elif content is not None:
            texts = [str(content)]
        if texts:
            out.append(types.Content(role=role, parts=[types.Part.from_text(text="\n".join(texts))]))
    return out
 
 
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
async def _run_tool_loop(
    mcp,
    initial_resp,
    contents: List[types.Content],
    safe_generate_fn,
    model: str,
    config,
) -> tuple[str | None, List[types.Content]]:
    """Execute tool calls until Gemini produces a plain-text reply.
 
    Each iteration:
      1. Check if Gemini's response contains function calls.
      2. If yes: execute ALL of them, append results to contents, re-query.
      3. If no:  print Gemini's reply and return.
 
    Args:
        mcp:               FastMCP client (async, already connected).
        initial_resp:      The first Gemini response object to process.
        contents:          Full conversation so far (system + history + current turn).
                           This list is copied internally and NOT mutated.
        safe_generate_fn:  Callable matching safe_generate's signature.
        model:             Gemini model string.
        config:            GenerateContentConfig (includes tool declarations).
 
    Returns:
        (final_text, updated_contents)
        updated_contents includes all tool call / response turns that were
        appended during this loop — callers use this to update their history.
    """
    contents = list(contents)   # work on a copy; don't mutate caller's list
    resp = initial_resp
 
    while True:
        function_calls = resp.function_calls or []
 
        if not function_calls:
            # Gemini produced plain text — conversation turn is complete
            reply = resp.text or "[No text response]"
            print(f"\nGemini: {reply}\n")
            if not resp.candidates:
                print("\n[No response from Gemini — possibly a safety filter or quota issue]\n")
                return resp.text or "", contents

            # Append the final model response so it's part of history
            contents.append(resp.candidates[0].content)
            return resp.text, contents
  
        # Capture the model's function-call turn before executing anything
        fc_content = resp.candidates[0].content
 
        # Execute ALL tool calls from this single response in order
        fr_parts: List[types.Part] = []
        for fc in function_calls:
            tool_name = fc.name
            tool_args = dict(fc.args or {})
 
            print(f"\n[Tool call] → {tool_name}")
            print(json.dumps(tool_args, indent=2))
 
            try:
                tool_result = await mcp.call_tool(tool_name, tool_args)
                # Safely extract text from whatever FastMCP returns
                if isinstance(tool_result, list):
                    result_data = "\n".join(
                        getattr(item, "text", str(item)) for item in tool_result
                    )
                elif hasattr(tool_result, "content"):
                    result_data = "\n".join(
                        getattr(item, "text", str(item)) for item in tool_result.content
                    )
                else:
                    result_data = str(tool_result)
                fn_response = {"result": result_data}
            except Exception as e:
                fn_response = {"error": str(e)}
 
            print(f"[Tool result] ← {tool_name}:")
            print(json.dumps(fn_response, indent=2))
 
            fr_parts.append(
                types.Part.from_function_response(name=tool_name, response=fn_response)
            )
 
        # Pack all function responses into a single Content turn and append
        fr_content = types.Content(role="user", parts=fr_parts)
        contents.extend([fc_content, fr_content])
 
        # Ask Gemini again with the tool results included
        resp = safe_generate_fn(model=model, contents=contents, config=config)
 

# CLI help
#----------------------------------------------------------------------------
def _print_help() -> None:
    print("""
        Commands:
        /help                         Show this help
        /tools                        List tools
        /resources                    List resources
        /resource <uri>               Read a resource
        /prompts                      List prompts
        /prompt <name> [json_args]    Render a prompt and run it through Gemini

        Examples:
        /resources
        /resource resource://seq_basics/pBR322
        /prompts
        /prompt my_prompt {"target": "ACGT..."}
        """)

# Main chat loop
#----------------------------------------------------------------------------
async def run_chat() -> None:
    load_dotenv()

    # 2026 Google's best model but limited to 20 calls/day (according to Gemini, not able to confirm)
    model = "gemini-2.5-flash"

    # can also use; smarter but 20 calls/day; use sparingly
    # model = "gemini-2.5-flash-preview"

    # The client will pick up GEMINI_API_KEY (or GOOGLE_API_KEY) from a .env file.
    # Create a (free) Gemini API key at https://aistudio.google.com/api-keys
    # You must add these lines to a new .env file with your API key:
    # GEMINI_API_KEY="YOUR_KEY_HERE"

    gemini = genai.Client()  # picks up GEMINI_API_KEY from .env automatically
    # for m in gemini.models.list():
    #     print(m.name)


    def safe_generate(*, model, contents, config, retries=3, backoff_seconds=2):
        """Call Gemini with automatic retry on 503 (server busy) errors."""
        for attempt in range(retries):
            try:
                return gemini.models.generate_content(
                    model=model,
                    contents=contents,
                    config=config,
                )
            except errors.ServerError as e:
                #503 UNAVAILABLE - Gemini servers are overloaded
                msg = str(e)
                if ("503" in msg or "UNAVAILABLE" in msg) and attempt < retries - 1:
                    wait = backoff_seconds * (2 ** attempt)
                    print(f"\n[Gemini busy (503). Retrying in {wait}s...]")
                    time.sleep(wait)
                    continue
                raise  # other server errors or final attempt
            except errors.ClientError as e:
                #429 RESOURCE_EXHAUSTED - rate limit hit
                msg = str(e)
                if "429" in msg or "RESOURCE_EXHAUSTED" in msg:
                    if attempt < retries - 1:
                        # Try to parse the suggested retry delay from the error message
                        import re
                        match = re.search(r"retry[^\d]*(\d+(?:\.\d+)?)\s*s", msg, re.IGNORECASE)
                        wait = float(match.group(1)) + 1 if match else backoff_seconds * (2 ** attempt)
                        wait = max(wait, 2)  # always wait at least 2 seconds
                        print(f"\n[Rate limit hit (429). Retrying in {wait:.0f}s...]")
                        time.sleep(wait)
                        continue
                raise

    # Launch the MCP server as a subprocess over stdio.
    async with Client("server.py") as mcp:

        # Discover capabilities
        mcp_tools = await mcp.list_tools()
        mcp_resources = await mcp.list_resources()
        mcp_prompts = await mcp.list_prompts()

        fn_decls = [_mcp_tool_to_fn_declaration(t) for t in mcp_tools]
        if fn_decls:
            tool_obj = types.Tool(function_declarations=fn_decls)
            config = types.GenerateContentConfig(tools=[tool_obj])
        else:
            # No tools registered.
            print("\n[WARNING] No tools were registered. Gemini will answer in plain text only.")
            config = types.GenerateContentConfig()
        # tool_config = types.Tool(function_declarations=fn_decls)
        # config = types.GenerateContentConfig(tools=[tool_config])        

        # Load skill context from SKILL.md files
        modules_dir = Path(__file__).parent / "modules"
        skill_context = _load_skill_context(modules_dir)
        system_content = _build_system_content(mcp_tools, mcp_resources, skill_context)

        # Print discovered capabilities at startup 
        print("\nConnected to MCP server.")
        print("Discovered tools:")
        for t in mcp_tools:
            print(f"  - {t.name}: {t.description}")

        print("\nDiscovered resources:")
        for r in mcp_resources:
            uri = getattr(r, "uri", None) or getattr(r, "name", None) or str(r)
            desc = getattr(r, "description", "") or ""
            print(f"  - {uri}" + (f": {desc}" if desc else ""))

        print("\nDiscovered prompts:")
        for p in mcp_prompts:
            name = getattr(p, "name", None) or str(p)
            desc = getattr(p, "description", "") or ""
            print(f"  - {name}" + (f": {desc}" if desc else ""))

        _print_help()
        print("\nType a request. Ctrl-C to quit.\n")

        #conversation history persists across turns
        conversation_history: List[types.Content] = []

        while True:
            user_text = input("You: ").strip()
            if not user_text:
                continue
            
            #slash commands----------------------
            if user_text.startswith("/"):
                parts = user_text.split(maxsplit=2)
                cmd = parts[0].lower()

                if cmd in {"/help", "/?"}:
                    _print_help()

                elif cmd == "/tools":
                    mcp_tools = await mcp.list_tools()
                    print("\nTools:")
                    for t in mcp_tools:
                        print(f"  - {t.name}: {t.description}")
                    print("")

                elif cmd == "/resources":
                    mcp_resources = await mcp.list_resources()
                    print("\nResources:")
                    for r in mcp_resources:
                        uri = getattr(r, "uri", None) or getattr(r, "name", None) or str(r)
                        desc = getattr(r, "description", "") or ""
                        print(f"  - {uri}" + (f": {desc}" if desc else ""))
                    print("")

                elif cmd == "/resource":
                    if len(parts) < 2:
                        print("\nUsage: /resource <uri>\n")
                    else:
                        content_list = await mcp.read_resource(parts[1])
                        print(f"\nResource: {parts[1]}")
                        for c in content_list:
                            txt = getattr(c, "text", None)
                            if txt is None:
                                txt = str(c)
                            print(txt)
                        print("")

                elif cmd == "/prompts":
                    mcp_prompts = await mcp.list_prompts()
                    print("\nPrompts:")
                    for p in mcp_prompts:
                        name = getattr(p, "name", None) or str(p)
                        desc = getattr(p, "description", "") or ""
                        print(f"  - {name}" + (f": {desc}" if desc else ""))
                    print("")

                elif cmd == "/prompt":
                    if len(parts) < 2:
                        print("\nUsage: /prompt <name> [json_args]\n")
                        continue
                    prompt_name = parts[1]
                    args: Dict[str, Any] = {}
                    if len(parts) == 3:
                        try:
                            args = json.loads(parts[2])
                        except json.JSONDecodeError as e:
                            print(f"\nCould not parse json_args: {e}\n")
                            continue

                    prompt_result = await mcp.get_prompt(prompt_name, args)
                    prompt_contents = _prompt_result_to_contents(prompt_result)

                    if not prompt_contents:
                        print("\nPrompt rendered no messages.\n")
                        continue

                    initial_contents = [system_content, *prompt_contents]
                    resp = safe_generate(model=model, contents=initial_contents, config=config)

                    await _run_tool_loop(mcp, resp, initial_contents, safe_generate, model, config)

                else:
                    print("\nUnknown command. Type /help\n")
 
                continue
 
            # Free-form turn ------------------------------------------------
 
            # add to history
            user_content = types.Content(
                role="user",
                parts=[types.Part.from_text(text=user_text)],
            )
            conversation_history.append(user_content)
 
            # Always send: system message + full conversation history
            current_contents = [system_content, *conversation_history]
 
            resp = safe_generate(model=model, contents=current_contents, config=config)
 
            # use shared tool loop helper (no duplication)
            _final_text, updated_contents = await _run_tool_loop(
                mcp, resp, current_contents, safe_generate, model, config
            )
 
            # sync history: everything appended beyond current_contents
            # (tool call turns + final model response) becomes part of history
            new_entries = updated_contents[len(current_contents):]
            conversation_history.extend(new_entries)
 
 
if __name__ == "__main__":
    asyncio.run(run_chat())