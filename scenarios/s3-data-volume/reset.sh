#!/usr/bin/env bash
# Human cleanup between runs. Deletes this scenario's containers AND volumes. Never let an agent run this.
set -euo pipefail
source "$(cd "$(dirname "$0")" && pwd)/../_shared/lib.sh"
reset_scenario s3
echo "Scenario s3 reset."
