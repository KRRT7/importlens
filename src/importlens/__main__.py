from __future__ import annotations

import argparse
import sys
from pathlib import Path

from rich.console import Console
from rich.table import Table

from importlens.parser import Import, parse


def add_rows(table: Table, imports: list[Import], prefix: str = "", is_last: bool = True) -> None:
    for i, imp in enumerate(imports):
        last = i == len(imports) - 1
        connector = "└── " if last else "├── "
        name = f"{prefix}{connector}[bold]{imp.name}[/]" if prefix or i > 0 or not last else f"{connector}[bold]{imp.name}[/]"
        if not prefix and i == 0 and len(imports) == 1:
            name = f"[bold]{imp.name}[/]"
        # Simpler: always use prefix + connector
        name = f"{prefix}{connector}[bold]{imp.name}[/]"

        table.add_row(name, f"{imp.self_us:,}", f"{imp.cumul_us:,}")

        child_prefix = prefix + ("    " if last else "│   ")
        add_rows(table, imp.children, child_prefix, last)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="importlens",
        description="Visualize python -X importtime output",
    )
    parser.add_argument(
        "file",
        nargs="?",
        type=Path,
        default=None,
        help="Path to importtime output (default: stdin)",
    )
    args = parser.parse_args(argv)

    if args.file:
        text = args.file.read_text()
    elif not sys.stdin.isatty():
        text = sys.stdin.read()
    else:
        parser.error("provide a file or pipe importtime output to stdin")

    imports = parse(text)
    if not imports:
        print("No import time data found.", file=sys.stderr)
        return 1

    console = Console()

    table = Table(title="Import Times")
    table.add_column("Module", style="cyan", no_wrap=True)
    table.add_column("Self (µs)", justify="right", style="bold yellow")
    table.add_column("Cumulative (µs)", justify="right")

    add_rows(table, imports)

    console.print(table)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
