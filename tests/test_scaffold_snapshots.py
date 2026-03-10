from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from repoagents.templates import PRESETS, scaffold_repository


EXPECTED_SCAFFOLD_SNAPSHOTS = {
    "none": {
        ".ai-repoagents/policies/merge-policy.md": "71236ff6be95eeb0b95280649d2de22d6f398909c666fb10fcd243c04e516cb5",
        ".ai-repoagents/policies/scope-policy.md": "31c0c49a90469c0802f90a73db123946410f5c74ff9033a2d6eaf4b1f8609a52",
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
        ".github/workflows/repoagents-check.yml": "0825ee10b92f1b603f56cfda7bd85c653095c787307aaa24f47fe1ec87041193",
        ".gitignore": "e5f2ce698888308437b8b9fa572d9308148b7fc446b4ff20208305485ff9a7fc",
        "AGENTS.md": "3084965d71e3d144149f6fe0fbdde59937bb5ffdd4ee6fbba047b66ce8df836a",
        "WORKFLOW.md": "926ce863a773d571373078caf069fa4891bde5fd74608e311dfe5323d4775b4c"
    },
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
        ".github/workflows/repoagents-check.yml": "0825ee10b92f1b603f56cfda7bd85c653095c787307aaa24f47fe1ec87041193",
        ".gitignore": "e5f2ce698888308437b8b9fa572d9308148b7fc446b4ff20208305485ff9a7fc",
        "AGENTS.md": "d56092dbc870b155d5557d789193113f405d4bb3345a2b1c5edd0f5b8f89a3a1",
        "WORKFLOW.md": "e7f9ba6bcbb8d0724aacae29bedddbd5c50ccdd91fdcffc98ebd014efcd19cfd"
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
        ".github/workflows/repoagents-check.yml": "0825ee10b92f1b603f56cfda7bd85c653095c787307aaa24f47fe1ec87041193",
        ".gitignore": "e5f2ce698888308437b8b9fa572d9308148b7fc446b4ff20208305485ff9a7fc",
        "AGENTS.md": "99c5cd914ca86d9db1e4e444e332283befe07b982039564e4e44fc778246959b",
        "WORKFLOW.md": "0b5f89aa8cbe6f4b7e060fcc8b347597bd213b1fe820f273fc7655370392be36"
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
        ".github/workflows/repoagents-check.yml": "0825ee10b92f1b603f56cfda7bd85c653095c787307aaa24f47fe1ec87041193",
        ".gitignore": "e5f2ce698888308437b8b9fa572d9308148b7fc446b4ff20208305485ff9a7fc",
        "AGENTS.md": "2efa72decd7a10b02582fd0eef2c5f22eb77788581b4ecb90e2ee912e16d081f",
        "WORKFLOW.md": "ef813c31b0958e25608091ac5e649b4b09e8f556b7501ec7ac89129d1f4b40d6"
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
        ".github/workflows/repoagents-check.yml": "0825ee10b92f1b603f56cfda7bd85c653095c787307aaa24f47fe1ec87041193",
        ".gitignore": "e5f2ce698888308437b8b9fa572d9308148b7fc446b4ff20208305485ff9a7fc",
        "AGENTS.md": "8a82498c5d7786e871363590660710d090169a3d784836f2c927f78b2a4069ef",
        "WORKFLOW.md": "3c7e11de7dcc5dba63521642b68ddfab2a1d6b5fb4b01aea203b43537e21db88"
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
        root / ".gitignore",
        root / "AGENTS.md",
        root / "WORKFLOW.md",
    ]
    manifest: dict[str, str] = {}
    for path in files:
        rel_path = path.relative_to(root).as_posix()
        manifest[rel_path] = hashlib.sha256(path.read_bytes()).hexdigest()
    return manifest
