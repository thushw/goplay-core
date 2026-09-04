import os
import io
import sys
import traceback
import pandas as pd
import anthropic
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

SYSTEM_CODE_GEN_PROMPT = """
You are an expert Python Data Engineer. Your task is to generate executable Python code using Pandas to transform a data file.

CRITICAL REQUIREMENTS:
1. Return ONLY pure executable Python code inside a single ```python ``` code block.
2. The code MUST read the input file from `input_path`.
3. Assume `input_path`, `output_path`, `input_format`, and `header_row` variables are already defined in the execution context.
4. `input_format` is either "csv" or "excel" — use the appropriate read/write functions.
5. AGGREGATIONS & GROUPING: When performing `.groupby()`, value counts, or aggregations, ALWAYS ensure result columns (including counts and group keys) are preserved in the final DataFrame. Use `as_index=False` or `.reset_index()` before saving.
6. ALWAYS save with `index=False` unless the user explicitly requested row index numbers.
7. Do NOT include markdown commentary outside the code block.
8. ONLY use column names that are EXACTLY as shown in the provided header/sample. Do NOT guess or invent column names. If unsure, print `df.columns.tolist()` first and verify before writing transformation code.

OUTPUT RULES:
- If the user asks for a SINGLE VALUE (sum, count, average, percentage, top item, "how much", "what is the", etc.), compute it and PRINT the result using `print()`. Do NOT write an output file.
- If the user asks for a TRANSFORMED TABLE (filter, sort, group, clean, deduplicate, etc.), write the result to `output_path` as a normal file.
- When printing aggregation results, format them clearly, e.g.: `print(f"Total Revenue for Patricia: ${total:,.2f}")`
- When writing file output, use `index=False`.

COMPUTED / DERIVED COLUMNS:
- Columns whose names suggest they hold a calculated value (e.g. "Total X", "Subtotal", "Gross Profit", "Amount", "% of Y") are often Excel formula cells. If the source file was generated or exported programmatically, those formulas may never have been evaluated, so pandas reads them back as entirely blank/NaN even though the underlying data is fine.
- If a column you need for the calculation is blank/NaN across the sample rows shown, do NOT trust or sum it directly — derive it yourself from the raw component columns using the obvious business logic implied by the column names (e.g. Total Revenue = Unit Price * Qty; Gross Profit = Total Revenue - Total Cost).
- Before printing a final aggregate result, sanity-check it: if it comes out as exactly 0 or NaN while the matching rows clearly have nonzero raw values (price, quantity, etc.), that is a strong signal you summed a blank computed column instead of deriving the value — recompute from the raw columns instead of printing the suspicious result.

INPUT FORMAT RULES:
- If `input_format` is "csv": Use `pd.read_csv(input_path, header=header_row)` to read and `df.to_csv(output_path, index=False)` to write.
- If `input_format` is "excel": Use `pd.read_excel(input_path, header=header_row)` to read and `df.to_excel(output_path, index=False, engine='openpyxl')` to write.
- For Excel files with multiple sheets, use `sheet_name=None` to read all sheets as a dict of DataFrames, then concatenate them. Add a "sheet_name" column to track which sheet each row came from.
- For Excel output, always write to a single sheet named "Sheet1".

MULTI-SHEET EXCEL RULES:
- When the file has multiple sheets, analyze the sheet names and samples to determine which sheet(s) contain the relevant data.
- If one sheet clearly matches the user's request, use only that sheet.
- If multiple sheets are relevant, combine them and add a "sheet_name" column.
- If it's ambiguous, pick the most likely sheet and note your choice in a comment or print statement.
"""

def extract_python_code(raw_response: str) -> str:
    if "```python" in raw_response:
        return raw_response.split("```python")[1].split("```")[0].strip()
    elif "```" in raw_response:
        return raw_response.split("```")[1].split("```")[0].strip()
    return raw_response.strip()


class GoPlayEngine:
    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        self.client = anthropic.Anthropic(api_key=self.api_key)
        self.resolved_model = self._get_active_haiku_model()

    def _get_active_haiku_model(self) -> str:
        try:
            page = self.client.models.list()
            available_ids = [m.id for m in page.data]
            haiku_models = [m_id for m_id in available_ids if "haiku" in m_id.lower()]

            if haiku_models:
                haiku_models.sort(reverse=True)
                return haiku_models[0]
            return available_ids[0]
        except Exception:
            return "claude-3-haiku-20240307"

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((
            anthropic.APIConnectionError,
            anthropic.InternalServerError,
            anthropic.RateLimitError,
        )),
        reraise=True
    )
    def call_claude_api(self, system_prompt: str, user_prompt: str) -> str:
        response = self.client.messages.create(
            model=self.resolved_model,
            max_tokens=2000,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}]
        )
        return response.content[0].text

    def execute_transformation_with_repair(
        self,
        input_csv_path: str,
        output_csv_path: str,
        user_prompt: str,
        df_sample_str: str,
        input_format: str = "csv",
        header_row: int = 0
    ) -> tuple[bool, str]:
        max_attempts = 2
        error_context = ""

        for attempt in range(1, max_attempts + 1):
            prompt = (
                f"Input Format: {input_format.upper()}\n"
                f"Header Row: {header_row} (0-indexed — use header={header_row} when reading)\n"
                f"File Header & First 3 Rows:\n{df_sample_str}\n\n"
                f"USER REQUEST: {user_prompt}\n"
                f"\nIMPORTANT: Use the EXACT column names shown above. "
                f"Use header={header_row} when reading the file. "
                f"If the file has multiple sheets, the sample shows all sheets — "
                f"your code should read only the relevant sheet.\n"
            )
            if error_context:
                prompt += f"\nYOUR PREVIOUS CODE FAILED WITH ERROR:\n{error_context}\nPlease fix the code and return a corrected version."

            try:
                raw_ai_out = self.call_claude_api(SYSTEM_CODE_GEN_PROMPT, prompt)
                py_code = extract_python_code(raw_ai_out)

                print("\n" + "="*40)
                print("🤖 GENERATED PYTHON CODE:")
                print(py_code)
                print("="*40 + "\n")

                exec_globals = {
                    "pd": pd,
                    "input_path": input_csv_path,
                    "output_path": output_csv_path,
                    "input_format": input_format,
                    "header_row": header_row,
                }

                captured_output = io.StringIO()
                old_stdout = sys.stdout
                sys.stdout = captured_output
                try:
                    exec(py_code, exec_globals)
                finally:
                    sys.stdout = old_stdout

                printed_output = captured_output.getvalue().strip()

                if os.path.exists(output_csv_path) and os.path.getsize(output_csv_path) > 0:
                    return True, printed_output or "Transformation executed successfully."
                elif printed_output:
                    return True, printed_output
                else:
                    error_context = "Output file was not created or was empty."

            except KeyError as e:
                error_context = (
                    f"KeyError: {e} — the column does not exist in the data.\n"
                    f"Available columns when reading the file (header={header_row}):\n"
                )
                try:
                    if input_format == "excel":
                        _df = pd.read_excel(input_csv_path, header=header_row, nrows=0)
                    else:
                        _df = pd.read_csv(input_csv_path, nrows=0)
                    error_context += f"{_df.columns.tolist()}\n"
                except Exception:
                    error_context += "(could not re-read file to list columns)\n"
                error_context += traceback.format_exc()
            except Exception as e:
                error_context = f"{type(e).__name__}: {str(e)}\n{traceback.format_exc()}"

        return False, f"Failed after {max_attempts} attempts. Last error:\n```\n{error_context[:400]}\n```"
