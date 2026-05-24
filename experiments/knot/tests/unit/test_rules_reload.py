import textwrap
import time
from pathlib import Path

import pytest

from app.rules import load_rules, start_watcher


def _write(path: Path, content: str) -> None:
    path.write_text(content)
    # macOS watchdog 안정성 위한 짧은 sleep
    time.sleep(0.05)


def _wait_for(predicate, timeout=2.0, interval=0.05):
    """predicate가 True 되거나 timeout."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return False


def test_reload_picks_up_new_rule(tmp_path):
    yaml_path = tmp_path / "rules.yaml"
    _write(yaml_path, textwrap.dedent("""
        domain: knot
        descriptors:
          - key: endpoint
            value: shorten
            rate_limit:
              algorithm: always_allow
              unit: minute
              requests_per_unit: 10
    """))

    state = {"rules": load_rules(yaml_path)}

    def reload():
        try:
            state["rules"] = load_rules(yaml_path)
        except Exception:
            pass

    observer = start_watcher(yaml_path, reload)
    try:
        # 새 rule로 덮어쓰기
        _write(yaml_path, textwrap.dedent("""
            domain: knot
            descriptors:
              - key: endpoint
                value: shorten
                rate_limit:
                  algorithm: always_allow
                  unit: minute
                  requests_per_unit: 99
        """))

        # rules.lookup이 새 값을 반환할 때까지 대기
        ok = _wait_for(
            lambda: state["rules"].lookup([("endpoint", "shorten")]).requests_per_unit == 99
        )
        assert ok, "watcher did not pick up new rules"
    finally:
        observer.stop()
        observer.join()


def test_reload_failure_keeps_previous(tmp_path):
    yaml_path = tmp_path / "rules.yaml"
    _write(yaml_path, textwrap.dedent("""
        domain: knot
        descriptors:
          - key: endpoint
            value: shorten
            rate_limit:
              algorithm: always_allow
              unit: minute
              requests_per_unit: 10
    """))

    state = {"rules": load_rules(yaml_path)}

    def reload():
        try:
            state["rules"] = load_rules(yaml_path)
        except Exception:
            pass  # 이전 rules 유지

    observer = start_watcher(yaml_path, reload)
    try:
        # 잘못된 yaml로 덮어쓰기
        _write(yaml_path, "not: valid: yaml: at: all: [")
        time.sleep(0.5)  # watcher trigger 시간

        # 이전 값 유지되어야 함
        rule = state["rules"].lookup([("endpoint", "shorten")])
        assert rule is not None
        assert rule.requests_per_unit == 10
    finally:
        observer.stop()
        observer.join()
