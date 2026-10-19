"""Pure tests; called only after same-buffer size/SHA-256 verification."""


def run_tests(module):
    sanitize = module["sanitize_build_diagnostics"]
    encode = module["canonical_json"]
    limit = module["MAX_INPUT_BYTES"]
    root = "/private/fixed/build"
    paths = frozenset(("src/unit.cpp", "include/api.h"))
    checks = 0

    def check(condition, label):
        nonlocal checks
        checks += 1
        if not condition:
            raise RuntimeError("sanitizer test failed: " + label)

    def result(data, allowlist=paths):
        value = sanitize(data, root, allowlist)
        encoded = encode(value)
        check(len(encoded) <= 8192, "encoded byte bound")
        check(len(value["observations"]) <= 20, "row bound")
        check(len(value["stderr_tail"].splitlines()) <= 20, "tail row bound")
        check(all(len(row["message"]) <= 160 for row in value["observations"]),
              "message bound")
        check(all(32 <= b <= 126 or b == 10 for b in encoded), "ASCII encoding")
        check(root.encode() not in encoded, "private root excluded")
        return value

    def reject_input(data, fixed_root=root, allowlist=paths):
        try:
            sanitize(data, fixed_root, allowlist)
        except ValueError as exc:
            check(str(exc) in ("invalid diagnostic input", "invalid fixed build root",
                               "invalid fixed path allowlist"), "fixed rejection text")
        else:
            raise RuntimeError("sanitizer test failed: input accepted")

    good = b"src/unit.cpp:12:3: error: expected ';' before '}' token"
    gcc = result(good)
    check(gcc["observations"][0] == {
        "path": "src/unit.cpp", "line": 12, "column": 3,
        "category": "syntax_error_reported", "message": "Compiler reported a syntax error.",
    }, "GCC location and fixed syntax observation")
    clang = result(b"/private/fixed/build/src/unit.cpp:44:9: error: "
                   b"use of undeclared identifier 'private_identifier'")
    check(clang["observations"][0]["category"] == "undeclared_name_reported",
          "Clang undeclared category")
    check(b"private_identifier" not in encode(clang), "identifier excluded")
    no_column = result(b"./include/api.h:2: fatal error: missing.h: No such file or directory")
    check(no_column["observations"][0]["column"] is None, "GCC missing column")
    check(b"missing.h" not in encode(no_column), "header detail excluded")
    layout_paths = paths | frozenset(("src/V3Foo.cpp", "include/header.h"))
    source_layout = result(b"../V3Foo.cpp:25:7: error: expected expression", layout_paths)
    check(source_layout["observations"][0]["path"] == "src/V3Foo.cpp",
          "fixed obj_opt parent-source basename mapping")
    header_layout = result(b"../../include/header.h:3:2: error: unknown type name 'private_type'",
                           layout_paths)
    check(header_layout["observations"][0]["path"] == "include/header.h",
          "fixed obj_opt include basename mapping")
    check(b"../" not in encode(source_layout) + encode(header_layout),
          "fixed layout output is canonical and relative")
    for unknown_layout in (
        b"../../../src/V3Foo.cpp", b"../../../include/header.h",
        b"../../src/V3Foo.cpp", b"../src/V3Foo.cpp",
        b"../nested/V3Foo.cpp", b"../../include/nested/header.h",
        b"../../include/../header.h", b"../V3Unknown.cpp",
        b"../../include/unknown.h", b"../", b"../.", b"../..",
        b"../../include/", b"../../include/.", b"../../include/..",
        b"./../V3Foo.cpp", b"./../../include/header.h",
        b"..//V3Foo.cpp", b"../../include//header.h",
    ):
        rejected = result(unknown_layout + b":1:2: error: expected expression", layout_paths)
        check(rejected["observations"] == [], "unknown layout or unlisted mapping rejected")
    clang_header = result(b"src/unit.cpp:2:1: fatal error: 'missing.h' file not found")
    check(clang_header["observations"][0]["category"] == "header_unavailable_reported",
          "Clang missing header")
    unknown_type = result(b"src/unit.cpp:2:1: error: unknown type name 'private_type'")
    check(unknown_type["observations"][0]["category"] == "unknown_type_reported",
          "unknown type category")
    check(b"private_type" not in encode(unknown_type), "type value excluded")
    termination = result(b"c++: fatal error: Killed signal terminated program cc1plus")
    check(termination["observations"][0]["category"] == "compiler_termination_reported",
          "termination observation")
    check("unestablished" in termination["observations"][0]["message"],
          "termination is not a root-cause claim")
    check("OOM" not in termination["stderr_tail"], "no OOM inference")

    malicious = (
        b"https://private.example/token=secret",
        b"Authorization: Bearer private_secret",
        b"TOKEN=private_secret",
        b"ENV_SECRET=private_secret",
        b"src/unit.cpp:1:2: error: https://private.example/token=secret",
        b"src/unit.cpp:1:2: error: Authorization: Bearer private_secret",
        b"src/unit.cpp:1:2: error: tensor=[1.1,2.2,3.3]",
        b"src/unit.cpp:1:2: error: 'secret' was not declared in this scope TOKEN=abc",
        b"src/unit.cpp:1:2: error: unexpected diagnostic prose",
        b"/unrecognized/private/source.cpp:1:2: error: expected expression",
        b"/private/fixed/build-evil/src/unit.cpp:1:2: error: expected expression",
        b"/private/fixed/build/../src/unit.cpp:1:2: error: expected expression",
        b"src/../src/unit.cpp:1:2: error: expected expression",
        b"unlisted.cpp:1:2: error: expected expression",
        b"src/unit.cpp:0:2: error: expected expression",
        b"src/unit.cpp:1:0: error: expected expression",
        b"src/unit.cpp:10000000:2: error: expected expression",
        b"src/unit.cpp:1:2: warning: expected expression",
        b"make: *** [Makefile:8: private_target] Error 2",
        "make: *** [Makefile:8: priváté_target] Error 2".encode("utf-8"),
        "src/unit.cpp:1:2: error: ‘secret’ was not declared in this scope".encode("utf-8"),
        good + b"\r",
        b"\x1b[31m" + good,
        good + b"\x00",
        good + b"\t",
        b"private\r" + good,
        b"private\v" + good,
        b"private\f" + good,
        b"x" * 1025,
    )
    for hostile in malicious:
        value = result(hostile)
        check(value["observations"] == [] and value["stderr_tail"] == "",
              "unknown or unsafe complete line dropped")
    combined = result(b"\n".join(malicious + (good, good)))
    check(len(combined["observations"]) == 2, "multiple safe errors survive noise")
    check(b"secret" not in encode(combined) and b"https" not in encode(combined),
          "malicious contents excluded")
    secret_identifier = result(b"src/unit.cpp:1:1: error: "
                               b"use of undeclared identifier 'TOKEN_private_secret'")
    check(b"TOKEN" not in encode(secret_identifier) and b"private_secret" not in encode(secret_identifier),
          "even recognized token-like identifiers cannot be copied")
    many = result(b"\n".join(b"src/unit.cpp:%d:1: error: expected expression" % n
                              for n in range(1, 101)))
    check(many["truncated"] is True, "row truncation recorded")
    check([row["line"] for row in many["observations"]] == list(range(81, 101)),
          "last twenty accepted observations retained")
    long_path = "src/" + "p" * 232 + ".cpp"
    long_allowlist = frozenset((long_path,))
    long_rows = result(b"\n".join((long_path + ":%d:1: error: expected expression" % n).encode()
                                   for n in range(1, 21)), long_allowlist)
    check(long_rows["truncated"] is True and len(long_rows["observations"]) < 20,
          "encoded byte bound truncates oldest rows")
    check(long_rows["observations"][-1]["line"] == 20, "byte bound preserves latest observation")
    full_list = frozenset("src/public_%03d.cpp" % n for n in range(473))
    public_line = b"src/public_472.cpp:1:2: error: expected expression"
    full = result(public_line, full_list)
    check(len(full["observations"]) == 1, "complete 473-path configuration")
    check(b"public_471" not in encode(full), "no path inventory disclosure")
    at_limit = result(b"x" * limit)
    check(at_limit["observations"] == [], "one-MiB limit accepted and safely dropped")
    reject_input(b"x" * (limit + 1))
    reject_input("not bytes")
    reject_input(bytearray(good))
    reject_input(good, "relative/root")
    reject_input(good, "/private/../root")
    reject_input(good, root + "\nsecret")
    reject_input(good, allowlist=["src/unit.cpp"])
    reject_input(good, allowlist=frozenset())
    reject_input(good, allowlist=frozenset(("/private/source.cpp",)))
    reject_input(good, allowlist=frozenset(("src/../source.cpp",)))
    reject_input(good, allowlist=frozenset("p%d.cpp" % n for n in range(474)))
    reject_input(good, allowlist=frozenset(("src/token\n.cpp",)))
    check(result(b"")["observations"] == [], "empty input")
    return checks


