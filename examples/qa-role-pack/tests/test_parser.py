from parser import parse_items


def test_parse_items() -> None:
    assert parse_items("a,b") == ["a", "b"]
