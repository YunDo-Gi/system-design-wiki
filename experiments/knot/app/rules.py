from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from app.limiter.base import Rule


@dataclass
class Rules:
    domain: str
    _index: dict[tuple[str, str], Rule] = field(default_factory=dict)

    def lookup(self, key: str, value: str) -> Rule | None:
        return self._index.get((key, value))


def load_rules(path: Path) -> Rules:
    data = yaml.safe_load(Path(path).read_text())
    rules = Rules(domain=data["domain"])
    for d in data.get("descriptors") or []:
        rl = d["rate_limit"]
        rule = Rule(
            algorithm=rl["algorithm"],
            unit=rl["unit"],
            requests_per_unit=rl["requests_per_unit"],
            burst=rl.get("burst"),
            mode=rl.get("mode", "hard"),
        )
        rules._index[(d["key"], d["value"])] = rule
    return rules
