from __future__ import annotations

import json
from importlib import resources
from pathlib import Path
from typing import Any

from jinja2 import ChoiceLoader, Environment, FileSystemLoader
from pydantic import BaseModel

from repoagents.config import LoadedConfig


class PromptRenderer:
    def __init__(self, loaded: LoadedConfig) -> None:
        self.loaded = loaded
        self.prompt_dir = loaded.ai_root / "prompts"
        self.roles_dir = loaded.ai_root / "roles"
        self.policies_dir = loaded.ai_root / "policies"
        loaders = [FileSystemLoader(str(self.prompt_dir))]
        package_prompt_dir = resources.files("repoagents").joinpath("templates/default/prompts")
        loaders.append(FileSystemLoader(str(package_prompt_dir)))
        self.environment = Environment(
            loader=ChoiceLoader(loaders),
            autoescape=False,
            keep_trailing_newline=True,
            trim_blocks=False,
        )

    def render(
        self,
        role_name: str,
        output_model: type[BaseModel],
        context: dict[str, Any],
    ) -> str:
        template = self.environment.get_template(f"{role_name}.txt.j2")
        policy_documents = self.load_policy_documents()
        rendered_context = {
            **context,
            "role_guidance": self.load_role_guidance(role_name),
            "policy_documents": policy_documents,
            "policy_bundle": "\n\n".join(
                f"## {name}\n{body}" for name, body in policy_documents.items()
            ),
            "output_schema_json": json.dumps(output_model.model_json_schema(), indent=2),
        }
        return template.render(**rendered_context)

    def load_role_guidance(self, role_name: str) -> str:
        local_path = self.roles_dir / f"{role_name}.md"
        if local_path.exists():
            return local_path.read_text(encoding="utf-8")
        package_path = resources.files("repoagents").joinpath(
            f"templates/default/roles/{role_name}.md"
        )
        return package_path.read_text(encoding="utf-8")

    def load_policy_documents(self) -> dict[str, str]:
        documents: dict[str, str] = {}
        for name in ("merge-policy.md", "scope-policy.md"):
            local_path = self.policies_dir / name
            if local_path.exists():
                documents[name] = local_path.read_text(encoding="utf-8")
                continue
            package_path = resources.files("repoagents").joinpath(
                f"templates/default/policies/{name}"
            )
            documents[name] = package_path.read_text(encoding="utf-8")
        return documents
