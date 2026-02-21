from __future__ import annotations

import re
from dataclasses import dataclass, field

IMPORT_TIME_RE = re.compile(r"^import time:\s+(\d+) \|\s+(\d+) \|(\s+\S.*)")


@dataclass
class Import:
    name: str
    self_us: int
    cumul_us: int
    children: list[Import] = field(default_factory=list)


def parse(text: str) -> list[Import]:
    root = Import(name="root", self_us=0, cumul_us=0)
    stack: list[Import] = [root]

    for line in reversed(text.splitlines()):
        m = IMPORT_TIME_RE.match(line)
        if not m:
            continue

        self_us = int(m[1])
        cumul_us = int(m[2])
        raw_name = m[3]
        name = raw_name.strip()
        depth = (len(raw_name) - len(raw_name.lstrip()) - 1) // 2 + 1

        node = Import(name=name, self_us=self_us, cumul_us=cumul_us)

        while len(stack) > depth:
            stack.pop()
        stack[-1].children.insert(0, node)
        stack.append(node)

    return root.children


def flatten(imports: list[Import], depth: int = 0) -> list[tuple[str, int, int, int]]:
    """Flatten the tree into (name, self_us, cumul_us, depth) tuples."""
    rows: list[tuple[str, int, int, int]] = []
    for imp in imports:
        rows.append((imp.name, imp.self_us, imp.cumul_us, depth))
        rows.extend(flatten(imp.children, depth + 1))
    return rows
