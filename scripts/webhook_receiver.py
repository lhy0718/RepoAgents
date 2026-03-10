from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import subprocess
import sys
import threading
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

SIGNATURE_HEADER = "X-Hub-Signature-256"


class RepoAgentsWebhookServer(ThreadingHTTPServer):
    def __init__(
        self,
        server_address: tuple[str, int],
        handler_class: type[BaseHTTPRequestHandler],
        *,
        repo_root: Path,
        project_root: Path,
        webhook_secret: str | None,
        render_dashboard: bool,
        max_requests: int | None,
    ) -> None:
        super().__init__(server_address, handler_class)
        self.repo_root = repo_root
        self.project_root = project_root
        self.webhook_secret = webhook_secret
        self.render_dashboard = render_dashboard
        self.max_requests = max_requests
        self.handled_requests = 0


class WebhookHandler(BaseHTTPRequestHandler):
    server: RepoAgentsWebhookServer

    def do_POST(self) -> None:  # noqa: N802
        if self.path.rstrip("/") != "/github":
            self._send_json(
                HTTPStatus.NOT_FOUND,
                {"ok": False, "error": f"unsupported path '{self.path}'"},
            )
            return

        length = int(self.headers.get("Content-Length", "0"))
        event = self.headers.get("X-GitHub-Event", "").strip().lower()
        if not event:
            self._send_json(
                HTTPStatus.BAD_REQUEST,
                {"ok": False, "error": "missing X-GitHub-Event header"},
            )
            return

        body = self.rfile.read(length)
        if self.server.webhook_secret is not None and not signature_matches(
            self.server.webhook_secret,
            body,
            self.headers.get(SIGNATURE_HEADER),
        ):
            self._send_json(
                HTTPStatus.UNAUTHORIZED,
                {
                    "ok": False,
                    "error": f"invalid or missing {SIGNATURE_HEADER} header",
                },
            )
            return
        try:
            payload = json.loads(body.decode("utf-8"))
        except json.JSONDecodeError as exc:
            self._send_json(
                HTTPStatus.BAD_REQUEST,
                {"ok": False, "error": f"invalid JSON payload: {exc}"},
            )
            return
        if not isinstance(payload, dict):
            self._send_json(
                HTTPStatus.BAD_REQUEST,
                {"ok": False, "error": "webhook payload must be a JSON object"},
            )
            return

        payload_path = _store_payload(self.server.repo_root, event, payload)
        webhook_result = _run_cli(
            project_root=self.server.project_root,
            repo_root=self.server.repo_root,
            args=["repoagents", "webhook", "--event", event, "--payload", str(payload_path)],
        )
        dashboard_result = None
        if self.server.render_dashboard and webhook_result.returncode == 0:
            dashboard_result = _run_cli(
                project_root=self.server.project_root,
                repo_root=self.server.repo_root,
                args=["repoagents", "dashboard"],
            )

        self.server.handled_requests += 1
        response_body = {
            "ok": webhook_result.returncode == 0 and (dashboard_result is None or dashboard_result.returncode == 0),
            "event": event,
            "payload_path": str(payload_path),
            "signature_verified": self.server.webhook_secret is not None,
            "webhook_exit_code": webhook_result.returncode,
            "webhook_stdout": webhook_result.stdout.strip(),
            "webhook_stderr": webhook_result.stderr.strip(),
        }
        if dashboard_result is not None:
            response_body["dashboard_exit_code"] = dashboard_result.returncode
            response_body["dashboard_stdout"] = dashboard_result.stdout.strip()
            response_body["dashboard_stderr"] = dashboard_result.stderr.strip()

        status = HTTPStatus.OK if response_body["ok"] else HTTPStatus.INTERNAL_SERVER_ERROR
        self._send_json(status, response_body)

        if self.server.max_requests is not None and self.server.handled_requests >= self.server.max_requests:
            threading.Thread(target=self.server.shutdown, daemon=True).start()

    def log_message(self, format: str, *args: object) -> None:
        message = format % args
        sys.stderr.write(f"[webhook-receiver] {message}\n")

    def _send_json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def _store_payload(repo_root: Path, event: str, payload: dict[str, Any]) -> Path:
    inbox_dir = repo_root / ".ai-repoagents" / "inbox" / "webhooks"
    inbox_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    payload_path = inbox_dir / f"{timestamp}-{event}.json"
    payload_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return payload_path


def _run_cli(project_root: Path, repo_root: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["uv", "run", "--project", str(project_root), *args],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
    )


def compute_signature(secret: str, body: bytes) -> str:
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def signature_matches(secret: str, body: bytes, provided_signature: str | None) -> bool:
    if provided_signature is None:
        return False
    expected_signature = compute_signature(secret, body)
    return hmac.compare_digest(expected_signature, provided_signature.strip())


def resolve_webhook_secret(secret: str | None, secret_env: str | None) -> str | None:
    if secret:
        return secret
    if not secret_env:
        return None
    value = os.environ.get(secret_env, "").strip()
    if not value:
        raise SystemExit(f"Environment variable '{secret_env}' is not set or empty.")
    return value


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Example webhook receiver for RepoAgents with optional signature verification."
    )
    parser.add_argument("--repo-root", type=Path, required=True, help="Target repository root.")
    parser.add_argument(
        "--project-root",
        type=Path,
        required=True,
        help="RepoAgents project root used for `uv run --project`.",
    )
    parser.add_argument("--host", default="127.0.0.1", help="Bind host.")
    parser.add_argument("--port", type=int, default=8787, help="Bind port.")
    parser.add_argument(
        "--render-dashboard",
        action="store_true",
        help="Run `repoagents dashboard` after each successful webhook execution.",
    )
    parser.add_argument(
        "--secret",
        default=None,
        help=f"Optional shared secret used to validate the {SIGNATURE_HEADER} header.",
    )
    parser.add_argument(
        "--secret-env",
        default=None,
        help="Optional environment variable that contains the shared secret.",
    )
    parser.add_argument(
        "--max-requests",
        type=int,
        default=None,
        help="Optional number of requests to handle before shutting down.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    webhook_secret = resolve_webhook_secret(args.secret, args.secret_env)
    server = RepoAgentsWebhookServer(
        (args.host, args.port),
        WebhookHandler,
        repo_root=args.repo_root.resolve(),
        project_root=args.project_root.resolve(),
        webhook_secret=webhook_secret,
        render_dashboard=args.render_dashboard,
        max_requests=args.max_requests,
    )
    print(
        f"RepoAgents webhook receiver listening on http://{args.host}:{args.port}/github "
        f"(repo_root={server.repo_root}, signature={'on' if webhook_secret else 'off'})",
        flush=True,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
