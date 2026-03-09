from parser import parse_rollout_steps


def test_parse_rollout_steps() -> None:
    assert parse_rollout_steps("baseline -> pr-ready") == ["baseline", "pr-ready"]
