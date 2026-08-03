#!/bin/sh
set -eu

if [ -z "${VIBE_APP_KEY:-}" ]; then
  echo "BLOCKED: set VIBE_APP_KEY locally; never commit it"
  exit 2
fi
case "$VIBE_APP_KEY" in
  vibe_app_*) ;;
  *) echo "BLOCKED: VIBE_APP_KEY must be an application key (vibe_app_...)"; exit 2 ;;
esac

echo "READY: application key is present in the current shell"
echo "SAFE MODE: DRY_RUN; deployment and placement binding were not executed"
