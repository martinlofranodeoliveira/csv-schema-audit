"""Protected source and installed-wheel checks in distinct offline namespaces.

Default mode qualifies ALL public tests. --scaffold-only is author diagnostics,
not candidate acceptance: it deliberately excludes the two semantic examples
and the editable engine test. No host packages are installed or downloaded.
"""
import argparse
import ast
import builtins
import errno
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import stat
import subprocess
import sys
import tempfile
import time
import zipfile

ROOT = Path(__file__).resolve().parent.parent
PINS = {"setuptools": "78.1.1", "wheel": "0.46.3", "pip": "25.1.1", "packaging": "26.0"}
OMIT = {".git", ".venv", "__pycache__", "build", "dist", ".pytest_cache"}
PURE_BUILTINS = {"abs", "all", "any", "ascii", "bool", "chr", "dict", "enumerate", "float", "frozenset", "int", "isinstance", "issubclass", "len", "list", "max", "min", "ord", "range", "repr", "reversed", "round", "set", "sorted", "str", "sum", "tuple", "type", "zip", "ValueError", "TypeError", "RuntimeError", "NotImplementedError", "Exception", "BaseException"}
BUILTIN_NAMES = frozenset(vars(builtins))
RE_FUNCTIONS = {"compile", "fullmatch", "match", "search", "escape", "findall", "finditer"}
RE_FLAGS = {"A", "ASCII", "I", "IGNORECASE", "M", "MULTILINE", "S", "DOTALL", "X", "VERBOSE", "U", "UNICODE", "NOFLAG"}
TYPING_TYPES = {"Any", "Dict", "List", "Tuple", "Set", "FrozenSet", "Sequence", "Mapping", "Optional", "Union", "Iterable", "Iterator", "Literal"}
PURE_METHODS = {"append", "extend", "insert", "pop", "remove", "clear", "copy", "count", "index", "reverse", "sort", "get", "items", "keys", "values", "setdefault", "update", "add", "discard", "union", "intersection", "difference", "issubset", "issuperset", "startswith", "endswith", "strip", "lstrip", "rstrip", "split", "rsplit", "splitlines", "join", "replace", "lower", "upper", "casefold", "isascii", "isdigit", "isdecimal", "isalpha", "isalnum", "isspace", "encode", "fullmatch", "match", "search", "findall", "finditer", "group", "groups", "groupdict", "start", "end", "span"}
PURE_NODES = {ast.Module, ast.Expr, ast.Constant, ast.Import, ast.ImportFrom, ast.alias, ast.FunctionDef, ast.arguments, ast.arg, ast.Return, ast.Assign, ast.AnnAssign, ast.AugAssign, ast.NamedExpr, ast.For, ast.While, ast.If, ast.IfExp, ast.Compare, ast.BoolOp, ast.BinOp, ast.UnaryOp, ast.Subscript, ast.Slice, ast.List, ast.Tuple, ast.Dict, ast.Set, ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp, ast.comprehension, ast.Call, ast.keyword, ast.Name, ast.Attribute, ast.Pass, ast.Break, ast.Continue, ast.Raise, ast.Try, ast.ExceptHandler, ast.Assert, ast.JoinedStr, ast.FormattedValue, ast.Load, ast.Store, ast.And, ast.Or, ast.Not, ast.UAdd, ast.USub, ast.Invert, ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow, ast.LShift, ast.RShift, ast.BitOr, ast.BitAnd, ast.BitXor, ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.Is, ast.IsNot, ast.In, ast.NotIn}


