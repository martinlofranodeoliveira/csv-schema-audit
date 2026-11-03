"""Protected public CLI error/IO tests; no customer data is used."""
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

from csv_schema_audit import api
from csv_schema_audit import __main__ as cli

SCHEMA = b'{"version":1,"columns":[{"name":"h","type":"string","required":true}]}'


class CLITests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="csv-public-cli-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.definition = self.root / "schema.json"
        self.definition.write_bytes(SCHEMA)
        self.data = self.root / "input.csv"
        self.data.write_bytes(b"wrong\nx\n")

    def run_cli(self, args, data=b""):
        console = os.environ.get("CSV_AUDIT_CONSOLE")
        command = [console] if console else [sys.executable, "-B", "-m", "csv_schema_audit"]
        return subprocess.run(command + args, input=data, capture_output=True, timeout=10, check=False)

    def assert_error(self, result, code):
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, b"")
        self.assertEqual(result.stderr, ('{"error":"' + code + '"}\n').encode())

    def test_usage_and_help(self):
        for args in ([], ["--schema"], ["--schema", "-"], ["--unknown", "SYNTHETIC_PRIVATE_MARKER"],
                     ["--schema", str(self.definition), "-bad"],
                     ["--schema", str(self.definition), "-", "extra"]):
            with self.subTest(args=args):
                self.assert_error(self.run_cli(args), "usage")
        result = self.run_cli(["--help"])
        self.assertEqual((result.returncode, result.stdout, result.stderr),
                         (0, b"usage: csv-schema-audit --schema SCHEMA [CSV|-]\n", b""))

    def test_redacted_file_error(self):
        self.assert_error(self.run_cli(["--schema", str(self.root / "SYNTHETIC_PRIVATE_MARKER")]), "io_error")

    def test_schema_precedes_input_open(self):
        self.definition.write_bytes(b"{}")
        self.assert_error(self.run_cli(["--schema", str(self.definition), str(self.root / "absent")]), "invalid_schema")

    def test_duplicate_json_keys_bom_and_bad_encoding(self):
        for data in (b'{"version":1,"version":1,"columns":[]}', b'\xef\xbb\xbf{}', b'\xff'):
            self.definition.write_bytes(data)
            self.assert_error(self.run_cli(["--schema", str(self.definition)]), "invalid_schema")

    def test_schema_cap_before_decode(self):
        self.definition.write_bytes(b" " * 16384 + b"\xff")
        self.assert_error(self.run_cli(["--schema", str(self.definition)]), "invalid_schema")

    def test_csv_encoding_is_fixed_error(self):
        self.assert_error(self.run_cli(["--schema", str(self.definition)], b"h\n\xff"), "invalid_encoding")

    def test_csv_cap_precedes_decode_and_syntax(self):
        result = self.run_cli(["--schema", str(self.definition)], b"x" * 65536 + b"\xff")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stderr, b"")
        self.assertEqual(json.loads(result.stdout), {"valid": False, "rows_checked": 0,
            "errors": [{"row": 0, "column": 0, "code": "input_limit"}], "truncated": False})

    def test_stdin_and_path_reports_have_exact_bytes(self):
        expected = b'{"valid":false,"rows_checked":0,"errors":[{"row":0,"column":0,"code":"header_mismatch"}],"truncated":false}\n'
        results = [self.run_cli(["--schema", str(self.definition)], b"wrong\nx\n"),
                   self.run_cli(["--schema", str(self.definition), "-"], b"wrong\nx\n"),
                   self.run_cli(["--schema", str(self.definition), str(self.data)])]
        for result in results:
            self.assertEqual((result.returncode, result.stdout, result.stderr), (1, expected, b""))

    def test_final_symlink_directory_and_fifo_are_rejected(self):
        link = self.root / "link"
        link.symlink_to(self.definition)
        self.assert_error(self.run_cli(["--schema", str(link)]), "io_error")
        link.unlink()
        link.symlink_to(self.data)
        self.assert_error(self.run_cli(["--schema", str(self.definition), str(link)]), "io_error")
        self.assert_error(self.run_cli(["--schema", str(self.definition), str(self.root)]), "io_error")
        fifo = self.root / "fifo"
        os.mkfifo(fifo)
        self.assert_error(self.run_cli(["--schema", str(self.definition), str(fifo)]), "io_error")

    def test_engine_exception_is_redacted_without_stdout(self):
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch.object(api.engine, "audit_rows", side_effect=ValueError("SYNTHETIC_PRIVATE_MARKER")), \
             patch.object(sys, "stdin", types.SimpleNamespace(buffer=io.BytesIO(b"h\nx\n"))), \
             contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = cli.main(["--schema", str(self.definition), "-"])
        self.assertEqual((code, stdout.getvalue(), stderr.getvalue()), (2, "", '{"error":"engine_error"}\n'))


if __name__ == "__main__":
    unittest.main()
