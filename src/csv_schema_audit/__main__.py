"""Protected bounded CLI. No user input is interpolated into diagnostics."""
import json
import os
import stat
import sys

from .api import INPUT_LIMIT, audit_csv
from .report import EngineError, structural
from .schema import SCHEMA_LIMIT, load_schema

USAGE = "usage: csv-schema-audit --schema SCHEMA [CSV|-]\n"


def _json(value):
    return json.dumps(value, ensure_ascii=True, separators=(",", ":")) + "\n"


def _error(code):
    sys.stderr.write(_json({"error": code}))
    return 2


def _read(path, limit):
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC
    fd = os.open(path, flags)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise OSError("not_regular")
        chunks = []
        remaining = limit + 1
        while remaining:
            chunk = os.read(fd, remaining)
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        return b"".join(chunks)
    finally:
        os.close(fd)


def _stdin(limit):
    chunks = []
    remaining = limit + 1
    while remaining:
        chunk = sys.stdin.buffer.read(remaining)
        if not chunk:
            break
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def main(argv=None):
    args = sys.argv[1:] if argv is None else list(argv)
    if args == ["--help"]:
        sys.stdout.write(USAGE)
        return 0
    if (len(args) not in (2, 3) or args[0] != "--schema"
            or not args[1] or args[1] == "-" or args[1].startswith("--")
            or (len(args) == 3 and (not args[2] or (args[2].startswith("-") and args[2] != "-")))):
        return _error("usage")
    try:
        schema_bytes = _read(args[1], SCHEMA_LIMIT)
    except (OSError, ValueError):
        return _error("io_error")
    try:
        schema = load_schema(schema_bytes)
    except ValueError:
        return _error("invalid_schema")
    path = args[2] if len(args) == 3 else "-"
    try:
        data = _stdin(INPUT_LIMIT) if path == "-" else _read(path, INPUT_LIMIT)
    except (OSError, ValueError):
        return _error("io_error")
    if len(data) > INPUT_LIMIT:
        report = structural("input_limit")
    else:
        try:
            text = data.decode("utf-8")
        except UnicodeError:
            return _error("invalid_encoding")
        try:
            report = audit_csv(text, schema)
        except EngineError:
            return _error("engine_error")
    sys.stdout.write(_json(report))
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
