from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from repoagents.templates import PRESETS, scaffold_repository


EXPECTED_SCAFFOLD_SNAPSHOTS = {
    "docs-only": {
        ".ai-repoagents/policies/merge-policy.md": "71236ff6be95eeb0b95280649d2de22d6f398909c666fb10fcd243c04e516cb5",
        ".ai-repoagents/policies/scope-policy.md": "7dbefe5fdfedf4464cf5e3a78184ddd4cb13dc77089902380e3ac38bb48d4d95",
        ".ai-repoagents/prompts/engineer.txt.j2": "18c5ee7f429daad16189f5fb77e4e08e4c074248e200116435bfd942ddb73bb3",
        ".ai-repoagents/prompts/planner.txt.j2": "9c23628a660f0d8fa4c66e9661a8fcb56acc5174e519a9805750abf933f504ec",
        ".ai-repoagents/prompts/qa.txt.j2": "92cb8cdb8b65a9fd9b7bc7557baedac3ab79117b0b79ff7274a14ce12ff33495",
        ".ai-repoagents/prompts/reviewer.txt.j2": "6463f47f82f6d8e56c3fed81e8b41180b939fe31c5bc9c9a3f87ce45c23cc323",
        ".ai-repoagents/prompts/triage.txt.j2": "a064f88eab6c22e720c7398012c0723dbf8dfd6b29b212c0f8acc20d249675b4",
        ".ai-repoagents/repoagents.yaml": "dd29e26c223572d5d0daf17adaef423ab9b002780b40d587228c679c11c67504",
        ".ai-repoagents/roles/engineer.md": "670a0314a5378ad87708ced32cc356bb4d51a503cbc541240aa132037aeab587",
        ".ai-repoagents/roles/planner.md": "6bed9894e0bb9c78f9575becb299668f6f088382812f141f9d68028757e7e5cc",
        ".ai-repoagents/roles/qa.md": "7ba8e99e7860de95028caa3b8e4f860084a50f6cfa7f337aa7e2e23c8cdec0fe",
        ".ai-repoagents/roles/reviewer.md": "a19313463db015a6d208646ca823c11fa3e6d3f073399eb9dd7ab2d70abfab78",
        ".ai-repoagents/roles/triage.md": "ab34cba0afeaad192e099beb151e14047d1fc40543b516f9df20a77bd21c8c07",
        ".ai-repoagents/state/runs.json": "434e2a01bec5e2ac6e481d9a2280fc79168009021c6624730f0257e7fed41828",
        ".github/workflows/repoagents-check.yml": "b2afb0700a791f0c5640603ce1bcc7b5afc6b50597ef08a6c0dee63aab01908a",
        "AGENTS.md": "b899c5206a7ca078b6df66fd158f21fdfae7f30b3aaeb625a1d6b9747c6368ee",
        "WORKFLOW.md": "a27314615f0d9348625e274ad80bc8b8e354a6b567ce671d58282fff76988a1a"
    },
    "python-library": {
        ".ai-repoagents/policies/merge-policy.md": "71236ff6be95eeb0b95280649d2de22d6f398909c666fb10fcd243c04e516cb5",
        ".ai-repoagents/policies/scope-policy.md": "2b890ee403bd18279c4f1f71367bd77b509957c2f522abcb3f97097793683634",
        ".ai-repoagents/prompts/engineer.txt.j2": "18c5ee7f429daad16189f5fb77e4e08e4c074248e200116435bfd942ddb73bb3",
        ".ai-repoagents/prompts/planner.txt.j2": "9c23628a660f0d8fa4c66e9661a8fcb56acc5174e519a9805750abf933f504ec",
        ".ai-repoagents/prompts/qa.txt.j2": "92cb8cdb8b65a9fd9b7bc7557baedac3ab79117b0b79ff7274a14ce12ff33495",
        ".ai-repoagents/prompts/reviewer.txt.j2": "6463f47f82f6d8e56c3fed81e8b41180b939fe31c5bc9c9a3f87ce45c23cc323",
        ".ai-repoagents/prompts/triage.txt.j2": "a064f88eab6c22e720c7398012c0723dbf8dfd6b29b212c0f8acc20d249675b4",
        ".ai-repoagents/repoagents.yaml": "dd29e26c223572d5d0daf17adaef423ab9b002780b40d587228c679c11c67504",
        ".ai-repoagents/roles/engineer.md": "670a0314a5378ad87708ced32cc356bb4d51a503cbc541240aa132037aeab587",
        ".ai-repoagents/roles/planner.md": "6bed9894e0bb9c78f9575becb299668f6f088382812f141f9d68028757e7e5cc",
        ".ai-repoagents/roles/qa.md": "7ba8e99e7860de95028caa3b8e4f860084a50f6cfa7f337aa7e2e23c8cdec0fe",
        ".ai-repoagents/roles/reviewer.md": "a19313463db015a6d208646ca823c11fa3e6d3f073399eb9dd7ab2d70abfab78",
        ".ai-repoagents/roles/triage.md": "ab34cba0afeaad192e099beb151e14047d1fc40543b516f9df20a77bd21c8c07",
        ".ai-repoagents/state/runs.json": "434e2a01bec5e2ac6e481d9a2280fc79168009021c6624730f0257e7fed41828",
        ".github/workflows/repoagents-check.yml": "b2afb0700a791f0c5640603ce1bcc7b5afc6b50597ef08a6c0dee63aab01908a",
        "AGENTS.md": "4b326b5a7cb82a4637e81243ca8929cad96084f3e630f2cfeff8c4e5448e7f5e",
        "WORKFLOW.md": "509fd71cd1b5e2acf14751d4f910ff6eb628b1f53a2e44ef8aaf2cbb608016bf"
    },
    "research-project": {
        ".ai-repoagents/policies/merge-policy.md": "71236ff6be95eeb0b95280649d2de22d6f398909c666fb10fcd243c04e516cb5",
        ".ai-repoagents/policies/scope-policy.md": "84a4f60e781f5aba036366654aa079e1d2f9df3fee3a73334e86e629b1aae47b",
        ".ai-repoagents/prompts/engineer.txt.j2": "18c5ee7f429daad16189f5fb77e4e08e4c074248e200116435bfd942ddb73bb3",
        ".ai-repoagents/prompts/planner.txt.j2": "9c23628a660f0d8fa4c66e9661a8fcb56acc5174e519a9805750abf933f504ec",
        ".ai-repoagents/prompts/qa.txt.j2": "92cb8cdb8b65a9fd9b7bc7557baedac3ab79117b0b79ff7274a14ce12ff33495",
        ".ai-repoagents/prompts/reviewer.txt.j2": "6463f47f82f6d8e56c3fed81e8b41180b939fe31c5bc9c9a3f87ce45c23cc323",
        ".ai-repoagents/prompts/triage.txt.j2": "a064f88eab6c22e720c7398012c0723dbf8dfd6b29b212c0f8acc20d249675b4",
        ".ai-repoagents/repoagents.yaml": "dd29e26c223572d5d0daf17adaef423ab9b002780b40d587228c679c11c67504",
        ".ai-repoagents/roles/engineer.md": "670a0314a5378ad87708ced32cc356bb4d51a503cbc541240aa132037aeab587",
        ".ai-repoagents/roles/planner.md": "6bed9894e0bb9c78f9575becb299668f6f088382812f141f9d68028757e7e5cc",
        ".ai-repoagents/roles/qa.md": "7ba8e99e7860de95028caa3b8e4f860084a50f6cfa7f337aa7e2e23c8cdec0fe",
        ".ai-repoagents/roles/reviewer.md": "a19313463db015a6d208646ca823c11fa3e6d3f073399eb9dd7ab2d70abfab78",
        ".ai-repoagents/roles/triage.md": "ab34cba0afeaad192e099beb151e14047d1fc40543b516f9df20a77bd21c8c07",
        ".ai-repoagents/state/runs.json": "434e2a01bec5e2ac6e481d9a2280fc79168009021c6624730f0257e7fed41828",
        ".github/workflows/repoagents-check.yml": "b2afb0700a791f0c5640603ce1bcc7b5afc6b50597ef08a6c0dee63aab01908a",
        "AGENTS.md": "b199ae45b8c45843156146fe5cbb791f17f9377387bc237dcc8108abe5947322",
        "WORKFLOW.md": "c6898e2d07f982047af7d72db2a3fa8cc04ce518217f636d0d57a0ee853f5d62"
    },
    "web-app": {
        ".ai-repoagents/policies/merge-policy.md": "71236ff6be95eeb0b95280649d2de22d6f398909c666fb10fcd243c04e516cb5",
        ".ai-repoagents/policies/scope-policy.md": "9f0f9ee7cdcce904a93c212f768a0f872fce84dc9cf88393ff57c4a78eabe611",
        ".ai-repoagents/prompts/engineer.txt.j2": "18c5ee7f429daad16189f5fb77e4e08e4c074248e200116435bfd942ddb73bb3",
        ".ai-repoagents/prompts/planner.txt.j2": "9c23628a660f0d8fa4c66e9661a8fcb56acc5174e519a9805750abf933f504ec",
        ".ai-repoagents/prompts/qa.txt.j2": "92cb8cdb8b65a9fd9b7bc7557baedac3ab79117b0b79ff7274a14ce12ff33495",
        ".ai-repoagents/prompts/reviewer.txt.j2": "6463f47f82f6d8e56c3fed81e8b41180b939fe31c5bc9c9a3f87ce45c23cc323",
        ".ai-repoagents/prompts/triage.txt.j2": "a064f88eab6c22e720c7398012c0723dbf8dfd6b29b212c0f8acc20d249675b4",
        ".ai-repoagents/repoagents.yaml": "dd29e26c223572d5d0daf17adaef423ab9b002780b40d587228c679c11c67504",
        ".ai-repoagents/roles/engineer.md": "670a0314a5378ad87708ced32cc356bb4d51a503cbc541240aa132037aeab587",
        ".ai-repoagents/roles/planner.md": "6bed9894e0bb9c78f9575becb299668f6f088382812f141f9d68028757e7e5cc",
        ".ai-repoagents/roles/qa.md": "7ba8e99e7860de95028caa3b8e4f860084a50f6cfa7f337aa7e2e23c8cdec0fe",
        ".ai-repoagents/roles/reviewer.md": "a19313463db015a6d208646ca823c11fa3e6d3f073399eb9dd7ab2d70abfab78",
        ".ai-repoagents/roles/triage.md": "ab34cba0afeaad192e099beb151e14047d1fc40543b516f9df20a77bd21c8c07",
        ".ai-repoagents/state/runs.json": "434e2a01bec5e2ac6e481d9a2280fc79168009021c6624730f0257e7fed41828",
        ".github/workflows/repoagents-check.yml": "b2afb0700a791f0c5640603ce1bcc7b5afc6b50597ef08a6c0dee63aab01908a",
        "AGENTS.md": "54fcd0233f556527261c81ae3a22269142474302de092ab1aa1c7f7701afde85",
        "WORKFLOW.md": "487abd9d8cc91149da412dd5a60be5ecf6b4dfe98cfc95d087e8de14300dcf05"
    }
}