def guard_engine_source(source):
    """Parse only. Never compile, import or call the candidate. Closed capabilities.

    This is an admission restriction, not a substitute for the offline namespace,
    resource bounds or independent semantic oracle. See ENGINE-AUTHORING.txt.
    """
    tree = ast.parse(source)
    parents = {child: parent for parent in ast.walk(tree) for child in ast.iter_child_nodes(parent)}
    modules, imported_calls, imported_flags, imported_types = {}, {}, set(), set()
    functions, constants, imports = set(), set(), set()
    annotation_nodes = set()

    def name_ok(name):
        return name.isidentifier() and not name.startswith("__")

    def bind(name, collection, regex_compile=False):
        if (not name_ok(name) or (name in BUILTIN_NAMES and not regex_compile)
                or name in imports | functions | constants):
            raise ValueError("pure_binding")
        collection.add(name)

    # Only closed imports, definitions and immutable constants run at module load.
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name not in {"re", "typing"}:
                        raise ValueError("pure_import")
                    local = alias.asname or alias.name
                    bind(local, imports)
                    modules[local] = alias.name
            else:
                if node.level or node.module not in {"re", "typing"}:
                    raise ValueError("pure_import")
                for alias in node.names:
                    allowed = RE_FUNCTIONS | RE_FLAGS if node.module == "re" else TYPING_TYPES
                    if alias.name not in allowed:
                        raise ValueError("pure_import")
                    local = alias.asname or alias.name
                    bind(local, imports, regex_compile=(node.module == "re" and alias.name == local == "compile"))
                    if node.module == "typing":
                        imported_types.add(local)
                    elif alias.name in RE_FUNCTIONS:
                        imported_calls[local] = alias.name
                    else:
                        imported_flags.add(local)
        elif isinstance(node, ast.FunctionDef):
            bind(node.name, functions)
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if not targets or any(not isinstance(target, ast.Name) for target in targets):
                raise ValueError("pure_module_constant")
            for target in targets:
                bind(target.id, constants)
        elif not (isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant)
                  and isinstance(node.value.value, str)):
            raise ValueError("pure_module_statement")

    definitions = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "audit_rows"]
    if len(definitions) != 1:
        raise ValueError("missing_pure_api")
    args = definitions[0].args
    if ([arg.arg for arg in args.args] != ["rows", "columns"] or args.posonlyargs
            or args.kwonlyargs or args.vararg or args.kwarg or args.defaults):
        raise ValueError("pure_api_signature")

    def immutable(node):
        if isinstance(node, ast.Constant):
            return isinstance(node.value, (str, bytes, int, float, complex, bool, type(None)))
        if isinstance(node, ast.Tuple):
            return all(immutable(value) for value in node.elts)
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub, ast.Invert)):
            return immutable(node.operand)
        if isinstance(node, ast.Name):
            return node.id in imported_flags
        if isinstance(node, ast.Attribute):
            return (isinstance(node.value, ast.Name) and modules.get(node.value.id) == "re"
                    and node.attr in RE_FLAGS)
        if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.BitOr, ast.BitAnd, ast.BitXor)):
            return immutable(node.left) and immutable(node.right)
        if isinstance(node, ast.Call):
            target = node.func
            regex = (isinstance(target, ast.Name) and imported_calls.get(target.id) == "compile") or (
                isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name)
                and modules.get(target.value.id) == "re" and target.attr == "compile")
            return (regex and 1 <= len(node.args) <= 2 and not node.keywords
                    and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str)
                    and all(immutable(value) for value in node.args[1:]))
        return False

    for node in tree.body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            if node.value is None or not immutable(node.value):
                raise ValueError("pure_module_constant")
        if isinstance(node, ast.FunctionDef):
            if node.decorator_list or getattr(node, "type_params", ()):
                raise ValueError("pure_definition")
            if any(not immutable(value) for value in node.args.defaults + [v for v in node.args.kw_defaults if v is not None]):
                raise ValueError("pure_default")
    for node in ast.walk(tree):
        if isinstance(node, (ast.arg, ast.AnnAssign)) and node.annotation is not None:
            annotation_nodes.update(ast.walk(node.annotation))
        if isinstance(node, ast.FunctionDef) and node.returns is not None:
            annotation_nodes.update(ast.walk(node.returns))

    reserved = PURE_BUILTINS | imports | functions | constants
    module_target_nodes = {target for node in tree.body if isinstance(node, (ast.Assign, ast.AnnAssign))
                           for target in (node.targets if isinstance(node, ast.Assign) else [node.target])}
    allowed_calls = PURE_BUILTINS | functions | set(imported_calls)
    for node in ast.walk(tree):
        if type(node) not in PURE_NODES or (isinstance(node, ast.comprehension) and node.is_async):
            raise ValueError("pure_syntax")
        parent = parents.get(node)
        if isinstance(node, (ast.Import, ast.ImportFrom, ast.FunctionDef)) and parent is not tree:
            raise ValueError("pure_definition")
        if isinstance(node, ast.Name):
            if not name_ok(node.id):
                raise ValueError("pure_name")
            if node.id in BUILTIN_NAMES - PURE_BUILTINS and node.id not in imported_calls:
                raise ValueError("pure_name")
            if isinstance(node.ctx, ast.Store) and node not in module_target_nodes and node.id in reserved:
                raise ValueError("pure_binding")
            if node.id in modules and not (isinstance(parent, ast.Attribute) and parent.value is node):
                raise ValueError("pure_module_reference")
            if node.id in imported_calls and not (isinstance(parent, ast.Call) and parent.func is node):
                raise ValueError("pure_callable_reference")
            if node.id in imported_types and node not in annotation_nodes:
                raise ValueError("pure_typing_reference")
        if isinstance(node, ast.arg) and (not name_ok(node.arg) or node.arg in reserved | BUILTIN_NAMES):
            raise ValueError("pure_binding")
        if isinstance(node, ast.ExceptHandler) and node.name is not None and (not name_ok(node.name) or node.name in reserved | BUILTIN_NAMES):
            raise ValueError("pure_binding")
        if node in annotation_nodes and not isinstance(node, (ast.Name, ast.Attribute, ast.Subscript, ast.Tuple, ast.List, ast.Constant, ast.Load, ast.BinOp, ast.BitOr)):
            raise ValueError("pure_annotation")
        if isinstance(node, ast.Attribute):
            if node.attr.startswith("_") or not isinstance(node.ctx, ast.Load):
                raise ValueError("pure_attribute")
            module = modules.get(node.value.id) if isinstance(node.value, ast.Name) else None
            if module == "re":
                if node.attr in RE_FLAGS:
                    continue
                if node.attr not in RE_FUNCTIONS or not (isinstance(parent, ast.Call) and parent.func is node):
                    raise ValueError("pure_module_attribute")
            elif module == "typing":
                if node.attr not in TYPING_TYPES or node not in annotation_nodes:
                    raise ValueError("pure_typing_reference")
            elif node.attr not in PURE_METHODS or not (isinstance(parent, ast.Call) and parent.func is node):
                raise ValueError("pure_method")
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                if node.func.id not in allowed_calls:
                    raise ValueError("pure_call")
                if node.func.id == "type" and (len(node.args) != 1 or node.keywords):
                    raise ValueError("pure_type_factory")
            elif not isinstance(node.func, ast.Attribute):
                raise ValueError("pure_call")
    return tree


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def files(root):
    result = {}
    for directory, names, filenames in os.walk(root, followlinks=False):
        names[:] = sorted(n for n in names if n not in OMIT and not n.endswith(".egg-info"))
        for name in names + filenames:
            path = Path(directory) / name
            if path.is_symlink():
                raise ValueError("source_symlink")
        for name in sorted(filenames):
            path = Path(directory) / name
            if not stat.S_ISREG(path.stat().st_mode):
                raise ValueError("source_not_regular")
            result[str(path.relative_to(root))] = sha(path)
    return result


