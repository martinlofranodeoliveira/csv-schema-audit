"""Protected public tests for parsing/schema/report boundaries, not an oracle."""
import copy
import csv
import unittest
from unittest.mock import patch

from csv_schema_audit import audit_csv
from csv_schema_audit import api
from csv_schema_audit.schema import load_schema, validate_schema


def schema():
    return {"version": 1, "columns": [{"name": "h", "type": "string", "required": True}]}


def valid(count):
    return {"valid": True, "rows_checked": count, "errors": [], "truncated": False}


class SchemaTests(unittest.TestCase):
    def test_strict_shape_and_types(self):
        for bad in (None, [], {}, {"version": True, "columns": []},
                    {"version": 1, "columns": []},
                    {"version": 1, "columns": [{"name": "h", "type": "text", "required": True}]},
                    {"version": 1, "columns": [{"name": "h", "type": "string", "required": 1}]},
                    {"version": 1, "columns": [{"name": "h", "type": "string", "required": True, "x": 1}]}):
            with self.subTest(bad=bad), self.assertRaisesRegex(ValueError, "^invalid_schema$"):
                validate_schema(bad)

    def test_schema_is_fresh_and_names_are_exact(self):
        original = schema()
        original["columns"][0]["enum"] = ["A", "a"]
        saved = copy.deepcopy(original)
        result = validate_schema(original)
        result[0]["enum"].append("B")
        self.assertEqual(original, saved)
        duplicate = schema()
        duplicate["columns"] *= 2
        with self.assertRaisesRegex(ValueError, "^invalid_schema$"):
            validate_schema(duplicate)

    def test_name_enum_and_utf8_boundaries(self):
        accepted = schema()
        accepted["columns"][0]["name"] = "é" * 32
        accepted["columns"][0]["enum"] = ["é" * 128]
        self.assertEqual(validate_schema(accepted)[0]["enum"], ["é" * 128])
        for key, value in (("name", "é" * 33), ("name", "a\nb"), ("name", "\ud800"),
                           ("enum", ["é" * 129]), ("enum", ["x", "x"]), ("enum", [""])):
            bad = schema()
            bad["columns"][0][key] = value
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "^invalid_schema$"):
                validate_schema(bad)

    def test_json_duplicate_and_nonfinite_keys_rejected(self):
        for data in (b'{"version":1,"version":1,"columns":[]}',
                     b'{"version":1,"columns":[{"name":"h","name":"h","type":"string","required":true}]}',
                     b'{"version":NaN,"columns":[]}', b'\xef\xbb\xbf{}', b'\xff', b' ' * 16385):
            with self.subTest(data=data[:20]), self.assertRaisesRegex(ValueError, "^invalid_schema$"):
                load_schema(data)

    def test_schema_validates_before_text(self):
        with self.assertRaisesRegex(ValueError, "^invalid_schema$"):
            audit_csv(None, {})
        for bad in (None, b"h\n", "\ud800"):
            with self.subTest(bad=repr(bad)), self.assertRaisesRegex(ValueError, "^invalid_input$"):
                audit_csv(bad, schema())


