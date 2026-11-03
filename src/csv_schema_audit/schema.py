"""Protected, strict schema validation. No schema inference or coercion."""
import json

SCHEMA_LIMIT = 16_384
COLUMN_LIMIT = 32


def validate_schema(schema):
    """Return a fresh validated column list; never mutate a supplied object."""
    try:
        if type(schema) is not dict or len(schema) != 2 or any(type(key) is not str for key in schema) or set(schema) != {"version", "columns"}:
            raise ValueError
        if type(schema["version"]) is not int or schema["version"] != 1:
            raise ValueError
        columns = schema["columns"]
        if type(columns) is not list or not 1 <= len(columns) <= COLUMN_LIMIT:
            raise ValueError
        names = set()
        result = []
        for column in columns:
            if type(column) is not dict or len(column) not in (3, 4) or any(type(key) is not str for key in column):
                raise ValueError
            if set(column) not in ({"name", "type", "required"}, {"name", "type", "required", "enum"}):
                raise ValueError
            name = column["name"]
            if type(name) is not str or not 1 <= len(name.encode("utf-8")) <= 64:
                raise ValueError
            if any(c in name for c in ("\0", "\r", "\n")) or name in names:
                raise ValueError
            names.add(name)
            if type(column["type"]) is not str or column["type"] not in ("string", "integer", "decimal", "boolean"):
                raise ValueError
            if type(column["required"]) is not bool:
                raise ValueError
            clean = {"name": name, "type": column["type"], "required": column["required"]}
            if "enum" in column:
                values = column["enum"]
                if type(values) is not list or not 1 <= len(values) <= 32:
                    raise ValueError
                seen = set()
                for value in values:
                    if type(value) is not str or not 1 <= len(value.encode("utf-8")) <= 256:
                        raise ValueError
                    if "\0" in value or value in seen:
                        raise ValueError
                    seen.add(value)
                clean["enum"] = list(values)
            result.append(clean)
        encoded = json.dumps(schema, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")
        if len(encoded) > SCHEMA_LIMIT:
            raise ValueError
        return result
    except (ValueError, TypeError, UnicodeError, OverflowError, RecursionError):
        raise ValueError("invalid_schema") from None


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("invalid_schema")
        result[key] = value
    return result


def load_schema(data):
    """Decode one bounded UTF-8 schema, rejecting duplicate JSON keys."""
    try:
        if type(data) is not bytes or len(data) > SCHEMA_LIMIT:
            raise ValueError
        text = data.decode("utf-8")
        if text.startswith("\ufeff"):
            raise ValueError
        schema = json.loads(text, object_pairs_hook=_object,
                            parse_constant=lambda value: (_ for _ in ()).throw(ValueError()))
        validate_schema(schema)
        return schema
    except (ValueError, TypeError, UnicodeError, OverflowError, RecursionError):
        raise ValueError("invalid_schema") from None
