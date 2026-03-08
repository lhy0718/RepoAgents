#!/usr/bin/env bash
set -euo pipefail

uv run republic doctor
uv run republic run
