from __future__ import annotations

from textual.app import App

from importlens.parser import Import
from importlens.screens.analysis_screen import AnalysisScreen
from importlens.screens.input_screen import InputScreen


class ImportLensApp(App):
    TITLE = "importlens"

    def __init__(self, imports: list[Import] | None = None) -> None:
        super().__init__()
        self._imports = imports

    def on_mount(self) -> None:
        if self._imports:
            self.push_screen(AnalysisScreen(self._imports))
        else:
            self.push_screen(InputScreen(), callback=self._on_input_done)

    def _on_input_done(self, imports: list[Import]) -> None:
        self.push_screen(AnalysisScreen(imports))
