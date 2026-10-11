"""Push a Lua script into the running game through the ModKit's live preview and print what it logged.

Usage:  python tools/lua_run.py path/to/script.lua [--as B2/Main.lua] [--wait 6]

The script is written into the ModKit project's Lua workspace (default slot B2/Main.lua), validated,
then the preview is reloaded so its on_begin runs. Everything it print()s from B2 lands in the
project's preview.log; the new lines are shown here.
"""
import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gamecli import MODKIT_MCP, call  # noqa: E402

PLUGIN = "MPGateTest_5F7FDFC6"
LOG = Path.home() / "Documents/inZOIModKit/inZOIModKit/Mods" / PLUGIN / "Intermediate/lua/preview.log"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("script")
    ap.add_argument("--as", dest="slot", default="B2/Main.lua")
    ap.add_argument("--wait", type=float, default=6)
    a = ap.parse_args()

    content = Path(a.script).read_text("utf-8")
    w = call("modkit_write_lua_script", _url=MODKIT_MCP, plugin=PLUGIN, path=a.slot, content=content)
    if not w.get("success"):
        sys.exit(f"write failed: {w}")
    v = call("modkit_validate_lua_script", _url=MODKIT_MCP, plugin=PLUGIN, path=a.slot)
    problems = [d for d in v.get("diagnostics", []) if d.get("severity") == "error"]
    for d in v.get("diagnostics", []):
        print(f"[{d['severity']}] line {d.get('line')}: {d.get('message')}")
    if problems:
        sys.exit("validation errors - not reloading")
    before = LOG.stat().st_mtime if LOG.exists() else 0
    r = call("modkit_reload_lua_preview", _url=MODKIT_MCP, plugin=PLUGIN)
    if not r.get("success"):
        r = call("modkit_start_lua_preview", _url=MODKIT_MCP, plugin=PLUGIN)
    print("preview:", json.dumps(r)[:200])
    time.sleep(a.wait)
    # The ModKit rewrites preview.log on every reload, so the whole file is this run's output.
    if not LOG.exists() or LOG.stat().st_mtime == before:
        print("(preview.log not rewritten yet - try a longer --wait)")
        return
    for line in LOG.read_text("utf-8", "replace").splitlines():
        if "[B2]" in line or "[B1]" in line or "error" in line.lower():
            print(line.replace("[log] ", ""))


if __name__ == "__main__":
    main()
