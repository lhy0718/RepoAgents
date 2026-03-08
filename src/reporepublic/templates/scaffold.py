from __future__ import annotations

from difflib import unified_diff
import re
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Literal

from jinja2 import Environment, FileSystemLoader

from reporepublic.models import CURRENT_RUN_STATE_VERSION
from reporepublic.utils.files import ensure_dir, write_text_file


BEGIN_MARKER = "<!-- reporepublic:begin -->"
END_MARKER = "<!-- reporepublic:end -->"


@dataclass(frozen=True, slots=True)
class PresetDefinition:
    name: str
    description: str
    scope_summary: str
    rules: list[str]


@dataclass(frozen=True, slots=True)
class UpgradePlanItem:
    path: Path
    label: str
    action: Literal["create", "refresh", "preserve", "update_managed_block", "create_state"]
    reason: str
    expected_body: str | None = None
    diff_preview: str | None = None


PRESETS: dict[str, PresetDefinition] = {
    "python-library": PresetDefinition(
        name="python-library",
        description="Python package or service repository.",
        scope_summary="Favor small Python changes, focused tests, and packaging hygiene.",
        rules=[
            "Prioritize fixes in `src/`, `tests/`, `pyproject.toml`, and documentation.",
            "Prefer pytest updates over ad hoc scripts when adding validation.",
            "Keep API surface changes explicit in summaries for maintainers.",
        ],
    ),
    "web-app": PresetDefinition(
        name="web-app",
        description="Frontend or full-stack application repository.",
        scope_summary="Favor safe UI or server changes with explicit asset and environment handling.",
        rules=[
            "Treat environment files and deployment configuration as sensitive.",
            "Call out visual regressions and browser test gaps in reviewer notes.",
            "Prefer focused component or route changes over sweeping refactors.",
        ],
    ),
    "docs-only": PresetDefinition(
        name="docs-only",
        description="Documentation-first repository.",
        scope_summary="Stay inside Markdown, docs tooling, and examples unless maintainers approve otherwise.",
        rules=[
            "Code changes are out of scope unless explicitly requested in the issue.",
            "Prefer improving quickstarts, examples, and reference docs.",
            "Highlight command accuracy and copy/paste fidelity in reviews.",
        ],
    ),
    "research-project": PresetDefinition(
        name="research-project",
        description="Research codebase with notebooks, experiments, or prototypes.",
        scope_summary="Favor reproducibility, experiment notes, and narrow code changes.",
        rules=[
            "Do not rewrite datasets or generated artifacts without human approval.",
            "Call out notebook execution assumptions and environment drift.",
            "Prefer additive experiment scaffolding over destructive cleanup.",
        ],
    ),
}


def scaffold_repository(
    repo_root: Path,
    preset_name: str,
    tracker_repo: str,
    fixture_issues: str | None = None,
    force: bool = False,
    tracker_kind: str = "github",
    tracker_path: str | None = None,
) -> list[Path]:
    if preset_name not in PRESETS:
        raise ValueError(f"Unknown preset '{preset_name}'.")

    ai_root = ensure_dir(repo_root / ".ai-republic")
    ensure_dir(ai_root / "roles")
    ensure_dir(ai_root / "prompts")
    ensure_dir(ai_root / "policies")
    ensure_dir(ai_root / "state")
    ensure_dir(repo_root / ".github" / "workflows")

    created: list[Path] = []
    managed_files = render_managed_file_map(
        preset_name=preset_name,
        tracker_repo=tracker_repo,
        fixture_issues=fixture_issues,
        tracker_kind=tracker_kind,
        tracker_path=tracker_path,
    )
    for rel_path, body in managed_files.items():
        created.extend(_write_if_allowed(repo_root / rel_path, body, force=force))

    runs_path = ai_root / "state" / "runs.json"
    if force or not runs_path.exists():
        runs_path.write_text(
            '{\n'
            f'  "version": {CURRENT_RUN_STATE_VERSION},\n'
            '  "runs": {}\n'
            '}\n',
            encoding="utf-8",
        )
        created.append(runs_path)

    agents_block = render_agents_block(
        preset_name=preset_name,
        tracker_repo=tracker_repo,
        fixture_issues=fixture_issues,
        tracker_kind=tracker_kind,
        tracker_path=tracker_path,
    )
    agents_path = repo_root / "AGENTS.md"
    if force and agents_path.exists():
        agents_path.unlink()
    if not agents_path.exists():
        write_text_file(agents_path, f"# AGENTS\n\n{BEGIN_MARKER}\n{agents_block}\n{END_MARKER}\n")
        created.append(agents_path)
    else:
        original = agents_path.read_text(encoding="utf-8")
        updated = _replace_managed_block(original, agents_block)
        if updated != original:
            agents_path.write_text(updated, encoding="utf-8")
            created.append(agents_path)

    return created