def verify(root):
    manifest = json.loads((root / "STATIC-MANIFEST.json").read_text())
    actual = files(root)
    if set(actual) != set(manifest["expected_paths"]):
        raise ValueError("unexpected_source_members")
    if any(actual.get(name) != digest for name, digest in manifest["protected_sha256"].items()):
        raise ValueError("protected_source_drift")
    for name in ("src/csv_schema_audit/engine.py", "tests/test_engine.py"):
        if (root / name).stat().st_size > 110_000:
            raise ValueError("candidate_file_limit")
    if sum((root / name).stat().st_size for name in manifest["editable_paths"]) > 200_000:
        raise ValueError("candidate_total_limit")
    engine_source = (root / "src/csv_schema_audit/engine.py").read_bytes()
    if hashlib.sha256(engine_source).hexdigest() != actual["src/csv_schema_audit/engine.py"]:
        raise ValueError("engine_source_changed")
    guard_engine_source(engine_source.decode("utf-8", "strict"))
    return actual


def run(command, deadline, env=None):
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError("offline_deadline")
    process = subprocess.Popen(command, env=env, stdin=subprocess.DEVNULL, start_new_session=True)
    try:
        code = process.wait(timeout=remaining)
    except BaseException:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait()
        raise
    if code:
        raise subprocess.CalledProcessError(code, command)


