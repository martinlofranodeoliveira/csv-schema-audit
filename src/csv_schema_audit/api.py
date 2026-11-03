"""Protected public boundary: bounded CSV parsing before pure engine use."""
import csv
import io

from . import engine
from .report import EngineError, gate, structural
from .schema import validate_schema

INPUT_LIMIT = 65_536
ROW_LIMIT = 1_000
COLUMN_LIMIT = 32
FIELD_LIMIT = 4_096


def audit_csv(text, schema):
    """Audit bounded CSV with a validated explicit schema. No I/O occurs here."""
    columns = validate_schema(schema)
    try:
        if type(text) is not str:
            raise ValueError
        encoded = text.encode("utf-8")
    except (ValueError, UnicodeError):
        raise ValueError("invalid_input") from None
    if len(encoded) > INPUT_LIMIT:
        return structural("input_limit")
    if "\0" in text or text.startswith("\ufeff"):
        return structural("invalid_csv")
    try:
        records = list(csv.reader(io.StringIO(text, newline=""), delimiter=",",
                                 quotechar='"', doublequote=True, escapechar=None,
                                 skipinitialspace=False, strict=True))
    except csv.Error:
        return structural("invalid_csv")
    if not records:
        return structural("missing_header")
    if len(records) - 1 > ROW_LIMIT:
        return structural("row_limit")
    if any(len(record) > COLUMN_LIMIT for record in records):
        return structural("column_limit")
    if any(len(field.encode("utf-8")) > FIELD_LIMIT for record in records for field in record):
        return structural("field_limit")
    if records[0] != [column["name"] for column in columns]:
        return structural("header_mismatch")
    rows = records[1:]
    widths = tuple(len(row) for row in rows)
    count = len(columns)
    try:
        report = engine.audit_rows(rows, columns)
    except BaseException:
        raise EngineError("engine_error") from None
    return gate(report, widths, count)
