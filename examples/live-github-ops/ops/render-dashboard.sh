#!/usr/bin/env bash
set -euo pipefail

uv run repoagents dashboard --refresh-seconds 30 --format all
