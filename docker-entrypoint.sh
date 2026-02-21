#!/bin/sh
set -e

# Ensure uploads directory exists and is writable by appuser.
# Fixes bind-mounted volumes that may have root-owned subdirectories.
mkdir -p /app/uploads/meals
chown -R appuser:appuser /app/uploads

# Drop privileges and exec the CMD (uvicorn, dramatiq, etc.)
exec setpriv --reuid=appuser --regid=appuser --init-groups "$@"
