from __future__ import annotations

import math
from copy import copy
from typing import NamedTuple

from rich.style import Style
from rich.text import Text
from textual.widgets import Tree
from textual.widgets._tree import TOGGLE_STYLE, TreeNode

from importlens.parser import Import

GUIDE_WIDTH = 4
MAX_BAR_WIDTH = 10


class _NodeData(NamedTuple):
    """Pre-computed display values for a single tree node."""

    name: str
    self_us: int
    cumul_us: int
    color: str
    name_w: int
    bar: str
    depth: int
    import_children: list[Import]


def _heat_color(ratio: float) -> str:
    """Interpolate green -> yellow -> red hex color based on ratio 0..1."""
    ratio = max(0.0, min(1.0, ratio))
    if ratio < 0.5:
        t = ratio * 2
        r = int(0x00 + t * (0xFF - 0x00))
        g = 0xFF
    else:
        t = (ratio - 0.5) * 2
        r = 0xFF
        g = int(0xFF - t * (0xFF - 0x00))
    return f"#{r:02x}{g:02x}00"


def _compute_maxes(imports: list[Import]) -> tuple[int, int, int]:
    """Walk tree to find max self_us, max cumul_us, and max name length."""
    max_self = 0
    max_cumul = 0
    max_name = 0
    stack = list(imports)
    while stack:
        node = stack.pop()
        max_self = max(max_self, node.self_us)
        max_cumul = max(max_cumul, node.cumul_us)
        max_name = max(max_name, len(node.name))
        stack.extend(node.children)
    return max_self, max_cumul, max_name


def _sort_tree(imports: list[Import], sort_key: str) -> list[Import]:
    """Sort one level of imports by key. Returns new list, does not recurse."""
    if sort_key == "self":
        return sorted(imports, key=lambda i: i.self_us, reverse=True)
    if sort_key == "cumul":
        return sorted(imports, key=lambda i: i.cumul_us, reverse=True)
    if sort_key == "name":
        return sorted(imports, key=lambda i: i.name)
    return list(imports)


def _filter_tree(imports: list[Import], filter_text: str) -> list[Import]:
    """Recursive filter: keep nodes matching name or having matching descendants."""
    if not filter_text:
        return imports
    result: list[Import] = []
    lower = filter_text.lower()
    for imp in imports:
        filtered_children = _filter_tree(imp.children, filter_text)
        if lower in imp.name.lower() or filtered_children:
            node = copy(imp)
            node.children = filtered_children
            result.append(node)
    return result


def _make_node_data(
    imp: Import, depth: int, max_self: int, max_name: int
) -> _NodeData:
    ratio = imp.self_us / max_self
    color = _heat_color(ratio)
    if imp.self_us > 0 and max_self > 0:
        log_ratio = math.log1p(imp.self_us) / math.log1p(max_self)
    else:
        log_ratio = 0.0
    bar = "█" * round(log_ratio * MAX_BAR_WIDTH)
    name_w = max(len(imp.name) + 1, max_name + 2 - depth * GUIDE_WIDTH)
    return _NodeData(
        name=imp.name,
        self_us=imp.self_us,
        cumul_us=imp.cumul_us,
        color=color,
        name_w=name_w,
        bar=bar,
        depth=depth,
        import_children=imp.children,
    )


class ImportTree(Tree[_NodeData]):
    """Tree widget displaying import timing data with color-coded bars."""

    def __init__(self) -> None:
        super().__init__("imports", data=None)
        self.show_root = False
        self._max_self: int = 1
        self._max_name: int = 1
        self._sort_key: str = "default"

    def populate(
        self,
        imports: list[Import],
        sort_key: str = "default",
        filter_text: str = "",
    ) -> None:
        """Clear and rebuild tree from import data."""
        filtered = _filter_tree(imports, filter_text)
        self._max_self, _, self._max_name = (
            _compute_maxes(filtered) if filtered else (1, 1, 1)
        )
        self._max_self = max(self._max_self, 1)
        self._max_name = max(self._max_name, 1)
        self._sort_key = sort_key

        self.clear()
        self._add_level(self.root, filtered, sort_key, depth=0, expand=True)

    def _add_level(
        self,
        parent: TreeNode[_NodeData],
        imports: list[Import],
        sort_key: str,
        depth: int,
        expand: bool,
    ) -> None:
        sorted_imports = _sort_tree(imports, sort_key)
        for imp in sorted_imports:
            data = _make_node_data(imp, depth, self._max_self, self._max_name)
            if imp.children:
                node = parent.add(imp.name, data=data, expand=expand)
                if expand:
                    # Pre-load one level deeper for expanded nodes
                    self._add_level(
                        node, imp.children, sort_key, depth + 1, expand=False
                    )
            else:
                parent.add_leaf(imp.name, data=data)

    def _on_tree_node_expanded(self, event: Tree.NodeExpanded[_NodeData]) -> None:
        """Lazily populate children when a node is expanded for the first time."""
        node = event.node
        data = node.data
        if data is None or not data.import_children:
            return
        # Already populated — children exist as TreeNodes
        if node.children:
            return
        self._add_level(
            node,
            data.import_children,
            self._sort_key,
            data.depth + 1,
            expand=False,
        )

    def render_label(
        self, node: TreeNode[_NodeData], base_style: Style, style: Style
    ) -> Text:
        data = node.data
        if data is None:
            label = node._label.copy()
            label.stylize(style)
            return Text.assemble(label)

        if node._allow_expand:
            icon = "▼ " if node.is_expanded else "▶ "
            prefix = (icon, base_style + TOGGLE_STYLE)
        else:
            prefix = ("  ", base_style)

        color_style = Style(color=data.color)
        return Text.assemble(
            prefix,
            Text(f"{data.name:<{data.name_w}s}", style=color_style + Style(bold=True)),
            Text(f"{data.self_us:>12,}", style=color_style),
            Text("  │ ", style=Style(dim=True)),
            Text(f"{data.cumul_us:>12,}", style=Style(dim=True)),
            Text(f"  {data.bar}", style=color_style),
        )
