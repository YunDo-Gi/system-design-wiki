import textwrap

from app.limiter.base import Rule
from app.rules import load_rules


def test_load_rules_parses_descriptors(tmp_path):
    yaml_text = textwrap.dedent("""
        domain: knot
        descriptors:
          - key: endpoint
            value: shorten
            rate_limit:
              algorithm: token_bucket
              unit: minute
              requests_per_unit: 10
              burst: 10
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

    rules = load_rules(yaml_file)

    assert rules.domain == "knot"

    shorten = rules.lookup([("endpoint", "shorten")])
    assert shorten == Rule(algorithm="token_bucket", unit="minute", requests_per_unit=10, burst=10)

    redirect = rules.lookup([("endpoint", "redirect")])
    assert redirect == Rule(
        algorithm="token_bucket",
        unit="second",
        requests_per_unit=50,
        burst=100,
    )


def test_lookup_missing_returns_none(tmp_path):
    yaml_file = tmp_path / "rules.yaml"
    yaml_file.write_text("domain: knot\ndescriptors: []\n")
    rules = load_rules(yaml_file)
    assert rules.lookup([("endpoint", "nonexistent")]) is None