class ParsingTests(unittest.TestCase):
    def assert_structural(self, text, code, definition=None):
        with patch.object(api.engine, "audit_rows", side_effect=AssertionError("engine must not run")):
            report = audit_csv(text, schema() if definition is None else definition)
        self.assertEqual(report, {"valid": False, "rows_checked": 0,
                                  "errors": [{"row": 0, "column": 0, "code": code}], "truncated": False})

    def test_input_before_csv_and_missing_header(self):
        self.assert_structural("\0" + "x" * 65536, "input_limit")
        self.assert_structural("", "missing_header")
        self.assert_structural("\n", "header_mismatch")

    def test_forbidden_bom_nul_and_malformed_csv(self):
        for text in ("\ufeffh\n", "h\nA\0B", 'h\n"unterminated', 'h\nx,y\n"unterminated'):
            self.assert_structural(text, "invalid_csv")

    def test_row_before_column_field_header(self):
        self.assert_structural("wrong\n" + "," * 32 + "\n" + "x\n" * 1000, "row_limit")
        self.assert_structural("," * 32 + "\n" + "x" * 4097, "column_limit")
        self.assert_structural("wrong\n" + "x" * 4097, "field_limit")
        self.assert_structural("wrong\nx\n", "header_mismatch")

    def test_quoted_fields_crlf_and_logical_rows(self):
        text = 'h\r\n"a,b"\r\n"a""b"\r\n"x\ny"\r\n'
        with patch.object(api.engine, "audit_rows", return_value=valid(3)) as engine:
            self.assertEqual(audit_csv(text, schema()), valid(3))
        self.assertEqual(engine.call_args.args[0], [["a,b"], ['a"b'], ["x\ny"]])

    def test_blank_record_reaches_engine_as_zero_fields(self):
        report = {"valid": False, "rows_checked": 2,
                  "errors": [{"row": 1, "column": 0, "code": "row_width"}], "truncated": False}
        with patch.object(api.engine, "audit_rows", return_value=report) as engine:
            self.assertEqual(audit_csv("h\n\nx\n", schema()), report)
        self.assertEqual(engine.call_args.args[0], [[], ["x"]])

    def test_exact_field_and_record_limits(self):
        with patch.object(api.engine, "audit_rows", return_value=valid(1)):
            self.assertEqual(audit_csv("h\n" + "é" * 2048, schema()), valid(1))
        with patch.object(api.engine, "audit_rows", return_value=valid(1000)):
            self.assertEqual(audit_csv("h\n" + "x\n" * 1000, schema()), valid(1000))

    def test_no_field_limit_or_caller_schema_mutation(self):
        original = schema()
        saved = copy.deepcopy(original)
        before = csv.field_size_limit()
        def pretend(rows, columns):
            rows.clear()
            columns.clear()
            return valid(1)
        with patch.object(api.engine, "audit_rows", side_effect=pretend):
            self.assertEqual(audit_csv("h\nx", original), valid(1))
        self.assertEqual(original, saved)
        self.assertEqual(csv.field_size_limit(), before)


class ReportGateTests(unittest.TestCase):
    def test_exception_has_fixed_message_without_input(self):
        for error in (ValueError("SYNTHETIC_PRIVATE_MARKER"), SystemExit("SYNTHETIC_PRIVATE_MARKER")):
            with patch.object(api.engine, "audit_rows", side_effect=error):
                with self.assertRaisesRegex(RuntimeError, "^engine_error$") as raised:
                    audit_csv("h\nSYNTHETIC_PRIVATE_MARKER", schema())
            self.assertTrue(raised.exception.__suppress_context__)

    def test_invalid_shapes_indices_codes_and_consistency(self):
        base = valid(1)
        bads = [None, {}, dict(base, rows_checked=True), dict(base, valid=False),
                dict(base, truncated=True), dict(base, extra="SYNTHETIC_PRIVATE_MARKER")]
        for error in ({"row": 0, "column": 1, "code": "required"},
                      {"row": True, "column": 1, "code": "required"},
                      {"row": 1, "column": 0, "code": "row_width"},
                      {"row": 1, "column": 1, "code": "SYNTHETIC_PRIVATE_MARKER"},
                      {"row": 1, "column": 2, "code": "required"},
                      {"row": 1, "column": 1, "code": "required", "value": "secret"}):
            bads.append({"valid": False, "rows_checked": 1, "errors": [error], "truncated": False})
        duplicate = {"row": 1, "column": 1, "code": "required"}
        bads.append({"valid": False, "rows_checked": 1, "errors": [duplicate, duplicate], "truncated": False})
        for report in bads:
            with self.subTest(report=report), patch.object(api.engine, "audit_rows", return_value=report):
                with self.assertRaisesRegex(RuntimeError, "^engine_error$"):
                    audit_csv("h\nx", schema())

    def test_report_is_copied_and_reordered(self):
        entry = {"code": "required", "column": 1, "row": 1}
        raw = {"truncated": False, "errors": [entry], "rows_checked": 1, "valid": False}
        with patch.object(api.engine, "audit_rows", return_value=raw):
            report = audit_csv("h\n\"\"", schema())
        self.assertEqual(list(report), ["valid", "rows_checked", "errors", "truncated"])
        self.assertEqual(list(report["errors"][0]), ["row", "column", "code"])
        report["errors"][0]["code"] = "changed"
        self.assertEqual(entry["code"], "required")


if __name__ == "__main__":
    unittest.main()
