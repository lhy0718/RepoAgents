from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from reporepublic.templates import PRESETS, scaffold_repository


EXPECTED_SCAFFOLD_SNAPSHOTS = {
    "docs-only": {
        ".ai-republic/policies/merge-policy.md": "87691b1744222302fbfb7cc99e08df37c010ad9e6076118a1b3c795fbce01f58",
        ".ai-republic/policies/scope-policy.md": "7dbefe5fdfedf4464cf5e3a78184ddd4cb13dc77089902380e3ac38bb48d4d95",
        ".ai-republic/prompts/engineer.txt.j2": "f5cc1ec143a74d611ad1502770a5cb83f2ac292b3bbb7dc1b4057773c21f6f90",
        ".ai-republic/prompts/planner.txt.j2": "966336b7e8888c7ec78f7e700de2c5a1630bca2acb112eca66a3f45d148bfdc0",
        ".ai-republic/prompts/qa.txt.j2": "afe73892015c816e6a07b56d2d605086c278a9b9a903f9c640fb19bd2d4f3bab",
        ".ai-republic/prompts/reviewer.txt.j2": "06859358cade48f72b95662de40c034b7a9bb97fa601cf34c03cdcb47c247ee7",
        ".ai-republic/prompts/triage.txt.j2": "0ef0df796b5d4d8fe7a93203a0ac9d77315752ee9aeb60e83b307f0d1970b815",
        ".ai-republic/reporepublic.yaml": "9ead8a83a89840b035bd702f33de9fca451ee42c0b644139ba1ee8ee17a6c660",
        ".ai-republic/roles/engineer.md": "670a0314a5378ad87708ced32cc356bb4d51a503cbc541240aa132037aeab587",
        ".ai-republic/roles/planner.md": "6bed9894e0bb9c78f9575becb299668f6f088382812f141f9d68028757e7e5cc",
        ".ai-republic/roles/qa.md": "7ba8e99e7860de95028caa3b8e4f860084a50f6cfa7f337aa7e2e23c8cdec0fe",
        ".ai-republic/roles/reviewer.md": "a19313463db015a6d208646ca823c11fa3e6d3f073399eb9dd7ab2d70abfab78",
        ".ai-republic/roles/triage.md": "ab34cba0afeaad192e099beb151e14047d1fc40543b516f9df20a77bd21c8c07",
        ".ai-republic/state/runs.json": "434e2a01bec5e2ac6e481d9a2280fc79168009021c6624730f0257e7fed41828",
        ".github/workflows/republic-check.yml": "bf6e0402e16e44dc7760b787d197dd41a7efef3863c1f997d906256d3f7459b3",
        "AGENTS.md": "86ae7c7e4daa8dff4740be5139375c6b7a4076f2b80b94907abc947ade8a682a",
        "WORKFLOW.md": "f5a0f501c65f5f18a40c4ac5805291e2579cb89fd4c148de84948875da08554a",
    },
    "python-library": {
        ".ai-republic/policies/merge-policy.md": "87691b1744222302fbfb7cc99e08df37c010ad9e6076118a1b3c795fbce01f58",
        ".ai-republic/policies/scope-policy.md": "2b890ee403bd18279c4f1f71367bd77b509957c2f522abcb3f97097793683634",
        ".ai-republic/prompts/engineer.txt.j2": "f5cc1ec143a74d611ad1502770a5cb83f2ac292b3bbb7dc1b4057773c21f6f90",
        ".ai-republic/prompts/planner.txt.j2": "966336b7e8888c7ec78f7e700de2c5a1630bca2acb112eca66a3f45d148bfdc0",
        ".ai-republic/prompts/qa.txt.j2": "afe73892015c816e6a07b56d2d605086c278a9b9a903f9c640fb19bd2d4f3bab",
        ".ai-republic/prompts/reviewer.txt.j2": "06859358cade48f72b95662de40c034b7a9bb97fa601cf34c03cdcb47c247ee7",
        ".ai-republic/prompts/triage.txt.j2": "0ef0df796b5d4d8fe7a93203a0ac9d77315752ee9aeb60e83b307f0d1970b815",
        ".ai-republic/reporepublic.yaml": "9ead8a83a89840b035bd702f33de9fca451ee42c0b644139ba1ee8ee17a6c660",
        ".ai-republic/roles/engineer.md": "670a0314a5378ad87708ced32cc356bb4d51a503cbc541240aa132037aeab587",
        ".ai-republic/roles/planner.md": "6bed9894e0bb9c78f9575becb299668f6f088382812f141f9d68028757e7e5cc",
        ".ai-republic/roles/qa.md": "7ba8e99e7860de95028caa3b8e4f860084a50f6cfa7f337aa7e2e23c8cdec0fe",
        ".ai-republic/roles/reviewer.md": "a19313463db015a6d208646ca823c11fa3e6d3f073399eb9dd7ab2d70abfab78",
        ".ai-republic/roles/triage.md": "ab34cba0afeaad192e099beb151e14047d1fc40543b516f9df20a77bd21c8c07",
        ".ai-republic/state/runs.json": "434e2a01bec5e2ac6e481d9a2280fc79168009021c6624730f0257e7fed41828",
        ".github/workflows/republic-check.yml": "bf6e0402e16e44dc7760b787d197dd41a7efef3863c1f997d906256d3f7459b3",
        "AGENTS.md": "6d299b12c22c60ffcede9aa731589cfff25dc30a8b7b3f1114347872e980ffc2",
        "WORKFLOW.md": "7bd14b33ff95e7386a7050568270ba73dc04a411f593ab1dad617609bb8a2046",
    },
    "research-project": {
        ".ai-republic/policies/merge-policy.md": "87691b1744222302fbfb7cc99e08df37c010ad9e6076118a1b3c795fbce01f58",
        ".ai-republic/policies/scope-policy.md": "84a4f60e781f5aba036366654aa079e1d2f9df3fee3a73334e86e629b1aae47b",
        ".ai-republic/prompts/engineer.txt.j2": "f5cc1ec143a74d611ad1502770a5cb83f2ac292b3bbb7dc1b4057773c21f6f90",
        ".ai-republic/prompts/planner.txt.j2": "966336b7e8888c7ec78f7e700de2c5a1630bca2acb112eca66a3f45d148bfdc0",
        ".ai-republic/prompts/qa.txt.j2": "afe73892015c816e6a07b56d2d605086c278a9b9a903f9c640fb19bd2d4f3bab",
        ".ai-republic/prompts/reviewer.txt.j2": "06859358cade48f72b95662de40c034b7a9bb97fa601cf34c03cdcb47c247ee7",
        ".ai-republic/prompts/triage.txt.j2": "0ef0df796b5d4d8fe7a93203a0ac9d77315752ee9aeb60e83b307f0d1970b815",
        ".ai-republic/reporepublic.yaml": "9ead8a83a89840b035bd702f33de9fca451ee42c0b644139ba1ee8ee17a6c660",
        ".ai-republic/roles/engineer.md": "670a0314a5378ad87708ced32cc356bb4d51a503cbc541240aa132037aeab587",
        ".ai-republic/roles/planner.md": "6bed9894e0bb9c78f9575becb299668f6f088382812f141f9d68028757e7e5cc",
        ".ai-republic/roles/qa.md": "7ba8e99e7860de95028caa3b8e4f860084a50f6cfa7f337aa7e2e23c8cdec0fe",
        ".ai-republic/roles/reviewer.md": "a19313463db015a6d208646ca823c11fa3e6d3f073399eb9dd7ab2d70abfab78",
        ".ai-republic/roles/triage.md": "ab34cba0afeaad192e099beb151e14047d1fc40543b516f9df20a77bd21c8c07",
        ".ai-republic/state/runs.json": "434e2a01bec5e2ac6e481d9a2280fc79168009021c6624730f0257e7fed41828",
        ".github/workflows/republic-check.yml": "bf6e0402e16e44dc7760b787d197dd41a7efef3863c1f997d906256d3f7459b3",
        "AGENTS.md": "944de775363a8391b1cf22154d9957b8f2a7863ff2b32a6bdfb58dbccf97c283",
        "WORKFLOW.md": "4d598d2c308a9fdcd152cf832f132503205609af32341a3db4a98448c815e708",
    },
    "web-app": {
        ".ai-republic/policies/merge-policy.md": "87691b1744222302fbfb7cc99e08df37c010ad9e6076118a1b3c795fbce01f58",
        ".ai-republic/policies/scope-policy.md": "9f0f9ee7cdcce904a93c212f768a0f872fce84dc9cf88393ff57c4a78eabe611",
        ".ai-republic/prompts/engineer.txt.j2": "f5cc1ec143a74d611ad1502770a5cb83f2ac292b3bbb7dc1b4057773c21f6f90",
        ".ai-republic/prompts/planner.txt.j2": "966336b7e8888c7ec78f7e700de2c5a1630bca2acb112eca66a3f45d148bfdc0",
        ".ai-republic/prompts/qa.txt.j2": "afe73892015c816e6a07b56d2d605086c278a9b9a903f9c640fb19bd2d4f3bab",
        ".ai-republic/prompts/reviewer.txt.j2": "06859358cade48f72b95662de40c034b7a9bb97fa601cf34c03cdcb47c247ee7",
        ".ai-republic/prompts/triage.txt.j2": "0ef0df796b5d4d8fe7a93203a0ac9d77315752ee9aeb60e83b307f0d1970b815",
        ".ai-republic/reporepublic.yaml": "9ead8a83a89840b035bd702f33de9fca451ee42c0b644139ba1ee8ee17a6c660",
        ".ai-republic/roles/engineer.md": "670a0314a5378ad87708ced32cc356bb4d51a503cbc541240aa132037aeab587",
        ".ai-republic/roles/planner.md": "6bed9894e0bb9c78f9575becb299668f6f088382812f141f9d68028757e7e5cc",
        ".ai-republic/roles/qa.md": "7ba8e99e7860de95028caa3b8e4f860084a50f6cfa7f337aa7e2e23c8cdec0fe",
        ".ai-republic/roles/reviewer.md": "a19313463db015a6d208646ca823c11fa3e6d3f073399eb9dd7ab2d70abfab78",
        ".ai-republic/roles/triage.md": "ab34cba0afeaad192e099beb151e14047d1fc40543b516f9df20a77bd21c8c07",
        ".ai-republic/state/runs.json": "434e2a01bec5e2ac6e481d9a2280fc79168009021c6624730f0257e7fed41828",
        ".github/workflows/republic-check.yml": "bf6e0402e16e44dc7760b787d197dd41a7efef3863c1f997d906256d3f7459b3",
        "AGENTS.md": "d6f8caa648013cd7057c506523989633e0526425ccbfc6f5d2c54bba4bac9f00",
        "WORKFLOW.md": "99e3e3dd1ba8a750071b43b20bee83bfa5d8c800d1a29286418c025127384c2d",
    },
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
        root / ".ai-republic" / "roles" / "triage.md",
        root / ".ai-republic" / "roles" / "planner.md",
        root / ".ai-republic" / "roles" / "engineer.md",
        root / ".ai-republic" / "roles" / "qa.md",
        root / ".ai-republic" / "roles" / "reviewer.md",
        root / ".ai-republic" / "prompts" / "triage.txt.j2",
        root / ".ai-republic" / "prompts" / "planner.txt.j2",
        root / ".ai-republic" / "prompts" / "engineer.txt.j2",
        root / ".ai-republic" / "prompts" / "qa.txt.j2",
        root / ".ai-republic" / "prompts" / "reviewer.txt.j2",
        root / ".ai-republic" / "policies" / "merge-policy.md",
        root / ".ai-republic" / "policies" / "scope-policy.md",
        root / ".ai-republic" / "reporepublic.yaml",
        root / ".ai-republic" / "state" / "runs.json",
        root / ".github" / "workflows" / "republic-check.yml",
        root / "AGENTS.md",
        root / "WORKFLOW.md",
    ]
    manifest: dict[str, str] = {}
    for path in files:
        rel_path = path.relative_to(root).as_posix()
        manifest[rel_path] = hashlib.sha256(path.read_bytes()).hexdigest()
    return manifest
