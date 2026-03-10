#!/usr/bin/env bash
set -euo pipefail

uv run repoagents doctor
uv run repoagents run
