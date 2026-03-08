from __future__ import annotations

import json
from pathlib import Path
import re

import yaml

from reporepublic.models import IssueRef


FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?", re.DOTALL)


def load_issue_file(path: Path) -> list[IssueRef]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        payload = payload.get("issues", [])
    if not isinstance(payload, list):
        raise ValueError(f"Issue file at {path} must contain a JSON array or an object with an 'issues' array.")

    issues: list[IssueRef] = []
    for item in payload:
        if not isinstance(item, dict):
            raise ValueError(f"Each issue entry in {path} must be a JSON object.")
        normalized = dict(item)
        if "id" not in normalized and "number" in normalized:
            normalized["id"] = normalized["number"]
        if "number" not in normalized and "id" in normalized:
            normalized["number"] = normalized["id"]
        normalized.setdefault("body", "")
        normalized.setdefault("labels", [])
        normalized.setdefault("comments", [])
        state = str(normalized.pop("state", "open")).lower()
        if state not in {"open", "opened"}:
            continue
        issues.append(IssueRef.model_validate(normalized))
    return issues


def load_markdown_issue_directory(path: Path) -> list[IssueRef]:
    if not path.exists():
        raise FileNotFoundError(f"Markdown issue directory does not exist: {path}")
    if not path.is_dir():
        raise ValueError(f"Markdown issue tracker path must be a directory: {path}")

    issues: list[IssueRef] = []
    for file_path in sorted(path.glob("*.md")):
        issue = _parse_markdown_issue(file_path)
        if issue is not None:
            issues.append(issue)
    return issues


def _parse_markdown_issue(path: Path) -> IssueRef | None:
    text = path.read_text(encoding="utf-8")
    metadata: dict[str, object] = {}
    body = text
    match = FRONTMATTER_RE.match(text)
    if match:
        raw_metadata = yaml.safe_load(match.group(1)) or {}
        if not isinstance(raw_metadata, dict):
            raise ValueError(f"Markdown issue frontmatter at {path} must be a mapping.")
        metadata = dict(raw_metadata)
        body = text[match.end():]

    title, body = _extract_title_and_body(body, metadata.get("title"), path)
    issue_number = _coerce_int(metadata.get("number")) or _coerce_int(metadata.get("id")) or _infer_issue_number(path)
    if issue_number is None:
        raise ValueError(f"Markdown issue {path} must define id/number or use a filename starting with digits.")
    issue_id = _coerce_int(metadata.get("id")) or issue_number
    state = str(metadata.get("state", "open")).lower()
    if state not in {"open", "opened"}:
        return None

    labels = metadata.get("labels", [])
    if isinstance(labels, str):
        labels = [labels]
    if not isinstance(labels, list):
        raise ValueError(f"Markdown issue labels at {path} must be a list or string.")

    comments = metadata.get("comments", [])
    if not isinstance(comments, list):
        raise ValueError(f"Markdown issue comments at {path} must be a list.")

    normalized = {
        "id": issue_id,
        "number": _coerce_int(metadata.get("number")) or issue_number,
        "title": title,
        "body": body.strip(),
        "labels": labels,
        "comments": comments,
    }
    if metadata.get("url"):
        normalized["url"] = metadata["url"]
    if metadata.get("updated_at"):
        normalized["updated_at"] = metadata["updated_at"]
    return IssueRef.model_validate(normalized)


def _extract_title_and_body(
    body: str,
    configured_title: object,
    path: Path,
) -> tuple[str, str]:
    if isinstance(configured_title, str) and configured_title.strip():
        return configured_title.strip(), body

    lines = body.splitlines()
    for index, line in enumerate(lines):
        if line.startswith("# "):
            title = line[2:].strip()
            remaining = "\n".join(lines[index + 1 :]).lstrip()
            return title, remaining

    inferred = re.sub(r"^\d+[-_. ]*", "", path.stem).replace("-", " ").replace("_", " ").strip()
    if inferred:
        return inferred.title(), body
    raise ValueError(f"Markdown issue {path} must define a title in frontmatter or as the first H1 heading.")


def _infer_issue_number(path: Path) -> int | None:
    match = re.match(r"^(\d+)", path.stem)
    if not match:
        return None
    return int(match.group(1))


def _coerce_int(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None