def proof(phase):
    fields = dict(line.split(":", 1) for line in Path("/proc/self/status").read_text().splitlines() if ":" in line)
    assert os.geteuid() == os.getegid() == 1000
    assert int(fields["CapEff"], 16) == 0 and fields["NoNewPrivs"].strip() == "1"
    assert not Path("/home").exists() and not Path("/root").exists()
    assert not Path("/work/.git").exists() and not Path("/work/.env").exists()
    protected = ["/helper.py"]
    if phase in ("source", "build"):
        protected.append("/work/README.md")
    else:
        assert not Path("/work").exists()
        protected.append("/tests/test_scaffold.py")
    if Path("/oracle").exists():
        protected.append(next(str(p) for p in Path("/oracle").glob("test_*.py")))
    for name in protected:
        try:
            fd = os.open(name, os.O_WRONLY)
        except OSError as error:
            assert error.errno == errno.EROFS
        else:
            os.close(fd)
            raise AssertionError("source_or_oracle_writable")
    with socket.socket() as connection:
        try:
            connection.connect(("1.1.1.1", 443))
        except OSError as error:
            assert error.errno == errno.ENETUNREACH
        else:
            raise AssertionError("network_egress")
    print("PROOF", phase, "UID1000 CapEff0 NoNewPrivs1 sourceRO emptyhome noenv ENETUNREACH", flush=True)


def tests(directory, selected, deadline):
    patterns = ["test_scaffold.py", "test_cli.py", "test_engine_guard.py"] if selected else ["test_*.py"]
    for pattern in patterns:
        run(["/usr/bin/python3", "-B", "-m", "unittest", "discover", "-s", directory, "-p", pattern, "-v"], deadline)


def inner(args):
    proof(args.phase)
    deadline = args.deadline
    if args.phase == "source":
        tests("/oracle" if args.oracle_dir else "/work/tests", args.scaffold_only, deadline)
    elif args.phase == "build":
        for name, expected in PINS.items():
            assert importlib.metadata.version(name) == expected, "build_dependency_pin"
        shutil.copytree("/work", "/tmp/build-source")
        os.chdir("/tmp/build-source")
        code = "import setuptools.build_meta as b; print(b.build_wheel('/out'))"
        run(["/usr/bin/python3", "-I", "-B", "-c", code], deadline)
    else:
        wheel = next(Path("/wheel").glob("*.whl"))
        run(["/usr/bin/python3", "-I", "-B", "-m", "pip", "install", "--no-index", "--no-deps", "--no-compile", "--ignore-installed", "--disable-pip-version-check", "--target", "/tmp/site", str(wheel)], deadline)
        os.environ["PYTHONPATH"] = "/tmp/site"
        os.environ["CSV_AUDIT_CONSOLE"] = "/tmp/site/bin/csv-schema-audit"
        run(["/usr/bin/python3", "-B", "-c", "import csv_schema_audit,sys; assert csv_schema_audit.__file__.startswith('/tmp/site/'); assert not any(p.startswith('/work') for p in sys.path)"], deadline)
        run(["/tmp/site/bin/csv-schema-audit", "--help"], deadline)
        tests("/oracle" if args.oracle_dir else "/tests", args.scaffold_only, deadline)


