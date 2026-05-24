from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from app.limiter.base import Rule

logger = logging.getLogger(__name__)


@dataclass
class RuleNode:
    rate_limit: Rule | None = None
    children: dict[tuple[str, str], "RuleNode"] = field(default_factory=dict)


@dataclass
class Rules:
    domain: str
    root: RuleNode = field(default_factory=RuleNode)

    def lookup(self, entries: list[tuple[str, str]]) -> Rule | None:
        """가장 구체적인 (depth 큰) 매치 반환. 없으면 None."""
        entries_set = set(entries)
        rule, _depth = self._dfs(self.root, entries_set, depth=0)
        return rule

    def _dfs(self, node: RuleNode, entries_set, depth):
        # 현재 노드가 rule 있으면 후보. root는 보통 없음.
        best = (node.rate_limit, depth if node.rate_limit else -1)
        for kv, child in node.children.items():
            if kv in entries_set:
                cand = self._dfs(child, entries_set, depth + 1)
                if cand[1] > best[1]:
                    best = cand
        return best


def _build_node(data: dict | None) -> RuleNode:
    """yaml 노드 dict → RuleNode."""
    node = RuleNode()
    if not data:
        return node

    rl = data.get("rate_limit")
    if rl:
        node.rate_limit = Rule(
            algorithm=rl["algorithm"],
            unit=rl["unit"],
            requests_per_unit=rl["requests_per_unit"],
            burst=rl.get("burst"),
        )

    for child_data in data.get("descriptors") or []:
        key = child_data["key"]
        value = child_data["value"]
        node.children[(key, value)] = _build_node(child_data)

    return node


def load_rules(path: Path) -> Rules:
    data = yaml.safe_load(Path(path).read_text())
    return Rules(
        domain=data["domain"],
        root=_build_node({"descriptors": data.get("descriptors") or []}),
    )


class _RulesReloader(FileSystemEventHandler):
    def __init__(self, path: Path, on_reload):
        self._path = path.resolve()
        self._on_reload = on_reload

    def _is_target(self, src: str) -> bool:
        try:
            return Path(src).resolve() == self._path
        except Exception:
            return False

    def on_modified(self, event):
        if not event.is_directory and self._is_target(event.src_path):
            self._on_reload()

    def on_moved(self, event):
        # vim/emacs atomic save: tmp → rename
        if not event.is_directory and self._is_target(event.dest_path):
            self._on_reload()


def start_watcher(path: Path, on_reload) -> Observer:
    """rules.yaml 변경 시 on_reload() 호출하는 watcher 시작."""
    path = path.resolve()
    handler = _RulesReloader(path, on_reload)
    observer = Observer()
    observer.schedule(handler, str(path.parent), recursive=False)
    observer.start()
    logger.info("rules watcher started: %s", path)
    return observer
