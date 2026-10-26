#!/usr/bin/env bash
set -euo pipefail
# Existing lakehouses are retained; API failures/LROs and pagination are handled.
exec python3 "$(dirname "$0")/fabric_lakehouses.py" provision
