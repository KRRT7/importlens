from __future__ import annotations

import re
from dataclasses import dataclass, field

# NOTE: CPython computes self_us as cum - accumulated inline
# (Python/import.c:4138, function import_find_and_load).  `accumulated` is
# per-interpreter, not per-thread, so concurrent imports can inflate it beyond
# `cum`, producing negative values.  We accept them with -?\d+.
IMPORT_TIME_RE = re.compile(
    r"^import time:\s+(-?\d+) \|\s+(-?\d+) \|(\s+\S.*)", re.MULTILINE
)


@dataclass(slots=True)
class Import:
    name: str
    self_us: int
    cumul_us: int
    children: list[Import] = field(default_factory=list)


def parse(text: str) -> list[Import]:
    root = Import(name="root", self_us=0, cumul_us=0)
    stack: list[Import] = [root]

    for self_us_s, cumul_us_s, raw_name in reversed(IMPORT_TIME_RE.findall(text)):
        leading = len(raw_name) - len(raw_name.lstrip())
        depth = (leading - 1) // 2 + 1

        node = Import(
            name=raw_name[leading:], self_us=int(self_us_s), cumul_us=int(cumul_us_s)
        )

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
