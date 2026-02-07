# Auto-Intall-Pterodactyl

Quick & dirty script to automate Pterodactyl panel/node setup. Made for homelab/testing — not for production without hardening.

![demo](https://i.imgur.com/Bc0rot4.png)

## ⚠️ Warning

- phpMyAdmin is locked down to localhost only (use SSH tunnel)
- No SSL auto-setup — run `certbot` manually after install
- **Do not use this for booter/DDoS services** — illegal and gets your VPS banned

## Features

- Panel install (Ubuntu 22.04/24.04)
- Secure phpMyAdmin (localhost + HTTP auth only)
- Auto import game server eggs from official repo
- Wings daemon setup with auto node registration
- All-in-one mode (panel + node on same machine for testing)

## Requirements

- Fresh Ubuntu 22.04 or 24.04 server
- Root access (`sudo su`)
- Domain pointed to server IP (for panel)
- At least 2GB RAM (4GB recommended)
