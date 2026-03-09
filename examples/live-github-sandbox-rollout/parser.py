def parse_rollout_steps(raw: str) -> list[str]:
    return [part.strip() for part in raw.split("->")]