def build_upgrade_plan(
    repo_root: Path,
    preset_name: str,
    tracker_repo: str,
    fixture_issues: str | None = None,
    force: bool = False,
    tracker_kind: str = "github",
    tracker_path: str | None = None,
) -> list[UpgradePlanItem]:
    if preset_name not in PRESETS:
        raise ValueError(f"Unknown preset '{preset_name}'.")

    plans: list[UpgradePlanItem] = []
    managed_files = render_managed_file_map(
        preset_name=preset_name,
        tracker_repo=tracker_repo,
        fixture_issues=fixture_issues,
        tracker_kind=tracker_kind,
        tracker_path=tracker_path,
    )
    for rel_path, expected_body in managed_files.items():
        path = repo_root / rel_path
        if not path.exists():
            plans.append(
                UpgradePlanItem(
                    path=path,
                    label=rel_path.as_posix(),
                    action="create",
                    reason="Managed file is missing and will be created.",
                    expected_body=expected_body,
                )
            )
            continue
        current_body = path.read_text(encoding="utf-8")
        if current_body == expected_body:
            continue
        plans.append(
            UpgradePlanItem(
                path=path,
                label=rel_path.as_posix(),
                action="refresh" if force else "preserve",
                reason=(
                    "Managed file differs from the packaged scaffold and will be refreshed."
                    if force
                    else "Managed file differs from the packaged scaffold; local changes will be preserved."
                ),
                expected_body=expected_body,
                diff_preview=_build_diff_preview(current_body, expected_body, rel_path.as_posix()),
            )
        )

    runs_path = repo_root / ".ai-republic" / "state" / "runs.json"
    if not runs_path.exists():
        plans.append(
            UpgradePlanItem(
                path=runs_path,
                label=".ai-republic/state/runs.json",
                action="create_state",
                reason="Run state file is missing and will be created.",
                expected_body=_default_runs_body(),
            )
        )

    expected_agents_block = render_agents_block(
        preset_name=preset_name,
        tracker_repo=tracker_repo,
        fixture_issues=fixture_issues,
        tracker_kind=tracker_kind,
        tracker_path=tracker_path,
    )
    agents_path = repo_root / "AGENTS.md"
    if not agents_path.exists():
        plans.append(
            UpgradePlanItem(
                path=agents_path,
                label="AGENTS.md",
                action="create",
                reason="AGENTS.md is missing and will be created with a managed block.",
                expected_body=f"# AGENTS\n\n{BEGIN_MARKER}\n{expected_agents_block}\n{END_MARKER}\n",
            )
        )
    else:
        current_body = agents_path.read_text(encoding="utf-8")
        current_block = extract_managed_block(current_body) or ""
        if current_block.strip() != expected_agents_block.strip():
            updated = _replace_managed_block(current_body, expected_agents_block)
            plans.append(
                UpgradePlanItem(
                    path=agents_path,
                    label="AGENTS.md#managed-block",
                    action="update_managed_block",
                    reason="The managed AGENTS.md block differs and will be refreshed without touching user content outside the block.",
                    expected_body=updated,
                    diff_preview=_build_diff_preview(
                        current_block,
                        expected_agents_block,
                        "AGENTS.md#managed-block",
                    ),
                )
            )
    return plans


def apply_upgrade_plan(plan: list[UpgradePlanItem]) -> list[Path]:
    updated: list[Path] = []
    for item in plan:
        if item.action == "preserve":
            continue
        if item.expected_body is None:
            continue
        write_text_file(item.path, item.expected_body)
        updated.append(item.path)
    return updated


def render_managed_file_map(
    preset_name: str,
    tracker_repo: str,
    fixture_issues: str | None = None,
    tracker_kind: str = "github",
    tracker_path: str | None = None,
) -> dict[Path, str]:
    if preset_name not in PRESETS:
        raise ValueError(f"Unknown preset '{preset_name}'.")

    template_root = _template_root()
    environment = _template_environment(template_root)
    template_context = _template_context(
        preset_name,
        tracker_repo,
        fixture_issues,
        tracker_kind=tracker_kind,
        tracker_path=tracker_path,
    )
    managed: dict[Path, str] = {}
    managed.update(_render_static_tree(template_root.joinpath("roles"), Path(".ai-republic/roles")))
    managed.update(_render_static_tree(template_root.joinpath("prompts"), Path(".ai-republic/prompts")))
    managed[Path(".ai-republic/policies/merge-policy.md")] = environment.get_template(
        "policies/merge-policy.md"
    ).render(**template_context)
    managed[Path(".ai-republic/policies/scope-policy.md")] = environment.get_template(
        "policies/scope-policy.md.j2"
    ).render(**template_context)
    managed[Path(".ai-republic/reporepublic.yaml")] = environment.get_template(
        "config/reporepublic.yaml.j2"
    ).render(**template_context)
    managed[Path("WORKFLOW.md")] = environment.get_template("WORKFLOW.md.j2").render(
        **template_context
    )
    managed[Path(".github/workflows/republic-check.yml")] = environment.get_template(
        ".github/workflows/republic-check.yml"
    ).render(**template_context)
    return managed


