#!/usr/bin/env bash
# Human cleanup between runs. Deletes this scenario's containers AND volumes. Never let an agent run this.
set -euo pipefail
source "$(cd "$(dirname "$0")" && pwd)/../_shared/lib.sh"
reset_scenario s1
echo "Scenario s1 reset."
