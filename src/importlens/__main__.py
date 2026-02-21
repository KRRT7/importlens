from __future__ import annotations

import sys
from pathlib import Path

import click

from importlens.app import ImportLensApp
from importlens.parser import parse


@click.command()
@click.argument("file", required=False, type=click.Path(exists=True, path_type=Path))
def main(file: Path | None) -> None:
    """Visualize python -X importtime output in a TUI."""
    if file:
        imports = parse(file.read_text())
    elif not sys.stdin.isatty():
        imports = parse(sys.stdin.read())
    else:
        imports = None  # paste mode
    ImportLensApp(imports=imports).run()


if __name__ == "__main__":
    main()