def render_agents_block(
    preset_name: str,
    tracker_repo: str,
    fixture_issues: str | None = None,
    tracker_kind: str = "github",
    tracker_path: str | None = None,
) -> str:
    template_root = _template_root()
    environment = _template_environment(template_root)
    return environment.get_template("AGENTS.block.md.j2").render(
        **_template_context(
            preset_name,
            tracker_repo,
            fixture_issues,
            tracker_kind=tracker_kind,
            tracker_path=tracker_path,
        )
    )


def detect_scaffold_preset(repo_root: Path) -> str | None:
    scope_policy_path = repo_root / ".ai-republic" / "policies" / "scope-policy.md"
    if not scope_policy_path.exists():
        return None
    match = re.search(
        r"^Preset:\s+`([^`]+)`",
        scope_policy_path.read_text(encoding="utf-8"),
        flags=re.MULTILINE,
    )
    if not match:
        return None
    preset_name = match.group(1)
    return preset_name if preset_name in PRESETS else None


def extract_managed_block(original: str) -> str | None:
    if BEGIN_MARKER not in original or END_MARKER not in original:
        return None
    _, _, tail = original.partition(BEGIN_MARKER)
    block, _, _ = tail.partition(END_MARKER)
    return block.strip()


def _default_runs_body() -> str:
    return (
        '{\n'
        f'  "version": {CURRENT_RUN_STATE_VERSION},\n'
        '  "runs": {}\n'
        '}\n'
    )


def _template_root() -> Path:
    return resources.files("reporepublic").joinpath("templates/default")


def _template_environment(template_root: Path) -> Environment:
    return Environment(
        loader=FileSystemLoader(str(template_root)),
        autoescape=False,
        keep_trailing_newline=True,
    )


def _template_context(
    preset_name: str,
    tracker_repo: str,
    fixture_issues: str | None,
    *,
    tracker_kind: str,
    tracker_path: str | None,
) -> dict[str, object]:
    preset = PRESETS[preset_name]
    return {
        "preset": preset,
        "tracker_kind": tracker_kind,
        "tracker_repo": tracker_repo,
        "tracker_mode": "fixture" if fixture_issues else "rest",
        "fixtures_path": fixture_issues or "",
        "tracker_path": tracker_path or "",
    }


def _render_static_tree(source: Path, destination: Path) -> dict[Path, str]:
    rendered: dict[Path, str] = {}
    for item in source.iterdir():
        if item.is_dir():
            rendered.update(_render_static_tree(item, destination / item.name))
            continue
        rendered[destination / item.name] = item.read_text(encoding="utf-8")
    return rendered


def _copy_static_tree(source: Path, destination: Path, force: bool) -> list[Path]:
    created: list[Path] = []
    for item in source.iterdir():
        if item.is_dir():
            ensure_dir(destination / item.name)
            created.extend(_copy_static_tree(item, destination / item.name, force=force))
            continue
        target = destination / item.name
        body = item.read_text(encoding="utf-8")
        created.extend(_write_if_allowed(target, body, force=force))
    return created


def _write_if_allowed(path: Path, body: str, force: bool) -> list[Path]:
    if path.exists() and not force:
        return []
    write_text_file(path, body)
    return [path]


def _replace_managed_block(original: str, block: str) -> str:
    replacement = f"{BEGIN_MARKER}\n{block}\n{END_MARKER}"
    if BEGIN_MARKER in original and END_MARKER in original:
        before, _, tail = original.partition(BEGIN_MARKER)
        _, _, after = tail.partition(END_MARKER)
        return f"{before}{replacement}{after.lstrip()}"
    suffix = "\n" if original.endswith("\n") else "\n\n"
    return f"{original}{suffix}{replacement}\n"


def _build_diff_preview(current_body: str, expected_body: str, label: str) -> str:
    diff_lines = list(
        unified_diff(
            current_body.splitlines(),
            expected_body.splitlines(),
            fromfile=f"current/{label}",
            tofile=f"packaged/{label}",
            lineterm="",
        )
    )
    if len(diff_lines) > 20:
        diff_lines = diff_lines[:20] + ["..."]
    return "\n".join(diff_lines)
