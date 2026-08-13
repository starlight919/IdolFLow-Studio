#!/usr/bin/env bash
set -euo pipefail

PORT="${1:-8913}"
ssh -o StrictHostKeyChecking=no -o ServerAliveInterval=30 -p 443 -R0:127.0.0.1:"$PORT" a.pinggy.io
