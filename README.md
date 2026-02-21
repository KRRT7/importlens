# importlens

Visualize `python -X importtime` output in your terminal.

## Usage

```bash
# From a file
python -X importtime -c "import json" 2> importtime.txt
uv run -m importlens importtime.txt

# From stdin
python -X importtime -c "import json" 2>&1 | uv run -m importlens
```

## Install

```bash
uv sync
```