def namespace(source, tests_path, output, oracle, phase, deadline, selected):
    command = ["/usr/bin/bwrap", "--unshare-all", "--unshare-user", "--uid", "1000", "--gid", "1000", "--disable-userns", "--cap-drop", "ALL", "--die-with-parent", "--new-session", "--clearenv"]
    for name in ("usr", "bin", "sbin", "lib", "lib64"):
        path = Path("/") / name
        if path.is_symlink():
            command += ["--symlink", os.readlink(path), "/" + name]
        elif path.exists():
            command += ["--ro-bind", str(path), str(path)]
    if Path("/etc/ld.so.cache").exists():
        command += ["--ro-bind", "/etc/ld.so.cache", "/etc/ld.so.cache"]
    if phase == "wheel":
        command += ["--ro-bind", "/etc/ssl/certs/ca-certificates.crt", "/etc/ssl/certs/ca-certificates.crt"]
    command += ["--proc", "/proc", "--dev", "/dev", "--size", "268435456", "--tmpfs", "/tmp", "--ro-bind", str(source / "scripts/checks-offline.py"), "/helper.py"]
    if phase in ("source", "build"):
        command += ["--ro-bind", str(source), "/work"]
    if phase == "build":
        command += ["--bind", str(output), "/out"]
    if phase == "wheel":
        command += ["--ro-bind", str(output), "/wheel", "--ro-bind", str(tests_path), "/tests"]
    if oracle:
        command += ["--ro-bind", str(oracle), "/oracle"]
    environment = {"PATH": "/usr/bin:/bin", "HOME": "/tmp", "LANG": "C.UTF-8", "TMPDIR": "/tmp", "PYTHONDONTWRITEBYTECODE": "1", "PYTHONNOUSERSITE": "1", "PIP_CONFIG_FILE": "/dev/null"}
    if phase == "source":
        environment["PYTHONPATH"] = "/work/src"
    for key, value in environment.items():
        command += ["--setenv", key, value]
    command += ["--chdir", "/tmp", "--", "/usr/bin/python3", "-B", "/helper.py", "--phase", phase, "--deadline", str(deadline)]
    if oracle:
        command += ["--oracle-dir", "/oracle"]
    if selected:
        command += ["--scaffold-only"]
    return command


def check_wheel(directory):
    wheels = list(directory.iterdir())
    if len(wheels) != 1 or wheels[0].name != "csv_schema_audit-0.1.0-py3-none-any.whl":
        raise ValueError("unexpected_wheel")
    with zipfile.ZipFile(wheels[0]) as archive:
        infos = archive.infolist()
        if len(infos) > 100 or sum(info.file_size for info in infos) > 2_000_000:
            raise ValueError("wheel_limit")
        for info in infos:
            path = Path(info.filename)
            if path.is_absolute() or ".." in path.parts or "\\" in info.filename or stat.S_ISLNK(info.external_attr >> 16):
                raise ValueError("unsafe_wheel_member")
    return sha(wheels[0])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--oracle-dir")
    parser.add_argument("--scaffold-only", action="store_true")
    parser.add_argument("--phase", choices=("source", "build", "wheel"))
    parser.add_argument("--deadline", type=float)
    args = parser.parse_args()
    if args.phase:
        if args.deadline is None:
            raise ValueError("missing_deadline")
        inner(args)
        return
    if args.scaffold_only and args.oracle_dir:
        raise ValueError("partial_oracle_check_refused")
    before = verify(ROOT)
    oracle_original = Path(args.oracle_dir).resolve(strict=True) if args.oracle_dir else None
    oracle_before = files(oracle_original) if oracle_original else None
    if oracle_before is not None and (not oracle_before or any(not name.endswith(".py") for name in oracle_before)):
        raise ValueError("oracle_members")
    deadline = time.monotonic() + 120
    try:
        with tempfile.TemporaryDirectory(prefix="csv-audit-check-") as temporary:
            scratch = Path(temporary)
            source = scratch / "source"
            for name in before:
                target = source / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / name, target)
            assert files(source) == before
            wheel_output = scratch / "wheel"
            wheel_output.mkdir()
            oracle = None
            if oracle_original:
                oracle = scratch / "oracle"
                shutil.copytree(oracle_original, oracle, ignore=shutil.ignore_patterns(*OMIT))
                assert files(oracle) == oracle_before
            try:
                for phase in ("source", "build", "wheel"):
                    command = namespace(source, source / "tests", wheel_output, oracle, phase, deadline, args.scaffold_only)
                    run(command, deadline, {"PATH": "/usr/bin:/bin"})
                    if phase == "build":
                        wheel_sha = check_wheel(wheel_output)
                print("SCAFFOLD-ONLY PASS; NOT CANDIDATE QUALIFICATION" if args.scaffold_only else "ALL PUBLIC CHECKS PASS", "wheel_sha256=" + wheel_sha, flush=True)
            finally:
                assert files(source) == before, "source_snapshot_changed"
                if oracle:
                    assert files(oracle) == oracle_before, "oracle_snapshot_changed"
    finally:
        assert files(ROOT) == before, "original_source_changed"
        if oracle_original:
            assert files(oracle_original) == oracle_before, "original_oracle_changed"


if __name__ == "__main__":
    main()
