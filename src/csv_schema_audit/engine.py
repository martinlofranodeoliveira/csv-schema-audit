"""Pure bounded CSV business validation."""
def is_integer_cell(cell):
    n = len(cell)
    if n == 0:
        return False
    pos = 0
    first = cell[0]
    if first == "+" or first == "-":
        pos = 1
        if n == 1:
            return False
    idx = pos
    while idx < n:
        ch = cell[idx]
        if ch < "0" or ch > "9":
            return False
        idx = idx + 1
    return True
def is_decimal_cell(cell):
    n = len(cell)
    if n == 0:
        return False
    pos = 0
    first = cell[0]
    if first == "+" or first == "-":
        pos = 1
        if n == 1:
            return False
    idx = pos
    before = 0
    while idx < n:
        ch = cell[idx]
        if ch >= "0" and ch <= "9":
            before = before + 1
            idx = idx + 1
        else:
            if ch == ".":
                if before == 0:
                    return False
                idx = idx + 1
                after = 0
                while idx < n:
                    ch2 = cell[idx]
                    if ch2 < "0" or ch2 > "9":
                        return False
                    after = after + 1
                    idx = idx + 1
                if after == 0:
                    return False
                return True
            else:
                return False
    if before == 0:
        return False
    return True
def is_boolean_cell(cell):
    if cell == "true":
        return True
    if cell == "false":
        return True
    return False
def audit_rows(rows, columns):
    ncols = len(columns)
    nrows = len(rows)
    errors = []
    total = 0
    row_idx = 0
    while row_idx < nrows:
        record = rows[row_idx]
        rownum = row_idx + 1
        if len(record) != ncols:
            total = total + 1
            if len(errors) < 100:
                errors.append({"row": rownum, "column": 0, "code": "row_width"})
        else:
            col_idx = 0
            while col_idx < ncols:
                col = columns[col_idx]
                cell = record[col_idx]
                colnum = col_idx + 1
                if cell == "":
                    if col["required"]:
                        total = total + 1
                        if len(errors) < 100:
                            errors.append({"row": rownum, "column": colnum, "code": "required"})
                else:
                    ctype = col["type"]
                    ok = False
                    if ctype == "string":
                        ok = True
                    else:
                        if ctype == "integer":
                            ok = is_integer_cell(cell)
                        else:
                            if ctype == "decimal":
                                ok = is_decimal_cell(cell)
                            else:
                                if ctype == "boolean":
                                    ok = is_boolean_cell(cell)
                                else:
                                    ok = False
                    if ok:
                        if "enum" in col:
                            enum_vals = col["enum"]
                            if cell in enum_vals:
                                ok = True
                            else:
                                total = total + 1
                                if len(errors) < 100:
                                    errors.append({"row": rownum, "column": colnum, "code": "enum_mismatch"})
                    else:
                        total = total + 1
                        if len(errors) < 100:
                            errors.append({"row": rownum, "column": colnum, "code": "type_mismatch"})
                col_idx = col_idx + 1
        row_idx = row_idx + 1
    valid = total == 0
    truncated = total > 100
    return {"valid": valid, "rows_checked": nrows, "errors": errors, "truncated": truncated}