def run_context_tests(module):
    sanitize = module['sanitize_build_context']
    encode = module['canonical_json']
    root = '/private/fixed/build'
    paths = frozenset(('src/unit.cpp', 'include/api.h'))
    checks = 0

    def check(ok, label):
        nonlocal checks
        checks += 1
        if not ok:
            raise RuntimeError('context test failed: ' + label)

    def result(raw):
        value = sanitize(raw, root, paths)
        check(set(value) == {'observations','merged_log_tail','truncated','context_state'}, 'exact keys')
        check(value['context_state'] == 'AVAILABLE', 'available even for empty input')
        check(len(encode(value)) <= 16384, 'whole diagnostic canonical cap')
        tail = value['merged_log_tail']
        lines = tail.split('\n') if tail else []
        check(len(lines) <= 80 and all(len(x) <= 512 for x in lines), 'line caps')
        check(all(32 <= ord(x) <= 126 or x == '\n' for x in tail), 'visible ASCII')
        return value

    positive = [
        "g++ -I../include -c V3Ast__gen.cpp -o V3Ast__gen.o",
        "V3Ast__gen.cpp:19:7: error: no matching function for call to 'AstNode::clone(int)'",
        '   19 | AstNode* result = node.clone(1);',
        '      |                  ~~~~~~~~~~^~~',
        'In file included from ../V3Ast.cpp:41:',
        "../V3AstNodeExpr.h:22:3: note: candidate expects 2 arguments, 1 provided",
        "bison: verilog.y:583: error: unexpected identifier",
        "Can't locate Parse/RecDescent.pm in @INC (you may need to install the Parse::RecDescent module)",
        'syntax error at ../astgen line 18, near "=>"',
        'make[2]: *** [../Makefile_obj:29: V3Ast__gen.o] Error 1',
        'make[1]: *** [Makefile:64: opt] Error 2',
        '',
        'arbitrary short compiler text without a known category',
    ]
    value = result(('\n'.join(positive)+'\n').encode())
    check(value['merged_log_tail'] == '\n'.join(positive), 'complete consecutive compiler/Perl/bison context')
    check(value['observations'] == [], 'context retained independently of old category matches')
    check(not value['truncated'], 'short complete context not truncated')
    for path in ('/home/alice/build/src/generated.cpp', 'C:\\Users\\alice\\generated.cpp',
                 '\\\\server\\share\\generated.cpp', '~/private/file', '/private/fixed/build/src/unit.cpp'):
        tail = result((path + ':41:2: error: generated source failed').encode())['merged_log_tail']
        check(path not in tail and '[PATH]:41:2: error:' in tail, 'absolute location redacted and coordinates retained')
    for raw in ("make: Entering directory '/home/alice/work tree'", 'g++ -I/private/include -L/opt/lib file.cpp',
                'cc --sysroot=/private/sysroot file.cpp', 'opened "/private/path with spaces/file"'):
        tail = result(raw.encode())['merged_log_tail']
        check('/private' not in tail and '/home/alice' not in tail and '/opt/lib' not in tail, 'embedded/quoted path redaction')
    for raw in ('src/obj_opt/V3Ast__gen.cpp:1: error: failed', '../generated.cpp:2: error: failed',
                '../../include/config_package.h:3: error: failed', 'int result = lhs / rhs;', 'one/two: error'):
        check(result(raw.encode())['merged_log_tail'] == raw, 'relative paths and ordinary slash syntax retained')
    for raw, secret in (
        ('TOKEN=small-secret', 'small-secret'), ('password: "a secret with spaces"', 'a secret with spaces'),
        ("{'api_key': 'short-secret'}", 'short-secret'), ('AWS_SECRET_ACCESS_KEY=small-secret', 'small-secret'),
        ('Authorization: Bearer short-secret', 'short-secret'), ('authorization : Basic c2VjcmV0', 'c2VjcmV0'),
        ('Proxy-Authorization: Basic tiny', 'tiny'), ('Cookie: SID=short-cookie; other=x', 'short-cookie'),
        ('Set-Cookie: SID=short-cookie; Secure', 'short-cookie'), ('X-Api-Key: tiny-key', 'tiny-key'),
        ('client_secret="short secret"', 'short secret'), ('--password short-secret --verbose', 'short-secret'),
        ('--access-token=small-secret', 'small-secret'), ('Bearer short-secret', 'short-secret'),
        (r'password="a\" escaped-secret"', 'escaped-secret'),
        (r"password='a\' escaped-secret'", 'escaped-secret'),
        ('credential=secret-value', 'secret-value'), ('session_id: small-secret', 'small-secret'),
        ('see https://user:pass@example.invalid/private?token=tiny', 'example.invalid'),
        ('see ssh://git@example.invalid/project', 'example.invalid'), ('see www.example.invalid/token', 'example.invalid'),
        ('key AKIAABCDEFGHIJKLMNOP', 'AKIAABCDEFGHIJKLMNOP'), ('key ghp_abcdefghijklmnop', 'ghp_abcdefghijklmnop'),
        ('opaque ' + 'aB7_'*16, 'aB7_'*16), ('jwt ' + 'abcD'*12 + '.' + 'efGH'*12, 'abcD'*12),
    ):
        tail = result(raw.encode())['merged_log_tail']
        check(secret not in tail, 'credential/url/token fixture redacted')
    for label in ('PRIVATE KEY','RSA PRIVATE KEY','EC PRIVATE KEY','OPENSSH PRIVATE KEY','ENCRYPTED PRIVATE KEY'):
        raw = ('before\n-----BEGIN '+label+'-----\nshort key body\n-----END '+label+'-----\nafter').encode()
        check(result(raw)['merged_log_tail'] == 'before\n[PRIVATE_KEY]\n[PRIVATE_KEY]\n[PRIVATE_KEY]\nafter', 'multiline PEM preserves record positions')
    raw = b'-----BEGIN PRIVATE KEY-----\n' + b'short key line\n'*100 + b'-----END PRIVATE KEY-----\nafter'
    tail = result(raw)['merged_log_tail']
    check('short key' not in tail and tail.endswith('\nafter') and len(tail.split('\n')) == 80, 'key start before 80-line boundary')
    check(result(b'partial private body\n-----END PRIVATE KEY-----\nafter')['merged_log_tail'] == '[PRIVATE_KEY]\n[PRIVATE_KEY]\nafter', 'truncated input missing BEGIN')
    check(result(b'before\n-----BEGIN PRIVATE KEY-----\nshort body')['merged_log_tail'] == 'before\n[PRIVATE_KEY]\n[PRIVATE_KEY]', 'unclosed key block')
    check(result(b'first\n-----END PRIVATE KEY-----\nsecond\n-----END PRIVATE KEY-----')['merged_log_tail'] == '\n'.join(['[PRIVATE_KEY]']*4), 'multiple orphan END markers')
    raw = b'a\x00b\x1b[31m\r\t\x7f\xff' + '\u202e'.encode('utf-8')
    tail = result(raw)['merged_log_tail']
    for escaped in ('\\x00','\\x1b','\\r','\\t','\\x7f','\\xff','\\u202e'):
        check(escaped in tail, 'control/unicode/invalid UTF-8 visible')
    lines = [('context %03d' % n) for n in range(100)]
    value = result(('\n'.join(lines)+'\n').encode())
    check(value['merged_log_tail'] == '\n'.join(lines[-80:]) and value['truncated'], 'last consecutive 80 records')
    value = result(('many short words '*100 + ' TOKEN=never-expose').encode())
    check(len(value['merged_log_tail']) == 512 and value['merged_log_tail'].endswith('...[TRUNCATED]') and value['truncated'], 'line cap after redaction')
    check('never-expose' not in value['merged_log_tail'], 'clip cannot expose secret')
    raw = '\n'.join(('record %03d ' % n) + 'word '*98 for n in range(80)).encode()
    value = result(raw); tail = value['merged_log_tail']
    check(value['truncated'] and 1 < len(tail.split('\n')) < 80, 'whole-object byte cap drops oldest complete records')
    check(tail.split('\n')[-1].startswith('record 079 ') and all(('record %03d ' % n) in tail for n in range(int(tail[7:10]),80)), 'byte cap retains consecutive suffix')
    check(result(b'')['merged_log_tail'] == '', 'empty log explicitly available')
    check(result(b'\n\n\n')['merged_log_tail'] == '\n\n', 'blank records retained')
    # F01: every fixed GCC joined path option must remove absolute machine paths.
    joined_options = ('I','L','isystem','iquote','include','imacros','idirafter',
                      'iprefix','iwithprefixbefore','iwithprefix','isysroot',
                      'MF','MT','MQ','B','o')
    for option in joined_options:
        for path in ('/private/fixed/build/deps.d', r'C:\private\build\deps.d'):
            value = result(('g++ -'+option+path+' -c unit.cpp').encode())
            tail = value['merged_log_tail']
            check(path not in tail and '-'+option+'[PATH]' in tail,
                  'F01 fixed joined GCC option removes absolute path')
        raw = 'g++ -'+option+'generated/deps.d -c unit.cpp'
        check(result(raw.encode())['merged_log_tail'] == raw,
              'F01 fixed option preserves relative generated name')
    # F02: long key names must be recognized before token-like runs are collapsed.
    for key in ('CMAKE_PRIVATE_AUTHENTICATION_SERVICE_PASSWORD',
                'BUILD_CONFIGURATION_CREDENTIAL_PROVIDER_API_KEY',
                'X_'*45+'TOKEN'):
        for value in ('"tiny-secret"', "'tiny secret'", 'tiny-secret'):
            tail = result((key+'='+value).encode())['merged_log_tail']
            check('tiny-secret' not in tail and 'tiny secret' not in tail and '[REDACTED]' in tail,
                  'F02 long credential key with short value redacted')
        tail = result(('--'+key+' "tiny-secret"').encode())['merged_log_tail']
        check('tiny-secret' not in tail and '[REDACTED]' in tail,
              'F02 long credential option with short value redacted')
    raw = 'CMAKE_PUBLIC_BUILD_CONFIGURATION_VARIABLE_NAME="ordinary-value"'
    tail = result(raw.encode())['merged_log_tail']
    check('ordinary-value' in tail and '[LONG_TOKEN]' in tail,
          'F02 ordinary unmatched short prose survives long-name folding')
    # Bound-sized degenerate inputs exercise scanner/regex termination without native work.
    for raw in (b'-'*1048576, b'x'*1048576, (b'-----END PRIVATE KEY-----\n'*40000)):
        value = result(raw)
        check(value['context_state'] == 'AVAILABLE', 'bounded degenerate input completes')
    for raw in (None, 'text', b'x'*1048577):
        try:
            sanitize(raw, root, paths)
        except ValueError:
            check(True, 'invalid context input rejected')
        else:
            raise RuntimeError('invalid context input accepted')
    return checks
