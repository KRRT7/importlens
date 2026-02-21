from __future__ import annotations

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Button, Footer, Static, TextArea

from importlens.parser import Import, parse


class InputScreen(Screen[list[Import]]):
    """Screen for pasting importtime output when no file/stdin is provided."""

    BINDINGS = [("q", "quit", "Quit")]

    def compose(self) -> ComposeResult:
        yield Static(
            "Paste [bold]python -X importtime[/] output below, then click Parse.",
            id="instructions",
        )
        yield TextArea(id="paste-area")
        yield Button("Parse & Analyze", variant="primary", id="submit-btn")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#paste-area", TextArea).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id != "submit-btn":
            return
        text = self.query_one("#paste-area", TextArea).text
        if not text.strip():
            self.notify("Paste importtime output first.", severity="error")
            return
        imports = parse(text)
        if not imports:
            self.notify("No import time data found.", severity="error")
            return
        self.dismiss(imports)
