from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel

from reporepublic.utils.files import ensure_dir, write_json_file, write_text_file


class ArtifactStore:
    def __init__(self, artifacts_root: Path) -> None:
        self.artifacts_root = ensure_dir(artifacts_root)

    def role_dir(self, issue_id: int, run_id: str) -> Path:
        return ensure_dir(self.artifacts_root / f"issue-{issue_id}" / run_id)

    def write_role_artifacts(
        self,
        issue_id: int,
        run_id: str,
        role_name: str,
        payload: BaseModel,
        markdown: str,
    ) -> dict[str, str]:
        role_dir = self.role_dir(issue_id, run_id)
        json_path = role_dir / f"{role_name}.json"
        markdown_path = role_dir / f"{role_name}.md"
        write_json_file(json_path, payload.model_dump(mode="json"))
        write_text_file(markdown_path, markdown)
        return {
            "json": str(json_path),
            "markdown": str(markdown_path),
        }

    def write_debug_artifacts(
        self,
        issue_id: int,
        run_id: str,
        role_name: str,
        prompt: str,
        raw_output: str,
    ) -> dict[str, str]:
        role_dir = self.role_dir(issue_id, run_id)
        prompt_path = role_dir / f"{role_name}.prompt.txt"
        raw_output_path = role_dir / f"{role_name}.raw-output.txt"
        write_text_file(prompt_path, prompt)
        write_text_file(raw_output_path, raw_output)
        return {
            "prompt": str(prompt_path),
            "raw_output": str(raw_output_path),
        }
