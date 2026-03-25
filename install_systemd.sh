#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MINUTES="${1:-15}"

python3 "$SCRIPT_DIR/artwall.py" install-systemd --minutes "$MINUTES"
