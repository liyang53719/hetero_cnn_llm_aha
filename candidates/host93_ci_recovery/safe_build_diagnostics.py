"""Pure, fail-closed compiler-log projection. This module performs no I/O.

The caller supplies the independently pinned, public source-path frozenset and
the exact private build root. Neither is discovered from log contents. Result
prose is entirely fixed; a classification is an observation, never a diagnosis.
The byte limit applies to canonical_json(result), including its final newline.
"""

import json
import re

MAX_INPUT_BYTES = 1024 * 1024
MAX_OUTPUT_BYTES = 8192
MAX_ROWS = 20
MAX_MESSAGE_CHARS = 160
MAX_ALLOWLIST_PATHS = 473
_PATH = re.compile(r"[A-Za-z0-9_.+\-]+(?:/[A-Za-z0-9_.+\-]+)*\Z")
_LOCATION = re.compile(
    r"([^:]{1,512}):([1-9][0-9]{0,6}):(?:([1-9][0-9]{0,6}):)? "
    r"(?:fatal error|error): ([ -~]{1,512})\Z"
)
_IDENT = r"[A-Za-z_][A-Za-z0-9_]{0,63}"
_RULES = (
    (
        "syntax_error_reported",
        "Compiler reported a syntax error.",
        re.compile(
            r"(?:expected '[;)}\],:]' before '(?:[;{}()[\],:]|" + _IDENT
            + r")' token|expected ';' after (?:expression|declaration|declarator|"
            r"class definition|struct definition|enum definition|top level declarator)|"
            r"expected expression|expected primary-expression before '[;)}\],:]' token|"
            r"expected declaration or statement at end of input)\Z"
        ),
    ),
    (
        "undeclared_name_reported",
        "Compiler reported an undeclared name.",
        re.compile(
            r"(?:'" + _IDENT + r"' was not declared in this scope|"
            r"use of undeclared identifier '" + _IDENT + r"')\Z"
        ),
    ),
    (
        "unknown_type_reported",
        "Compiler reported an unknown type.",
        re.compile(
            r"(?:unknown type name '" + _IDENT + r"'|'"
            + _IDENT + r"' does not name a type)\Z"
        ),
    ),
    (
        "header_unavailable_reported",
        "Compiler reported an unavailable header.",
        re.compile(
            r"(?:[A-Za-z0-9_.+\-/]{1,128}: No such file or directory|"
            r"'[A-Za-z0-9_.+\-/]{1,128}' file not found)\Z"
        ),
    ),
)
_TERMINATION = re.compile(
    r"(?:cc|c\+\+|gcc|g\+\+|clang|clang\+\+): fatal error: "
    r"Killed signal terminated program (?:cc1|cc1plus)\Z"
)


def canonical_json(result):
    """Return the exact public encoding against which the size cap is enforced."""
    return (json.dumps(result, sort_keys=True, separators=(",", ":"),
                       ensure_ascii=True) + "\n").encode("ascii")


def _safe_relative(path):
    return (
        type(path) is str and 1 <= len(path) <= 240
        and _PATH.fullmatch(path) is not None
        and all(part not in (".", "..") for part in path.split("/"))
    )


def _public_path(raw, build_root, allowed_paths):
    if raw.startswith(build_root + "/"):
        raw = raw[len(build_root) + 1:]
    elif raw.startswith("./"):
        raw = raw[2:]
    # Fixed src/obj_opt compiler layout only; never resolve arbitrary traversal.
    elif raw.startswith("../") and "/" not in raw[3:]:
        raw = "src/" + raw[3:]
    elif raw.startswith("../../include/") and "/" not in raw[14:]:
        raw = "include/" + raw[14:]
    return raw if raw in allowed_paths else None


def _tail(rows):
    lines = []
    for row in rows:
        location = ""
        if "path" in row:
            location = row["path"] + ":" + str(row["line"])
            if row["column"] is not None:
                location += ":" + str(row["column"])
            location += ": "
        lines.append(location + row["category"] + ": " + row["message"])
    return "\n".join(lines)


def sanitize_build_diagnostics(log_bytes, build_root, allowed_paths):
    """Project at most 1 MiB of private bytes into at most 20 sanitized rows.

    allowed_paths must be a fixed frozenset of 1..473 public, canonical relative
    paths supplied by trusted caller configuration. Production integration must
    pin its complete 473-path source list separately. Unknown text is discarded;
    controls, non-ASCII, oversized lines and arbitrary compiler prose are never
    copied. Values from diagnostic prose are never returned, even if recognized.
    """
    if type(log_bytes) is not bytes or len(log_bytes) > MAX_INPUT_BYTES:
        raise ValueError("invalid diagnostic input")
    if (type(build_root) is not str or not build_root.startswith("/")
            or not _safe_relative(build_root[1:])):
        raise ValueError("invalid fixed build root")
    if (type(allowed_paths) is not frozenset
            or not 1 <= len(allowed_paths) <= MAX_ALLOWLIST_PATHS
            or any(not _safe_relative(path) for path in allowed_paths)):
        raise ValueError("invalid fixed path allowlist")
    rows = []
    truncated = False
    # Split only on LF. CR, NUL, ANSI escapes and every other control reject a
    # complete line rather than creating a new line that could look trustworthy.
    for raw in log_bytes.split(b"\n"):
        if not 1 <= len(raw) <= 1024 or any(c < 32 or c > 126 for c in raw):
            continue
        line = raw.decode("ascii")
        row = None
        if _TERMINATION.fullmatch(line):
            row = {
                "category": "compiler_termination_reported",
                "message": "Compiler reported signal termination; cause is unestablished.",
            }
        else:
            match = _LOCATION.fullmatch(line)
            if match is None:
                continue
            raw_path, line_number, column, message = match.groups()
            path = _public_path(raw_path, build_root, allowed_paths)
            if path is None:
                continue
            for category, public_message, grammar in _RULES:
                if grammar.fullmatch(message):
                    row = {
                        "path": path,
                        "line": int(line_number),
                        "column": int(column) if column is not None else None,
                        "category": category,
                        "message": public_message,
                    }
                    break
        if row is not None:
            rows.append(row)
            if len(rows) > MAX_ROWS:
                rows.pop(0)
                truncated = True
    result = {"observations": rows, "stderr_tail": _tail(rows),
              "truncated": truncated}
    while len(canonical_json(result)) > MAX_OUTPUT_BYTES:
        rows.pop(0)
        result["stderr_tail"] = _tail(rows)
        result["truncated"] = True
    return result
