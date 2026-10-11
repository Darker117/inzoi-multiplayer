@echo off
rem Starts the inZOI Multiplayer server on this PC (needs Python 3.9+ from python.org).
rem Optional: set a password or port by editing the line below, e.g. --password secret --port 24242
rem Players on other networks need port 24242 (TCP) forwarded to this PC, or a VPN like Tailscale.
pushd "%~dp0"
title inZOI Multiplayer server
python inzoi_mp_server.py %*
if errorlevel 1 pause
