"""Recalculate uncached Excel formulas, in place.

pandas/openpyxl only ever read a formula cell's *cached* computed value —
neither one actually evaluates formulas. A workbook generated
programmatically (rather than saved from an open Excel/LibreOffice
session) typically has formulas with no cached value at all, so those
cells silently read back as NaN even though the underlying data and the
formula itself are both perfectly fine.

This module uses the `formulas` package (a pure-Python Excel formula
engine — no external spreadsheet application required) to actually
evaluate every formula in the workbook, then writes the computed values
back into the same cells via openpyxl. Sheet names, order, and layout
are all preserved exactly, so nothing downstream (sample previews,
generated pandas code that reads a specific sheet by name) needs to
change.
"""
import logging
import os
import warnings

import openpyxl

logger = logging.getLogger(__name__)


def recalculate_excel_formulas(path: str) -> bool:
    """Evaluate every formula in the workbook at `path` and overwrite each
    formula cell with its computed literal value, in place.

    Best-effort: if the `formulas` package can't load or evaluate the
    workbook (unsupported function, corrupt file, etc.), the file is left
    untouched and this returns False so callers can fall back to whatever
    they were already doing.

    Returns True if at least one formula cell was recalculated and the
    file was rewritten.
    """
    try:
        import formulas
    except ImportError:
        logger.warning("`formulas` package not installed; skipping Excel formula recalculation.")
        return False

    basename = os.path.basename(path)

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            xl_model = formulas.ExcelModel().loads(path).finish()
            solution = xl_model.calculate()
    except Exception:
        logger.exception("Failed to load/calculate formulas for %s", basename)
        return False

    try:
        wb = openpyxl.load_workbook(path, data_only=False)
    except Exception:
        logger.exception("Failed to open %s with openpyxl for formula rewrite", basename)
        return False

    recalculated = 0
    unresolved = 0
    for ws in wb.worksheets:
        sheet_key = ws.title.upper()
        for row in ws.iter_rows():
            for cell in row:
                if cell.data_type != "f":
                    continue
                key = f"'[{basename}]{sheet_key}'!{cell.coordinate}"
                try:
                    raw_value = solution[key].value
                    cell.value = raw_value.item() if hasattr(raw_value, "item") else raw_value
                    recalculated += 1
                except Exception:
                    # Formula referencing something the engine couldn't
                    # resolve (unsupported function, external ref, error
                    # value, etc.) -- leave this one cell as-is.
                    unresolved += 1

    if recalculated == 0:
        return False

    try:
        wb.save(path)
    except Exception:
        logger.exception("Failed to save recalculated workbook %s", basename)
        return False

    logger.info(
        "Recalculated %d formula cell(s) in %s (%d could not be resolved)",
        recalculated, basename, unresolved,
    )
    return True
