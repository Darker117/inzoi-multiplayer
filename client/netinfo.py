"""This PC's addresses, to tell friends where to find a server hosted here."""
import ipaddress
import json
import os
import shutil
import socket
import subprocess

TAILNET = ipaddress.ip_network("100.64.0.0/10")


def lan_address() -> str | None:
    """This PC's address on the home network (the interface that leads to the internet; nothing is sent)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("192.0.2.1", 9))
        ip = s.getsockname()[0]
        return None if ip.startswith("127.") or ipaddress.ip_address(ip) in TAILNET else ip
    except OSError:
        return None
    finally:
        s.close()


def tailscale_self() -> tuple[str | None, str | None]:
    """(MagicDNS name, Tailscale IPv4) of this PC, if it's on Tailscale."""
    exe = shutil.which("tailscale") or (r"C:\Program Files\Tailscale\tailscale.exe" if os.name == "nt" else "tailscale")
    try:
        out = subprocess.run([exe, "status", "--json", "--peers=false"], capture_output=True, text=True, timeout=5,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        me = json.loads(out.stdout).get("Self") or {}
    except (OSError, ValueError, subprocess.SubprocessError):
        return None, None
    ips = [ip for ip in me.get("TailscaleIPs") or [] if "." in ip]
    return (me.get("DNSName") or "").rstrip(".") or None, ips[0] if ips else None


def addresses(port: int) -> list[dict]:
    """Where friends can reach a server on this PC: [{address, how}]. The Tailscale IP, not its name: names change."""
    at = "" if port == 24242 else f":{port}"
    out = []
    _, ts_ip = tailscale_self()
    if ts_ip:
        out.append({"address": ts_ip + at, "how": "friends anywhere, over Tailscale (share this PC with them first)"})
    lan = lan_address()
    if lan:
        out.append({"address": lan + at, "how": "friends in your home (same Wi-Fi or network)"})
    return out
