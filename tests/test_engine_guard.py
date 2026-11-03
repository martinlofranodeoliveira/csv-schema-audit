"""Protected author regression checks of AST admission, never candidate execution.

The strings below are parsed as data only. They are never compiled, imported,
eval'd, exec'd, or called. No CSV business reference is supplied by these tests.
"""
import ast
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


HELPER = Path("/helper.py")
if not HELPER.exists():
    HELPER = Path(__file__).resolve().parents[1] / "scripts/checks-offline.py"
SPEC = importlib.util.spec_from_file_location("protected_csv_guard", HELPER)
GUARD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GUARD)  # Trusted protected helper only; no candidate import.


def api(body="return None", imports="", prefix=""):
    return imports + prefix + "def audit_rows(rows, columns):\n" + "\n".join(
        "    " + line for line in body.splitlines()) + "\n"


class EngineGuardTests(unittest.TestCase):
    def allow(self, source):
        self.assertIsInstance(GUARD.guard_engine_source(source), ast.Module)

    def deny(self, sources):
        for source in sources:
            with self.subTest(source=source), self.assertRaises(ValueError):
                GUARD.guard_engine_source(source)

    def test_common_pure_operations_are_parseable_without_reference_engine(self):
        self.allow('''import re
from typing import List, Dict, Any
PATTERN = re.compile(r"[a-z]+", re.ASCII)
def _sample(value: str) -> bool:
    return PATTERN.fullmatch(value) is not None
def audit_rows(rows: List[List[str]], columns: List[Dict[str, Any]]) -> dict:
    scratch = []
    for index, row in enumerate(rows, 1):
        scratch.append((index, len(row)))
    labels = {item.get("name", ""): item.get("type", "") for item in columns}
    labels.update({})
    pieces = [text.strip().lower() for row in rows for text in row]
    return {"scratch": scratch, "labels": labels, "pieces": pieces}
''')  # Intentionally not a valid CSV report or semantic engine.

    def test_closed_regex_import_aliases_and_flags(self):
        self.allow(api('return bool(rx.fullmatch("a", "a", flags=rx.ASCII))', "import re as rx\n"))
        self.allow(api('return matches("a", "a", flags=ascii_flag)',
                       "from re import fullmatch as matches, ASCII as ascii_flag\n"))
        self.allow(api('return p.fullmatch("a")', "from re import compile\n", 'p = compile("a")\n'))

    def test_closed_annotation_types_and_stub_are_admissible(self):
        self.allow('''import typing as t
def audit_rows(rows: t.Sequence[t.Sequence[str]], columns: t.List[t.Dict[str, t.Any]]) -> t.Optional[dict]:
    raise NotImplementedError("unimplemented")
''')
        self.allow(api('return type(rows) is list'))

    def test_imported_secret_names_star_and_public_graph_are_rejected(self):
        self.deny([api('return b["open"]("/tmp/not-executed", "w")', 'from re import __builtins__ as b\n'),
                   api('return t.sys.modules["os"].system("NEVER_RUN")', 'import typing as t\n'),
                   api('return re.sys.modules', 'import re\n'),
                   api(imports='from re import *\n'), api(imports='from typing import sys as s\n'),
                   api(imports='from typing import cast\n'), api(imports='from os import path\n'),
                   api(imports='from .re import fullmatch\n')])

    def test_module_objects_cannot_be_aliased_passed_or_returned(self):
        self.deny([api(body, 'import re\n') for body in (
            'x = re\nreturn x.sys', 'return re', 'return dict(value=re)',
            'return [re for item in rows]', 'return rows.append(re)',
            'x = {"module": re}\nreturn x["module"]')])

    def test_imported_calls_and_methods_cannot_be_saved_for_indirect_use(self):
        self.deny([api('x = fullmatch\nreturn x("a", "a")', 'from re import fullmatch\n'),
                   api('x = re.fullmatch\nreturn x("a", "a")', 'import re\n'),
                   api('x = rows.append\nreturn x(1)'),
                   api('return {"f": len}["f"](rows)'),
                   api('return (lambda: None)()'), api('return rows.pop()()')])

    def test_unsafe_builtins_also_cannot_be_callbacks(self):
        self.deny([api(body) for body in (
            'return sorted(rows, key=open)', 'return rows.sort(key=print)',
            'return globals()', 'return getattr(rows, "x")',
            'return eval("NEVER_RUN")', 'return __import__("os")',
            'return type("X", (), {})', 'return compile("x", "x", "exec")')])

    def test_unlisted_attributes_and_effectful_methods_are_rejected(self):
        self.deny([api(body) for body in (
            'return rows.register(1)', 'return "{0.__class__}".format(rows)',
            'return rows.__class__', 'return rows.real',
            'rows.x = 1\nreturn None', 'return rows.system("NEVER_RUN")',
            'return rows.read()', 'return rows.load_module("os")')])

    def test_import_builtin_and_helper_bindings_cannot_be_rebound(self):
        self.deny([api('re = rows\nreturn None', 'import re\n'),
                   api('for re in rows:\n    pass\nreturn None', 'import re\n'),
                   api('try:\n    pass\nexcept Exception as re:\n    pass\nreturn None', 'import re\n'),
                   api('len = rows\nreturn None'),
                   api('audit_rows = rows\nreturn None'),
                   api('return None', 'import re as open\n'),
                   api('return None', 'from re import fullmatch as open\n'),
                   'def helper(re):\n    return None\n' + api(imports='import re\n')])

    def test_annotations_are_types_only_and_not_runtime_capabilities(self):
        self.deny([api('return t.List', 'import typing as t\n'),
                   api('return List(rows)', 'from typing import List\n'),
                   'import typing as t\ndef audit_rows(rows: t.get_type_hints, columns):\n    return None\n',
                   'def audit_rows(rows: len([]), columns):\n    return None\n'])

    def test_no_module_execution_mutable_defaults_or_dynamic_class(self):
        self.deny([api(prefix='state = []\n'), api(prefix='state = ({},)\n'),
                   api(prefix='len([])\n'), api(prefix='class X:\n    pass\n'),
                   api(prefix='def helper(items=[]):\n    return items\n'),
                   '@len\n' + api(), api('def nested():\n    return None\nreturn nested()'),
                   api('global x\nreturn None'), api('import re\nreturn None'),
                   api('return None', prefix='def __getattr__(name):\n    return None\n')])

    def test_signature_and_node_families_are_closed(self):
        self.deny(['def wrong(rows, columns):\n    return None\n',
                   'def audit_rows(rows, columns=()):\n    return None\n',
                   'async def audit_rows(rows, columns):\n    return None\n',
                   api('with rows:\n    pass\nreturn None'),
                   api('del rows[0]\nreturn None')])

    def test_admission_rejects_escape_before_any_namespace_or_subprocess(self):
        # Write source text to an own transient fixture, never import that text.
        source = api('return t.sys.modules["os"].system("NEVER_RUN")', 'import typing as t\n')
        with tempfile.TemporaryDirectory(prefix="csv-ast-only-") as temp:
            root = Path(temp)
            for name, data in (("src/csv_schema_audit/engine.py", source), ("tests/test_engine.py", "# fixture\n")):
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(data)
            paths = ["STATIC-MANIFEST.json", "src/csv_schema_audit/engine.py", "tests/test_engine.py"]
            (root / "STATIC-MANIFEST.json").write_text(json.dumps({"expected_paths": paths,
                "protected_sha256": {}, "editable_paths": paths[1:]}))
            with patch.object(GUARD, "ROOT", root), patch.object(GUARD.sys, "argv", ["helper", "--scaffold-only"]), \
                    patch.object(GUARD, "namespace") as namespace, patch.object(GUARD, "run") as run:
                # The outer .system method is visited before the inner t.sys.
                with self.assertRaisesRegex(ValueError, "^pure_method$"):
                    GUARD.main()
                namespace.assert_not_called()
                run.assert_not_called()

    def test_guarded_bytes_must_match_the_source_snapshot_hash(self):
        # Model a mismatched metadata/read observation; neither string executes.
        with tempfile.TemporaryDirectory(prefix="csv-ast-binding-") as temp:
            root = Path(temp)
            name = "src/csv_schema_audit/engine.py"
            for path, text in ((name, api()), ("tests/test_engine.py", "# fixture\n")):
                target = root / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(text)
            expected = ["STATIC-MANIFEST.json", name, "tests/test_engine.py"]
            (root / "STATIC-MANIFEST.json").write_text(json.dumps({"expected_paths": expected,
                "protected_sha256": {}, "editable_paths": expected[1:]}))
            observed = {path: "0" * 64 for path in expected}
            with patch.object(GUARD, "files", return_value=observed), \
                    patch.object(GUARD, "guard_engine_source") as parse:
                with self.assertRaisesRegex(ValueError, "^engine_source_changed$"):
                    GUARD.verify(root)
                parse.assert_not_called()


if __name__ == "__main__":
    unittest.main()
