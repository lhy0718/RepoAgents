def parse_items(raw: str) -> list[str]:
    return [part.strip() for part in raw.split(",")]
