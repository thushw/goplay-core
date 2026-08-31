# goplay-core

Self-healing document and CSV transformation engine powered by Claude.

Give it a data file (CSV or Excel), a plain-English instruction, and a sample of
the data. It asks a Claude Haiku model to generate pandas code, executes it, and
if the code raises an error it feeds the traceback back to Claude to repair it
(up to two attempts).

- **Transformed table** requests (filter, sort, group, clean, deduplicate) are
  written to an output file.
- **Single-value** requests (sum, count, average, "how much…") are computed and
  printed; no file is written.

## Requirements

- Python 3.10–3.12
- An Anthropic API key (`ANTHROPIC_API_KEY`) for real transformations. The test
  suite is fully mocked and needs no key.

## Installation

```bash
git clone https://github.com/thushw/goplay-core.git
cd goplay-core

python3 -m venv .venv
source .venv/bin/activate

pip install --upgrade pip
pip install -e ".[dev]"
```

## Usage

### Command line

```bash
export ANTHROPIC_API_KEY=sk-ant-...

# transform a table -> writes data.transformed.csv
goplay data.csv "keep only rows where region is East, sorted by revenue desc"

# aggregation -> prints the result, writes no file
goplay sales.xlsx "what is the total revenue for Patricia?"

# non-standard header row and explicit output path
goplay report.xlsx "dedupe on email" -o clean.xlsx --header-row 2
```

| Option | Description |
| --- | --- |
| `input` | Path to the input CSV or Excel file. |
| `prompt` | Plain-English description of the transformation. |
| `-o, --output` | Output path (default: `<input>.transformed.<ext>`). Ignored for aggregation queries. |
| `--format {csv,excel}` | Override extension-based format detection. |
| `--header-row N` | 0-indexed header row for files with non-standard headers (default: `0`). |
| `--api-key KEY` | Anthropic API key (defaults to `ANTHROPIC_API_KEY`). |

Exit codes: `0` success, `1` transformation failed, `2` bad input or missing key.

### Library

```python
import pandas as pd
from goplay_core import GoPlayEngine

engine = GoPlayEngine()  # reads ANTHROPIC_API_KEY from the environment
df = pd.read_csv("data.csv")
sample = df.head(3).to_csv(index=False)

success, result = engine.execute_transformation_with_repair(
    input_csv_path="data.csv",
    output_csv_path="out.csv",
    user_prompt="Sum revenue by region, sorted descending",
    df_sample_str=sample,
    input_format="csv",   # or "excel"
    header_row=0,
)
print(success, result)
```

## Development

```bash
pytest tests/ -v
```

CI runs the test suite on Python 3.10, 3.11, and 3.12
(`.github/workflows/test.yml`).

## Project layout

```
src/goplay_core/
  engine.py   GoPlayEngine: API client, code-gen prompt, execute-and-repair loop
  models.py   get_active_haiku_model(): picks the newest available Haiku model
  cli.py      goplay command-line entry point
tests/
  test_models.py
```

## License

MIT
