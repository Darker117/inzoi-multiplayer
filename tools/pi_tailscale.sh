#!/usr/bin/env bash
# Puts the Pi on your Tailscale network, so friends can reach the inZOI Multiplayer server from anywhere.
# Run on the Pi:  bash pi_tailscale.sh
# It asks for your sudo password, then prints a login link: open it and approve the Pi with your Tailscale account.
set -e

if ! command -v tailscale >/dev/null; then
    echo "Installing Tailscale (official installer from tailscale.com)..."
    curl -fsSL https://tailscale.com/install.sh | sh
fi
sudo systemctl enable --now tailscaled

echo
echo "Logging the Pi in. If a link appears below, open it in your browser and approve the Pi."
sudo tailscale up --hostname=nox

echo
echo "Done. The Pi on Tailscale:"
tailscale ip -4
tailscale status --self --peers=false
echo "The inZOI Multiplayer server is reachable at that address, port 24242."