@pytest.mark.parametrize("preset_name", sorted(PRESETS))
def test_scaffold_snapshot_manifest_matches_expected(tmp_path: Path, preset_name: str) -> None:
    scaffold_repository(
        repo_root=tmp_path,
        preset_name=preset_name,
        tracker_repo="demo/repo",
        fixture_issues="issues.json",
        force=True,
    )

    manifest = _collect_hash_manifest(tmp_path)

    assert manifest == EXPECTED_SCAFFOLD_SNAPSHOTS[preset_name]


def _collect_hash_manifest(root: Path) -> dict[str, str]:
    files = [
        root / ".ai-repoagents" / "roles" / "triage.md",
        root / ".ai-repoagents" / "roles" / "planner.md",
        root / ".ai-repoagents" / "roles" / "engineer.md",
        root / ".ai-repoagents" / "roles" / "qa.md",
        root / ".ai-repoagents" / "roles" / "reviewer.md",
        root / ".ai-repoagents" / "prompts" / "triage.txt.j2",
        root / ".ai-repoagents" / "prompts" / "planner.txt.j2",
        root / ".ai-repoagents" / "prompts" / "engineer.txt.j2",
        root / ".ai-repoagents" / "prompts" / "qa.txt.j2",
        root / ".ai-repoagents" / "prompts" / "reviewer.txt.j2",
        root / ".ai-repoagents" / "policies" / "merge-policy.md",
        root / ".ai-repoagents" / "policies" / "scope-policy.md",
        root / ".ai-repoagents" / "repoagents.yaml",
        root / ".ai-repoagents" / "state" / "runs.json",
        root / ".github" / "workflows" / "repoagents-check.yml",
        root / "AGENTS.md",
        root / "WORKFLOW.md",
    ]
    manifest: dict[str, str] = {}
    for path in files:
        rel_path = path.relative_to(root).as_posix()
        manifest[rel_path] = hashlib.sha256(path.read_bytes()).hexdigest()
    return manifest
