from __future__ import annotations

import math
import sys
from copy import copy

from rich.style import Style
from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Container
from textual.reactive import reactive
from textual.screen import Screen
from textual.timer import Timer
from textual.widgets import DataTable, Footer, Input, Static

from importlens.parser import Import

_STDLIB_NAMES = sys.stdlib_module_names

MAX_BAR_WIDTH = 10

SORT_CYCLE = ["default", "self", "cumul", "name"]
SORT_LABELS = {
    "default": "Parse Order",
    "self": "Self Time",
    "cumul": "Cumulative Time",
    "name": "Name",
}


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
    """Main analysis screen with aggregated table view, filter, and sort."""

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
    #agg-table {
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
            yield DataTable(id="agg-table", cursor_type="row")
        yield Footer()

    def _initial_populate(self) -> None:
        self._update_header()
        self._rebuild_table()

    def on_mount(self) -> None:
        self.query_one("#filter-bar", Input).display = False
        self.query_one("#agg-table", DataTable).focus()
        self.call_after_refresh(self._initial_populate)

    def watch_sort_key(self) -> None:
        self._update_header()
        self._rebuild_table()

    def watch_filter_text(self) -> None:
        self._rebuild_table()

    def watch_show_stdlib(self) -> None:
        self._update_header()
        self._rebuild_table()

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

    def _rebuild_table(self) -> None:
        try:
            table = self.query_one("#agg-table", DataTable)
        except Exception:
            return
        visible = self._visible_imports()
        filtered = _filter_tree(visible, self.filter_text)
        raw: list[tuple[str, int, int]] = []
        for imp in filtered:
            raw.extend(_flatten_all(imp))
        agg: dict[str, list[int]] = {}
        for name, self_us, cumul_us in raw:
            if name in agg:
                agg[name][0] += self_us
                agg[name][1] += cumul_us
                agg[name][2] += 1
            else:
                agg[name] = [self_us, cumul_us, 1]
        rows = [(name, vals[0], vals[1], vals[2]) for name, vals in agg.items()]
        if self.sort_key == "cumul":
            rows.sort(key=lambda r: r[2], reverse=True)
        elif self.sort_key == "name":
            rows.sort(key=lambda r: r[0])
        else:
            rows.sort(key=lambda r: r[1], reverse=True)
        max_self = max((r[1] for r in rows), default=1) or 1

        table.clear(columns=True)
        table.add_columns("Module", "Self (µs)", "Cumul (µs)", "Imports", "Bar")
        for name, self_us, cumul_us, count in rows:
            ratio = self_us / max_self
            color = _heat_color(ratio)
            if self_us > 0:
                log_ratio = math.log1p(self_us) / math.log1p(max_self)
            else:
                log_ratio = 0.0
            bar = "█" * round(log_ratio * MAX_BAR_WIDTH)
            style = Style(color=color)
            table.add_row(
                Text(name, style=style + Style(bold=True)),
                Text(f"{self_us:>12,}", style=style),
                Text(f"{cumul_us:>12,}", style=Style(dim=True)),
                Text(f"{count:>8}", style=Style(dim=True)),
                Text(bar, style=style),
            )

    def action_toggle_filter(self) -> None:
        bar = self.query_one("#filter-bar", Input)
        if bar.display:
            bar.display = False
            bar.value = ""
            self.filter_text = ""
            self.query_one("#agg-table", DataTable).focus()
        else:
            bar.display = True
            bar.focus()

    def action_cycle_sort(self) -> None:
        idx = SORT_CYCLE.index(self.sort_key)
        self.sort_key = SORT_CYCLE[(idx + 1) % len(SORT_CYCLE)]

    def action_export(self) -> None:
        visible = self._visible_imports()
        filtered = _filter_tree(visible, self.filter_text)
        raw: list[tuple[str, int, int]] = []
        for imp in filtered:
            raw.extend(_flatten_all(imp))
        # Deduplicate: sum self-time and count occurrences per module
        agg: dict[str, list[int]] = {}
        for name, self_us, _ in raw:
            if name in agg:
                agg[name][0] += self_us
                agg[name][1] += 1
            else:
                agg[name] = [self_us, 1]
        rows = [(name, vals[0], vals[1]) for name, vals in agg.items()]
        rows.sort(key=lambda r: r[1], reverse=True)
        total = sum(r[1] for r in rows)
        lines = [
            "# Import Time Analysis",
            "",
            f"{len(rows):,} unique modules | Total self time: {total:,}µs",
            "",
            "| Module | Self (µs) | Imports |",
            "|--------|----------:|--------:|",
        ]
        for name, self_us, count in rows:
            lines.append(f"| {name} | {self_us:,} | {count} |")
        md = "\n".join(lines) + "\n"
        self.app.copy_to_clipboard(md)
        self.notify("Copied to clipboard")

    def action_toggle_stdlib(self) -> None:
        self.show_stdlib = not self.show_stdlib

    def action_cursor_down(self) -> None:
        self.query_one("#agg-table", DataTable).action_cursor_down()

    def action_cursor_up(self) -> None:
        self.query_one("#agg-table", DataTable).action_cursor_up()

    def key_escape(self) -> None:
        bar = self.query_one("#filter-bar", Input)
        if bar.display:
            bar.display = False
            bar.value = ""
            self.filter_text = ""
            self.query_one("#agg-table", DataTable).focus()
