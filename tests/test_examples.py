"""Protected public contract examples. These MUST fail on the engine stub."""
import unittest
from csv_schema_audit import audit_csv

SCHEMA = {"version": 1, "columns": [
    {"name": "sku", "type": "string", "required": True},
    {"name": "qty", "type": "integer", "required": True},
    {"name": "active", "type": "boolean", "required": False}]}


class PublicExampleTests(unittest.TestCase):
    def test_synthetic_valid_example(self):
        self.assertEqual(audit_csv("sku,qty,active\nA-1,+02,true\nB-2,-3,\n", SCHEMA),
                         {"valid": True, "rows_checked": 2, "errors": [], "truncated": False})

    def test_synthetic_invalid_example(self):
        self.assertEqual(audit_csv("sku,qty,active\n,2.0,TRUE\n", SCHEMA),
                         {"valid": False, "rows_checked": 1, "errors": [
                             {"row": 1, "column": 1, "code": "required"},
                             {"row": 1, "column": 2, "code": "type_mismatch"},
                             {"row": 1, "column": 3, "code": "type_mismatch"}], "truncated": False})


if __name__ == "__main__":
    unittest.main()
