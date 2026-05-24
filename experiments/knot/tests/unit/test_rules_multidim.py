import textwrap

import pytest

from app.limiter.base import Rule
from app.rules import load_rules


@pytest.fixture
def rules(tmp_path):
    yaml_text = textwrap.dedent("""
        domain: knot
        descriptors:
          - key: endpoint
            value: shorten
            descriptors:
              - key: user_tier
                value: premium
                rate_limit:
                  algorithm: sliding_window_log
                  unit: minute
                  requests_per_unit: 50
              - key: user_tier
                value: enterprise
                rate_limit:
                  algorithm: sliding_window_log
                  unit: minute
                  requests_per_unit: 500
            rate_limit:
              algorithm: sliding_window_log
              unit: minute
              requests_per_unit: 10
          - key: endpoint
            value: redirect
            rate_limit:
              algorithm: token_bucket
              unit: second
              requests_per_unit: 50
              burst: 100
    """)
    yaml_file = tmp_path / "rules.yaml"
    yaml_file.write_text(yaml_text)
    return load_rules(yaml_file)


def test_endpoint_only_match(rules):
    """user_tier 미선언 시 endpoint default rule 매치."""
    rule = rules.lookup([("endpoint", "shorten")])
    assert rule is not None
    assert rule.requests_per_unit == 10  # default


def test_endpoint_plus_tier_match(rules):
    """endpoint+tier 둘 다 매치되면 tier rule (더 구체적) 선택."""
    rule = rules.lookup([("endpoint", "shorten"), ("user_tier", "premium")])
    assert rule.requests_per_unit == 50

    rule_ent = rules.lookup([("endpoint", "shorten"), ("user_tier", "enterprise")])
    assert rule_ent.requests_per_unit == 500


def test_specificity_priority(rules):
    """depth 큰 매치가 항상 우선 — 입력 순서 무관."""
    # 순서 바꿔도 결과 동일
    rule1 = rules.lookup([("user_tier", "premium"), ("endpoint", "shorten")])
    rule2 = rules.lookup([("endpoint", "shorten"), ("user_tier", "premium")])
    assert rule1 == rule2
    assert rule1.requests_per_unit == 50


def test_unknown_tier_fallback(rules):
    """미정의 tier (예: 'unknown') 보내면 endpoint default."""
    rule = rules.lookup([("endpoint", "shorten"), ("user_tier", "unknown")])
    assert rule.requests_per_unit == 10  # endpoint default


def test_unknown_endpoint_returns_none(rules):
    """정의되지 않은 endpoint → None."""
    rule = rules.lookup([("endpoint", "nonexistent"), ("user_tier", "premium")])
    assert rule is None
