from __future__ import annotations

import json


def extract_json_object(text: str) -> dict:
    candidate = text.strip()
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        start = candidate.find("{")
        end = candidate.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise ValueError("Could not find a JSON object in backend output.") from None
        return json.loads(candidate[start : end + 1])
