from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Container
from textual.reactive import reactive
from textual.screen import Screen
from textual.timer import Timer
from textual.widgets import Footer, Input, Static

from importlens.parser import Import
from importlens.widgets.import_tree import ImportTree

SORT_CYCLE = ["default", "self", "cumul", "name"]
SORT_LABELS = {
    "default": "Parse Order",
    "self": "Self Time",
    "cumul": "Cumulative Time",
    "name": "Name",
}


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
    ImportTree {
        width: 85%;
    }
    """

    BINDINGS = [
        ("slash", "toggle_filter", "Filter"),
        ("s", "cycle_sort", "Sort"),
        ("j", "cursor_down", "Down"),
        ("k", "cursor_up", "Up"),
        ("q", "quit", "Quit"),
    ]

    sort_key: reactive[str] = reactive("default")
    filter_text: reactive[str] = reactive("")

    def __init__(self, imports: list[Import]) -> None:
        super().__init__()
        self._imports = imports
        self._debounce_timer: Timer | None = None

    def compose(self) -> ComposeResult:
        count = _count_modules(self._imports)
        total = _total_self_us(self._imports)
        yield Static(
            f" {count:,} modules | Total: {total:,}µs | Sort: Parse Order",
            id="header-bar",
        )
        yield Input(placeholder="Filter modules…", id="filter-bar")
        with Container(id="tree-wrap"):
            yield ImportTree()
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#filter-bar", Input).display = False
        tree = self.query_one(ImportTree)
        tree.focus()
        self.call_after_refresh(
            tree.populate, self._imports, self.sort_key, self.filter_text
        )

    def _update_header(self) -> None:
        count = _count_modules(self._imports)
        total = _total_self_us(self._imports)
        label = SORT_LABELS.get(self.sort_key, self.sort_key)
        self.query_one("#header-bar", Static).update(
            f" {count:,} modules | Total: {total:,}µs | Sort: {label}"
        )

    def watch_sort_key(self, value: str) -> None:
        self._update_header()
        try:
            tree = self.query_one(ImportTree)
        except Exception:
            return
        tree.populate(self._imports, value, self.filter_text)

    def watch_filter_text(self, value: str) -> None:
        try:
            tree = self.query_one(ImportTree)
        except Exception:
            return
        tree.populate(self._imports, self.sort_key, value)

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
