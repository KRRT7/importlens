from __future__ import annotations

import sys

from textual.app import ComposeResult
from textual.containers import Container
from textual.reactive import reactive
from textual.screen import Screen
from textual.timer import Timer
from textual.widgets import Footer, Input, Static

from importlens.parser import Import
from importlens.widgets.import_tree import (
    ImportTree,
    _filter_tree,
    build_column_header,
)

_STDLIB_NAMES = sys.stdlib_module_names

SORT_CYCLE = ["default", "self", "cumul", "name"]
SORT_LABELS = {
    "default": "Parse Order",
    "self": "Self Time",
    "cumul": "Cumulative Time",
    "name": "Name",
}


def _filter_stdlib(imports: list[Import], show: bool) -> list[Import]:
    """Filter out top-level stdlib imports when show is False."""
    if show:
        return imports
    return [imp for imp in imports if imp.name.split(".")[0] not in _STDLIB_NAMES]


def _count_modules(imports: list[Import]) -> int:
    count = 0
    stack = list(imports)
    while stack:
        node = stack.pop()
        count += 1
        stack.extend(node.children)
    return count


def _total_self_us(imports: list[Import]) -> int:
    total = 0
    stack = list(imports)
    while stack:
        node = stack.pop()
        total += node.self_us
        stack.extend(node.children)
    return total


def _flatten_all(imp: Import) -> list[tuple[str, int, int]]:
    """Flatten an import and all its descendants."""
    result: list[tuple[str, int, int]] = [(imp.name, imp.self_us, imp.cumul_us)]
    for child in imp.children:
        result.extend(_flatten_all(child))
    return result


class AnalysisScreen(Screen):
    """Main analysis screen with tree view, filter, and sort."""

    DEFAULT_CSS = """
    #header-bar {
        text-align: center;
        width: 100%;
        padding: 1 0;
    }
    #filter-bar {
        width: 80;
    }
    #tree-wrap {
        height: 1fr;
        align: center top;
    }
    #column-header {
        width: 85%;
        height: 1;
    }
    ImportTree {
        width: 85%;
    }
    """

    BINDINGS = [
        ("slash", "toggle_filter", "Filter"),
        ("s", "cycle_sort", "Sort"),
        ("t", "toggle_stdlib", "Stdlib"),
        ("j", "cursor_down", "Down"),
        ("k", "cursor_up", "Up"),
        ("e", "export", "Export"),
        ("q", "quit", "Quit"),
    ]

    sort_key: reactive[str] = reactive("self", init=False)
    filter_text: reactive[str] = reactive("", init=False)
    show_stdlib: reactive[bool] = reactive(False, init=False)

    def __init__(self, imports: list[Import]) -> None:
        super().__init__()
        self._imports = imports
        self._debounce_timer: Timer | None = None

    def _visible_imports(self) -> list[Import]:
        return _filter_stdlib(self._imports, self.show_stdlib)

    def _rebuild_tree(self) -> None:
        try:
            tree = self.query_one(ImportTree)
        except Exception:
            return
        tree.populate(self._visible_imports(), self.sort_key, self.filter_text)
        self.query_one("#column-header", Static).update(
            build_column_header(tree._max_name)
        )

    def _update_header(self) -> None:
        visible = self._visible_imports()
        count = _count_modules(visible)
        total = _total_self_us(visible)
        label = SORT_LABELS.get(self.sort_key, self.sort_key)
        stdlib_tag = "" if self.show_stdlib else " | Stdlib: hidden"
        self.query_one("#header-bar", Static).update(
            f" {count:,} modules | Total: {total:,}µs | Sort: {label}{stdlib_tag}"
        )

    def compose(self) -> ComposeResult:
        yield Static(id="header-bar")
        yield Input(placeholder="Filter modules…", id="filter-bar")
        with Container(id="tree-wrap"):
            yield Static(id="column-header")
            yield ImportTree()
        yield Footer()

    def _initial_populate(self) -> None:
        self._update_header()
        tree = self.query_one(ImportTree)
        tree.populate(self._visible_imports(), self.sort_key, self.filter_text)
        self.query_one("#column-header", Static).update(
            build_column_header(tree._max_name)
        )

    def on_mount(self) -> None:
        self.query_one("#filter-bar", Input).display = False
        tree = self.query_one(ImportTree)
        tree.focus()
        self.call_after_refresh(self._initial_populate)

    def watch_sort_key(self) -> None:
        self._update_header()
        self._rebuild_tree()

    def watch_filter_text(self) -> None:
        self._rebuild_tree()

    def watch_show_stdlib(self) -> None:
        self._update_header()
        self._rebuild_tree()

    def _schedule_filter(self, value: str) -> None:
        """Debounced filter update."""
        if self._debounce_timer is not None:
            self._debounce_timer.stop()
        self._debounce_timer = self.set_timer(
            0.15, lambda: setattr(self, "filter_text", value)
        )

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "filter-bar":
            self._schedule_filter(event.value)

    def action_toggle_filter(self) -> None:
        bar = self.query_one("#filter-bar", Input)
        if bar.display:
            bar.display = False
            bar.value = ""
            self.filter_text = ""
            self.query_one(ImportTree).focus()
        else:
            bar.display = True
            bar.focus()

    def action_cycle_sort(self) -> None:
        idx = SORT_CYCLE.index(self.sort_key)
        self.sort_key = SORT_CYCLE[(idx + 1) % len(SORT_CYCLE)]

    def action_export(self) -> None:
        visible = self._visible_imports()
        filtered = _filter_tree(visible, self.filter_text)
        rows = []
        for imp in filtered:
            rows.extend(_flatten_all(imp))
        sort_key = self.sort_key
        if sort_key == "self":
            rows.sort(key=lambda r: r[1], reverse=True)
        elif sort_key == "cumul":
            rows.sort(key=lambda r: r[2], reverse=True)
        elif sort_key == "name":
            rows.sort(key=lambda r: r[0])
        count = len(rows)
        total = sum(r[1] for r in rows)
        lines = [
            f"# Import Time Analysis",
            f"",
            f"{count:,} modules | Total self time: {total:,}µs",
            f"",
            f"| Module | Self (µs) | Cumul (µs) |",
            f"|--------|----------:|----------:|",
        ]
        for name, self_us, cumul_us in rows:
            lines.append(f"| {name} | {self_us:,} | {cumul_us:,} |")
        md = "\n".join(lines) + "\n"
        self.app.copy_to_clipboard(md)
        self.notify("Copied to clipboard")

    def action_toggle_stdlib(self) -> None:
        self.show_stdlib = not self.show_stdlib

    def action_cursor_down(self) -> None:
        self.query_one(ImportTree).action_cursor_down()

    def action_cursor_up(self) -> None:
        self.query_one(ImportTree).action_cursor_up()

    def key_escape(self) -> None:
        bar = self.query_one("#filter-bar", Input)
        if bar.display:
            bar.display = False
            bar.value = ""
            self.filter_text = ""
            self.query_one(ImportTree).focus()
