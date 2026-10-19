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
