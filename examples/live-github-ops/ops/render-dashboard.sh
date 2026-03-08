#!/usr/bin/env bash
set -euo pipefail

uv run republic dashboard --refresh-seconds 30 --format all
