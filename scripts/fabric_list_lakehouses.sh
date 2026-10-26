#!/usr/bin/env bash
set -euo pipefail
# Supply FABRIC_TOKEN through the environment, never command-line arguments.
exec python3 "$(dirname "$0")/fabric_lakehouses.py"
