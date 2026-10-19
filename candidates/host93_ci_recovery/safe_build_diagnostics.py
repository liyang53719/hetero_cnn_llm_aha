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


# Context is a bounded diagnostic for this public-source, clean-environment build.
# These finite redactions are NOT a general-purpose secret-removal guarantee.
MAX_CONTEXT_BYTES = 16 * 1024
MAX_CONTEXT_LINES = 80
MAX_CONTEXT_LINE_CHARS = 512
_PRIVATE_BEGIN = re.compile(r'-----BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY-----')
_PRIVATE_END = re.compile(r'-----END (?:[A-Z0-9]+ )*PRIVATE KEY-----')
_URL = re.compile(r'(?i)\b(?:[a-z][a-z0-9+.-]{1,20}://|www\.)[^\s\x00-\x1f\"\'<>]+')
_HEADER = re.compile(r'(?i)\b(?:proxy-authorization|authorization|x-api-key|x-auth-token|cookie|set-cookie)\s*:\s*.*')
_SECRET_NAME = r'[A-Za-z0-9_.-]{0,128}(?:password|passwd|pwd|secret|token|api[_-]?key|access[_-]?key|private[_-]?key|credential|authorization|cookie|session[_-]?id)[A-Za-z0-9_.-]{0,128}'
_SECRET_VALUE = r'''(?:"(?:\\.|[^"\\\n])*"|'(?:\\.|[^'\\\n])*'|[^\s,;\}\]]+)'''
_KEY_VALUE = re.compile(r'(?i)(?<![A-Za-z0-9_.-])([\"\']?' + _SECRET_NAME + r'[\"\']?[ \t]*[:=][ \t]*)' + _SECRET_VALUE)
_SECRET_OPTION = re.compile(r'(?i)(?<![A-Za-z0-9_.-])(--' + _SECRET_NAME + r'[ \t]+)' + _SECRET_VALUE)
_AUTH = re.compile(r'(?i)\b(?:Bearer|Basic)[ \t]+[^\s,;\}\]]+')
_QUOTED_PATH = re.compile(r'''(["'`])(?:[A-Za-z]:[\\/]|\\\\|/|~/)[^\n]*?\1''')
_OPTION_PATH = re.compile(r'''(-(?:I|L|isystem|iquote|include|imacros|idirafter|iprefix|iwithprefixbefore|iwithprefix|isysroot|MF|MT|MQ|B|o))(?:/|[A-Za-z]:[\\/])[^\s"'`<>\[\]{}(),;:]+''')
_ABSOLUTE_PATH = re.compile(r'''(?<![A-Za-z0-9_./\\])(?:/(?![/*])|[A-Za-z]:[\\/]|\\\\|~/)[^\s"'`<>\[\]{}(),;:]+''')
_LONG_TOKEN = re.compile(r'[A-Za-z0-9_+/.=\-]{40,}')
_KNOWN_TOKEN = re.compile(r'\b(?:(?:AKIA|ASIA)[A-Z0-9]{16}|(?:gh[pousr]_|github_pat_|sk-)[A-Za-z0-9_-]{12,})\b')
_LINE_MARKER = '...[TRUNCATED]'


def _visible_ascii(text):
    """Escape all controls, invalid UTF-8 and non-ASCII; LF is split by caller."""
    out = []
    for char in text:
        n = ord(char)
        if 32 <= n <= 126:
            out.append(char)
        elif char == '\t':
            out.append('\\t')
        elif char == '\r':
            out.append('\\r')
        elif n <= 255:
            out.append('\\x%02x' % n)
        elif n <= 65535:
            out.append('\\u%04x' % n)
        else:
            out.append('\\U%08x' % n)
    return ''.join(out)


def _redact_context_line(line):
    # Redact before clipping, so no clipping boundary exposes a partial secret.
    # Preserve credential keys until their values have been redacted.
    line = _HEADER.sub('[AUTH_HEADER]', line)
    line = _AUTH.sub('[AUTH]', line)
    line = _KEY_VALUE.sub(lambda m: m[1] + '[REDACTED]', line)
    line = _SECRET_OPTION.sub(lambda m: m[1] + '[REDACTED]', line)
    line = _URL.sub('[URL]', line)
    line = _QUOTED_PATH.sub(lambda m: m[1] + '[PATH]' + m[1], line)
    line = _OPTION_PATH.sub(lambda m: m[1] + '[PATH]', line)
    line = _ABSOLUTE_PATH.sub('[PATH]', line)
    line = _KNOWN_TOKEN.sub('[TOKEN]', line)
    line = _LONG_TOKEN.sub('[LONG_TOKEN]', line)
    return _visible_ascii(line)


def sanitize_build_context(log_bytes, build_root, allowed_paths):
    """Keep a consecutive suffix of at most 80 redacted merged-log lines.

    Each line is at most 512 printable ASCII characters; the entire returned
    diagnostics object, canonical JSON plus LF, is at most 16 KiB. Old fixed
    observations remain a bounded adjunct. All input lines are scanned before
    selecting the suffix so PEM blocks beginning earlier are still covered.
    An unmatched END marker conservatively redacts the prefix through that END,
    including a block whose BEGIN fell outside the caller's 1 MiB read window.
    """
    observed = sanitize_build_diagnostics(log_bytes, build_root, allowed_paths)
    raw_lines = log_bytes.decode('utf-8', errors='backslashreplace').split('\n')
    if raw_lines[-1] == '':
        raw_lines.pop()  # A terminal LF is a terminator, not another log record.
    private = [False] * len(raw_lines)
    block_start = None
    prefix_end = -1
    for index, line in enumerate(raw_lines):
        if _PRIVATE_BEGIN.search(line):
            if block_start is None:
                block_start = index
        if _PRIVATE_END.search(line):
            if block_start is None:
                prefix_end = index
            else:
                private[block_start:index+1] = [True] * (index + 1 - block_start)
            block_start = None
    if prefix_end >= 0:
        private[:prefix_end+1] = [True] * (prefix_end+1)
    if block_start is not None:
        private[block_start:] = [True] * (len(raw_lines) - block_start)
    selected = range(max(0, len(raw_lines) - MAX_CONTEXT_LINES), len(raw_lines))
    lines = []
    truncated = len(raw_lines) > MAX_CONTEXT_LINES or observed['truncated']
    for index in selected:
        line = '[PRIVATE_KEY]' if private[index] else _redact_context_line(raw_lines[index])
        if len(line) > MAX_CONTEXT_LINE_CHARS:
            line = line[:MAX_CONTEXT_LINE_CHARS-len(_LINE_MARKER)] + _LINE_MARKER
            truncated = True
        lines.append(line)
    result = {'observations': observed['observations'], 'merged_log_tail': '\n'.join(lines),
              'truncated': truncated, 'context_state': 'AVAILABLE'}
    while len(canonical_json(result)) > MAX_CONTEXT_BYTES:
        # Drop only oldest whole lines; never pick isolated matching errors.
        lines.pop(0)
        result['merged_log_tail'] = '\n'.join(lines)
        result['truncated'] = True
    return result
