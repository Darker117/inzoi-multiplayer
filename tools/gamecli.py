"""Run one inZOI CLI command against the running game (its built-in MCP server), or a ModKit editor tool.

Usage:  python tools/gamecli.py entity.get_possessed
        python tools/gamecli.py motion.play anim_id=GreetingPositiveA entity_id=1234
        python tools/gamecli.py --list [category]
        python tools/gamecli.py --modkit modkit_status        (talk to the ModKit editor instead, port 11213)
        python tools/gamecli.py --modkit --tools [filter]     (list ModKit tools with their parameters)
        python tools/gamecli.py --tools [filter]              (same for the game)

Dots in the command name are fine (they're sent as underscores, which is what the MCP tool names use).
Values that look like JSON (numbers, true/false, lists) are parsed; everything else is sent as a string.
"""
import json
import sys
import urllib.request

GAME_MCP = "http://127.0.0.1:11212/mcp"
MODKIT_MCP = "http://127.0.0.1:11213/mcp"


def rpc(method: str, params: dict, url: str = GAME_MCP):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    req = urllib.request.Request(url, body, {"Content-Type": "application/json",
                                             "Accept": "application/json, text/event-stream"})
    raw = urllib.request.urlopen(req, timeout=120).read().decode("utf-8", "replace")
    if raw.startswith(("event:", "data:")):
        raw = "\n".join(l[5:].strip() for l in raw.splitlines() if l.startswith("data:"))
    return json.loads(raw)


def call(tool: str, _url: str = GAME_MCP, **args):
    res = rpc("tools/call", {"name": tool.replace(".", "_"), "arguments": args}, _url)
    if "error" in res:
        return {"_rpc_error": res["error"]}
    res = res.get("result", {})
    if res.get("structuredContent") is not None:
        return res["structuredContent"]
    text = " ".join(c.get("text", "") for c in res.get("content", []))
    try:
        return json.loads(text)
    except ValueError:
        return {"_error" if res.get("isError") else "_text": text}


def _value(v: str):
    try:
        return json.loads(v)
    except ValueError:
        return v


def main(argv):
    if not argv:
        print(__doc__)
        return 1
    url = GAME_MCP
    if argv[0] == "--modkit":
        url, argv = MODKIT_MCP, argv[1:]
    if argv[0] == "--tools":
        flt = argv[1] if len(argv) > 1 else ""
        for t in rpc("tools/list", {}, url)["result"]["tools"]:
            if flt in t["name"]:
                schema = t.get("inputSchema", {})
                required = set(schema.get("required", []))
                params = ", ".join(k + ("" if k in required else "?") for k in schema.get("properties", {}))
                print(f"{t['name']}({params})")
                print(f"    {t.get('description', '')[:500]}")
        return 0
    if argv[0] == "--list":
        r = call("cli.list", _url=url, **({"category": argv[1]} if len(argv) > 1 else {}))
    else:
        args = dict(a.split("=", 1) for a in argv[1:])
        r = call(argv[0], _url=url, **{k: _value(v) for k, v in args.items()})
    print(json.dumps(r, indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
