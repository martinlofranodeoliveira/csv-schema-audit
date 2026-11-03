"""Protected fixed report shapes and redaction of engine failures."""
ERROR_LIMIT = 100
STRUCTURAL_CODES = frozenset(("input_limit", "invalid_csv", "missing_header", "row_limit", "column_limit", "field_limit", "header_mismatch"))
BUSINESS_CODES = frozenset(("row_width", "required", "type_mismatch", "enum_mismatch"))


class EngineError(RuntimeError):
    """A candidate did not produce an admissible redacted report."""


def structural(code):
    if code not in STRUCTURAL_CODES:
        raise ValueError("invalid_report")
    return {"valid": False, "rows_checked": 0,
            "errors": [{"row": 0, "column": 0, "code": code}], "truncated": False}


def gate(report, widths, column_count):
    """Validate shape, safe codes, true indices, order and basic consistency.

    This is not a reference validator: semantic truth remains the engine's
    responsibility and must pass the separately frozen independent oracle.
    """
    try:
        if type(report) is not dict or set(report) != {"valid", "rows_checked", "errors", "truncated"}:
            raise ValueError
        valid, count, errors, truncated = (report[k] for k in ("valid", "rows_checked", "errors", "truncated"))
        if type(valid) is not bool or type(truncated) is not bool:
            raise ValueError
        if type(count) is not int or count != len(widths):
            raise ValueError
        if type(errors) is not list or len(errors) > ERROR_LIMIT:
            raise ValueError
        if valid != (len(errors) == 0) or (truncated and len(errors) != ERROR_LIMIT):
            raise ValueError
        if valid and truncated:
            raise ValueError
        clean = []
        last = (0, 0)
        for error in errors:
            if type(error) is not dict or set(error) != {"row", "column", "code"}:
                raise ValueError
            row, column, code = (error[k] for k in ("row", "column", "code"))
            if type(row) is not int or type(column) is not int or type(code) is not str:
                raise ValueError
            if not 1 <= row <= len(widths) or code not in BUSINESS_CODES:
                raise ValueError
            if code == "row_width":
                if column != 0 or widths[row - 1] == column_count:
                    raise ValueError
            elif not 1 <= column <= column_count or widths[row - 1] != column_count:
                raise ValueError
            if (row, column) <= last:
                raise ValueError
            last = (row, column)
            clean.append({"row": row, "column": column, "code": code})
        return {"valid": valid, "rows_checked": count, "errors": clean, "truncated": truncated}
    except (KeyError, ValueError, TypeError):
        raise EngineError("engine_error") from None
