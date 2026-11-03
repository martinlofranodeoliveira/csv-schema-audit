import unittest
from csv_schema_audit.engine import audit_rows
class EngineTests(unittest.TestCase):
    def test_valid_synthetic(self):
        cols = [{"name": "sku", "type": "string", "required": True}, {"name": "qty", "type": "integer", "required": True}, {"name": "active", "type": "boolean", "required": False}]
        rows = [["A-1", "+02", "true"], ["B-2", "-3", ""]]
        self.assertEqual(audit_rows(rows, cols), {"valid": True, "rows_checked": 2, "errors": [], "truncated": False})
    def test_invalid_synthetic(self):
        cols = [{"name": "sku", "type": "string", "required": True}, {"name": "qty", "type": "integer", "required": True}, {"name": "active", "type": "boolean", "required": False}]
        rows = [["", "2.0", "TRUE"]]
        self.assertEqual(audit_rows(rows, cols), {"valid": False, "rows_checked": 1, "errors": [{"row": 1, "column": 1, "code": "required"}, {"row": 1, "column": 2, "code": "type_mismatch"}, {"row": 1, "column": 3, "code": "type_mismatch"}], "truncated": False})
    def test_enum_and_width(self):
        cols = [{"name": "c", "type": "string", "required": False, "enum": ["a", "b"]}, {"name": "d", "type": "decimal", "required": True}]
        rows = [["x", "1.5"], ["a"], ["b", ""]]
        rep = audit_rows(rows, cols)
        self.assertEqual(rep["rows_checked"], 3)
        self.assertEqual(rep["errors"], [{"row": 1, "column": 1, "code": "enum_mismatch"}, {"row": 2, "column": 0, "code": "row_width"}, {"row": 3, "column": 2, "code": "required"}])
        self.assertFalse(rep["valid"])
        self.assertFalse(rep["truncated"])
    def test_numeric_grammar(self):
        cols = [{"name": "i", "type": "integer", "required": True}, {"name": "d", "type": "decimal", "required": True}, {"name": "b", "type": "boolean", "required": True}]
        good = [["+02", "-3.14", "false"], ["007", "+2", "true"]]
        self.assertTrue(audit_rows(good, cols)["valid"])
        bad = [[" 1", "1.", "True"], ["1.0e3", ".5", "FALSE"]]
        rep = audit_rows(bad, cols)
        self.assertEqual(len(rep["errors"]), 6)
        self.assertEqual(rep["errors"][0], {"row": 1, "column": 1, "code": "type_mismatch"})
    def test_truncation(self):
        cols = [{"name": "q", "type": "integer", "required": True}]
        rows = [["bad!"]] * 101
        rep = audit_rows(rows, cols)
        self.assertFalse(rep["valid"])
        self.assertTrue(rep["truncated"])
        self.assertEqual(rep["rows_checked"], 101)
        self.assertEqual(len(rep["errors"]), 100)
        self.assertEqual(rep["errors"][99], {"row": 100, "column": 1, "code": "type_mismatch"})
if __name__ == "__main__":
    unittest.main()
