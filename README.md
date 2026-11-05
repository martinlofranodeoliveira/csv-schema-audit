<!-- public-docs-pt:v1 -->
# Auditoria de CSV com esquema explícito

Audita CSV local com limites de recursos e diagnósticos sem ecoar valores. Mantém contrato público, testes protegidos e checagem da distribuição instalada.

**Estado:** edição pública de desenvolvimento. Recursos e limites detalhados estão na referência técnica preservada abaixo.

## Começar em português

**Requisitos:** Python 3.10+; CLI de arquivo requer POSIX O_NOFOLLOW.

```sh
git clone https://github.com/martinlofranodeoliveira/csv-schema-audit.git
cd csv-schema-audit
python3 -m venv .venv
.venv/bin/python -m pip install .
.venv/bin/csv-schema-audit --help
```

Use um ambiente de desenvolvimento separado. Não envie `.env`, chaves, bancos,
uploads ou dados pessoais ao Git. Nas demonstrações, use somente dados fictícios.

## Documentação e validação

[Guia adicional em português](README.pt-BR.md) · [Planejamento](ROADMAP.md) · [Licença](LICENSE) · [Catálogo do laboratório](https://github.com/martinlofranodeoliveira#projetos-abertos)

Os comandos acima foram conferidos nos manifests/guia público; não significam que todas as integrações, plataformas ou serviços reais foram exercitados nesta revisão documental.

A referência técnica original abaixo preserva APIs, exemplos, limites e histórico
de funcionalidades. Auxiliares em `community/` são módulos independentes: sua
existência não comprova integração na interface ou no fluxo principal. Ao avaliar
uma funcionalidade, consulte também o teste e o código do módulo correspondente.

## Contribuir

Abra uma issue com objetivo, comportamento observado, versão e um exemplo mínimo
sintético. Para código, inclua testes relevantes, instruções de reprodução e
atualização da documentação. Não envie segredos ou informações de terceiros em
issues, exemplos, capturas ou pull requests. Mudanças úteis e completas têm
preferência sobre alterações feitas apenas para aumentar atividade.

## Licença e autoria

Licença declarada no repositório: **MIT**. Consulte o arquivo de licença e mantenha as atribuições de terceiros.

Nome técnico e URL preservados para manter imports, links e automações existentes.
Título, descrição e tópicos em português facilitam localizar a finalidade do projeto.

<!-- public-docs-pt:end -->

---

## Referência técnica e documentação original

# csv-schema-audit

A small offline Python library and CLI for checking CSV against an explicit schema. Runtime dependencies: none. Python3.10+; the path-reading CLI requires POSIX `O_NOFOLLOW`. No network, schema inference, repair or spreadsheet evaluation.

Acceptance requires all public tests and a separately frozen independent oracle. The originating template has two deliberately incomplete editable stubs, which must be replaced before a qualified release. This documentation defines behavior, not a claim that an unqualified checkout passes. The scaffold's passing checks alone do not qualify a release.

## Use

After building and installing an accepted wheel:

```text
csv-schema-audit --schema examples/schema.json examples/valid.csv
csv-schema-audit --schema examples/schema.json examples/invalid.csv
cat examples/valid.csv | csv-schema-audit --schema examples/schema.json
```

The valid synthetic example exits0 and prints:

```json
{"valid":true,"rows_checked":2,"errors":[],"truncated":false}
```

The invalid synthetic example exits1 and prints:

```json
{"valid":false,"rows_checked":1,"errors":[{"row":1,"column":1,"code":"required"},{"row":1,"column":2,"code":"type_mismatch"},{"row":1,"column":3,"code":"type_mismatch"}],"truncated":false}
```

```python
from csv_schema_audit import audit_csv
schema = {"version": 1, "columns": [
    {"name": "qty", "type": "integer", "required": True}]}
report = audit_csv("qty\n+02\n", schema)
```

The library performs no I/O and does not mutate caller arguments or CSV globals. The supported host retains the normal stdlib CSV field limit, at least65,536. A caller that externally lowers that global is outside this ABI.

## Contract

[CONTRACT.txt](CONTRACT.txt) contains the complete accepted contract and public examples, followed by the defensive engine-error addendum. Header order/names must exactly match the explicit schema, even when a cell is optional. Unknown schema keys, duplicate names and duplicate JSON keys are rejected. No trimming, normalization or coercion.

`required` rejects an empty string. An optional empty string skips type and enum. Nonempty cells use exact raw-string enum membership after type validation. Types are string; integer with optional sign and ASCII digits; decimal with optional sign, ASCII digits and optional dot plus digits; and exactly `true`/`false`. No exponents, nonfinite numbers or Unicode numeric coercion. Decimal accepts integer-shaped tokens. `=`, `+`, `-`, `@` are ordinary inert text; no spreadsheet/export escaping is claimed.

Inclusive limits:65,536 input UTF-8 bytes,16,384 raw/compact schema bytes,1,000 data records,32 fields per record,4,096 UTF-8 bytes per decoded field,100 stored errors. Names are1..64 UTF-8 bytes without NUL/CR/LF; enum has1..32 distinct strings of1..256 bytes without NUL. Schema columns are1..32.

Parsing is the documented Python strict comma/double-quote dialect, including quoted commas/newlines, doubled quotes, LF/CRLF and normal bare-CR handling. A blank line is a zero-field record; a final terminator adds no row. CSV BOM/NUL is invalid. Structural precedence: input_limit, invalid_csv, missing_header, row_limit, column_limit, field_limit, header_mismatch. Parsing finishes before business validation. Structural errors use row0/column0 and rows_checked0.

Business errors are row_width at column0, otherwise required/type_mismatch/enum_mismatch at the1-based schema column; records are logical data records excluding the header. Width-invalid rows skip cells. One error per cell, ordered by row then column. All rows are visited; only the first100 errors are stored, truncated means more than100 occurred, and valid means no errors.

## CLI outcomes

stdout/stderr contain compact ASCII JSON with one LF and no filenames, supplied values, header/schema names or parser exceptions. Exit0 means valid,1 means validation failure. Exit2 has empty stdout and one stderr code: usage,io_error,invalid_schema,invalid_encoding, or engine_error. An engine failure/unsafe report is never a successful audit; the API raises RuntimeError("engine_error") without the candidate exception as an exposed cause.

The syntax is exactly `csv-schema-audit --schema SCHEMA [CSV|-]`, or standalone `--help`. Schema is validated before CSV is opened. CSV defaults to bounded stdin; raw CSV over65,536 bytes returns input_limit before decode. Schema over16,384 bytes is invalid_schema before decode. Only regular files may be opened; final-component symlinks, devices, FIFOs and directories are refused. Parent symlinks are not forbidden. Schema cannot be stdin. Prefix a CSV filename starting with `-` with `./`.

## Development and checks

```text
/usr/bin/python3 scripts/checks-offline.py
/usr/bin/python3 scripts/checks-offline.py --scaffold-only
```

The default runs all public tests in a read-only offline source namespace, builds a wheel in a separate disposable namespace, and tests the installed wheel/console in a third namespace where the source tree is absent. No host installation/download is done. Wheel phase mounts only the system public CA bundle read-only so distro pip can import; the network stays isolated. The diagnostic flag runs only protected scaffold/CLI tests and is explicitly not candidate acceptance. It is expected to pass while the full stub suite fails. Root's independent oracle is external and not supplied in this repository; a future trusted qualifier may pass `--oracle-dir` for separate source+wheel oracle runs. Diagnostic/oracle modes cannot be combined.

Locally available build tools are pinned: setuptools78.1.1, wheel0.46.3, pip25.1.1, packaging26.0. The optional `build` frontend is not needed; the helper calls the PEP517 backend directly in its disposable copy, then uses pip --no-index --no-deps --target only inside the namespace. Missing/different tools or unsupported namespaces fail checks, with no fallback. The256MiB tmpfs is a storage limit, not an aggregate process-memory claim; launcher/controller budgets remain separate. CI installs the pinned build tools on its disposable hosted runner before the offline check. No provider, customer data, auth or runtime controller is involved.

See [Portuguese quickstart](README.pt-BR.md), [roadmap](ROADMAP.md), and the MIT [license](LICENSE).
