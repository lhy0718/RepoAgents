from parser import parse_items


def test_parse_items_splits_csv() -> None:
    assert parse_items("a,b,c") == ["a", "b", "c"]
