"""Run the in-game Multiplayer page's brain (client/ingame.py) against an inZOI Multiplayer program that's already
running (its local API on 127.0.0.1:24243) and the running game (its control server, for opening the page and
showing messages). For trying changes to the page without rebuilding the program.

    python tools/ingame_dev.py
"""
import asyncio
import json
import logging
import os
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "client"))
sys.path.insert(0, str(ROOT / "tools"))
import ingame  # noqa: E402
import gamecli  # noqa: E402

PANEL = f"http://127.0.0.1:{os.environ.get('INZOI_MP_PANEL_PORT', '24243')}"
SIGNALS = Path(os.environ.get("INZOI_MP_INGAME_DIR") or Path(os.environ["APPDATA"]) / "inzoi-mp" / "ingame")


def post(path, body):
    req = urllib.request.Request(PANEL + path, json.dumps(body).encode(), {"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=20).read())


async def api(path, body):
    return await asyncio.to_thread(post, path, body)


def lobby_window():
    res = gamecli.call("ui.list_windows")
    text = res.get("_text", "")
    data = json.loads(text[text.index("{"):]) if "{" in text else res
    for w in data.get("windows") or []:
        if w.get("ui_type") == "MainMenu":
            return w["window"]
    return None


async def open_mods():
    win = await asyncio.to_thread(lobby_window)
    if not win:
        logging.warning("no main menu on screen")
        return
    r = await asyncio.to_thread(gamecli.call, "ui.click", ref=f"{win}/BW_WBP_Button_Mod/BW_Button", force=True)
    logging.info("opened the Mods page: %s", r.get("clicked"))


async def toast(text):
    await asyncio.to_thread(gamecli.call, "toast.show", message=text, immediate=True)


async def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    page = ingame.InGame(SIGNALS, api, open_mods, toast)
    version = (await api("/servers/state", {})).get("version", "?")
    logging.info("in-game page brain running against the program %s", version)
    await page.run(version)


if __name__ == "__main__":
    asyncio.run(main())
