#!/usr/bin/env bash
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd "$DIR"

echo "Stopping and tearing down Chaos Engineering containers..."
docker compose down -v
echo "Cleanup complete."
