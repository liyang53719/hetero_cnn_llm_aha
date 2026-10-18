"""Fixed five-deb / 67 regular-member staging worker. No installation or execution.

SOURCE candidate only. Accepted opaque-byte identity review is fixed in PINS.
Use stage_fixed() only from the separately reviewed bounded parent entrypoint.
Pure functions are exposed for synthetic cold tests, never an alternate CLI.
"""
import hashlib
import json
import lzma
import os
from pathlib import Path
import re
import stat

PINS_BYTES = 205675
PINS_SHA256 = "abc9e5f55b045b6402cc5c13e4d4c4263eb6a7403e84b01a165a12b5d5d20cd0"
INPUT_ROOT = "/UNBOUND_HOST93_DEPENDENCY_INPUT"
OUTPUT_ROOT = "/UNBOUND_HOST93_DEPENDENCY_OUTPUT"
SELECTED_COUNT = 67
SELECTED_BYTES = 3598623
MAX_OUTPUT_BYTES = 8 * 1024 * 1024
MAX_REPORT_BYTES = 512 * 1024
MAX_FILE_BYTES = 4 * 1024 * 1024
CFG_PATH = "usr/share/autoconf/autom4te.cfg"
CFG_SHA = "a72748b80a0aa61a968f662fc07fedf2002ff5fd325692f882070c564a351662"
CFG_BYTES = 5143
CFG_DERIVED_BYTES = None
CFG_DERIVED_SHA = None
CFG_LINES = (118, 145, 159, 171)
CFG_OLD = b"args: --prepend-include '/usr/share/autoconf'\n"
CFG_NEW = ("args: --prepend-include '" + OUTPUT_ROOT + "/usr/share/autoconf'\n").encode("ascii")
DIRECTORY_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
READ_FLAGS = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def exact(raw, size, digest, label):
    require(type(size) is int and 0 <= size <= MAX_FILE_BYTES, label + " size pin")
    require(isinstance(digest, str) and re.fullmatch("[0-9a-f]{64}", digest), label + " SHA pin")
    require(len(raw) == size and sha(raw) == digest, label + " identity")


def json_unique(raw):
    def pairs(items):
        result = {}
        for k, v in items:
            require(k not in result, "duplicate JSON key")
            result[k] = v
        return result
    return json.loads(raw, object_pairs_hook=pairs)


def clean_relative(path, *, root_ok=False):
    require(isinstance(path, str) and len(path) <= 256, "path length/type")
    require(all(32 < ord(c) < 127 and c not in "\\:" for c in path), "path characters")
    if root_ok and path == ".":
        return path
    require(path and not path.startswith("/"), "absolute/empty path")
    parts = path.split("/")
    require(all(p not in ("", ".", "..") for p in parts), "path traversal/empty component")
    return path


def tar_path(raw, kind):
    require(raw.startswith("./"), "tar path must start with one ./")
    value = raw[2:]
    if kind == "5":
        if value.endswith("/"):
            value = value[:-1]
        if not value:
            value = "."
    return clean_relative(value, root_ok=(kind == "5"))


def text_field(raw):
    value, sep, tail = raw.partition(b"\0")
    require(not sep or not any(tail), "nonzero string field tail")
    require(all(32 <= c < 127 for c in value), "non-ASCII/control tar field")
    return value.decode("ascii")


def octal(raw, label, *, empty_ok=False):
    require(not raw[0] & 128, label + " base256 forbidden")
    value = raw.rstrip(b"\0 ").lstrip(b" ")
    require((empty_ok and not value) or re.fullmatch(b"[0-7]+", value), label + " octal encoding")
    return int(value or b"0", 8)


def ar_entries(raw, expected):
    require(raw.startswith(b"!<arch>\n"), "ar magic")
    require([x["name"] for x in expected] == ["debian-binary", "control.tar.xz", "data.tar.xz"], "ar fixed names")
    pos = 8
    answer = {}
    for pin in expected:
        require(pos + 60 <= len(raw), "ar short header")
        h = raw[pos:pos+60]
        require(h[58:60] == b"`\n", "ar header marker")
        name = h[:16].rstrip(b" ").decode("ascii")
        require(name == pin["name"], "ar member order/name")
        require(re.fullmatch(b"[0-9]+ *", h[16:28]), "ar timestamp encoding")
        require(re.fullmatch(b"[0-9]+ *", h[28:34]) and re.fullmatch(b"[0-9]+ *", h[34:40]), "ar uid/gid encoding")
        require(re.fullmatch(b"[0-7]+ *", h[40:48]), "ar mode encoding")
        require(re.fullmatch(b"[0-9]+ *", h[48:58]), "ar size encoding")
        size = int(h[48:58])
        require(size == pin["bytes"], "ar size pin")
        pos += 60
        require(pos + size <= len(raw), "ar member truncation")
        payload = raw[pos:pos+size]
        exact(payload, size, pin["sha256"], "ar " + name)
        require(payload.startswith(bytes.fromhex(pin["prefix_hex"])), "ar payload prefix")
        answer[name] = payload
        pos += size
        if size % 2:
            require(raw[pos:pos+1] == b"\n", "ar odd padding")
            pos += 1
    require(pos == len(raw), "ar tail/extra entry")
    require(answer["debian-binary"] == b"2.0\n", "debian version")
    return answer


def expand_xz(raw, size, digest):
    require(0 < size <= MAX_FILE_BYTES, "expanded stream bound")
    require(raw.startswith(bytes.fromhex("fd377a585a00")), "XZ magic")
    decoder = lzma.LZMADecompressor(format=lzma.FORMAT_XZ, memlimit=64 * 1024 * 1024)
    data = decoder.decompress(raw, max_length=size + 1)
    require(len(data) == size, "XZ output size/excess")
    require(decoder.eof and not decoder.unused_data, "XZ unfinished/concatenated/trailing stream")
    exact(data, size, digest, "expanded tar")
    return data


def parse_tar(raw, framing):
    """Only ordinary GNU ustar-space-space-NUL headers; no tarfile abstraction."""
    require(len(raw) == framing["expanded_bytes"] and len(raw) % 512 == 0, "tar expanded size")
    require(framing["raw_headers"] <= 1024, "tar header bound")
    pos, rows, bodies, seen, counts = 0, [], {}, {}, {}
    while pos + 512 <= len(raw):
        h = raw[pos:pos+512]
        if h == b"\0" * 512:
            tail = raw[pos:]
            require(len(tail) >= 1024 and not any(tail), "tar two-zero/tail")
            require(len(tail) == framing["zero_tail_bytes"], "tar tail size pin")
            break
        require(len(rows) < framing["raw_headers"], "tar excess header")
        require(h[257:265] == b"ustar  \0", "tar unsupported magic/version")
        require(not any(h[345:512]), "tar GNU extension fields unsupported")
        stored = octal(h[148:156], "checksum")
        require(stored == sum(h[:148]) + 8 * 32 + sum(h[156:]), "tar header checksum")
        kind = h[156:157].decode("ascii")
        require(kind in ("0", "5", "2"), "tar unknown type/extension")
        mode = octal(h[100:108], "mode")
        require(mode in (0o644, 0o755, 0o777), "tar unsupported mode")
        for field, label in ((h[108:116], "uid"), (h[116:124], "gid"), (h[136:148], "mtime")):
            octal(field, label)
        for field in (h[329:337], h[337:345]):
            require(octal(field, "device number", empty_ok=True) == 0, "device number nonzero")
        text_field(h[265:297]); text_field(h[297:329])
        size = octal(h[124:136], "member size")
        require(size <= MAX_FILE_BYTES, "tar member size bound")
        name = text_field(h[:100])
        path = tar_path(name, kind)
        link = text_field(h[157:257])
        require((kind == "2" and size == 0 and bool(link)) or (kind != "2" and not link), "tar link form")
        require(kind == "0" or size == 0, "directory/link data forbidden")
        require(path not in seen, "tar duplicate normalized path")
        for i in range(1, len(path.split("/"))):
            ancestor = "/".join(path.split("/")[:i])
            require(ancestor not in seen or seen[ancestor] == "5", "tar file/link ancestor collision")
        if kind != "5":
            require(not any(p.startswith(path + "/") for p in seen), "tar descendant collision")
        seen[path] = kind
        start, end = pos + 512, pos + 512 + size
        padded = start + ((size + 511) // 512) * 512
        require(padded <= len(raw), "tar member truncation")
        require(not any(raw[end:padded]), "tar nonzero member padding")
        body = raw[start:end]
        row = {"name": "." if path == "." else "./" + path, "type": kind, "mode": oct(mode), "bytes": size, "linkname": link}
        if kind == "0":
            row["sha256"] = sha(body)
            bodies[path] = body
        rows.append(row)
        counts[kind] = counts.get(kind, 0) + 1
        pos = padded
    else:
        raise ValueError("tar missing terminator")
    require(len(rows) == framing["raw_headers"] and counts == framing["types"], "tar header/type count pin")
    require(framing["magic8_hex_counts"] == {"7573746172202000": len(rows)}, "tar magic count pin")
    return rows, bodies


def control_identity(raw):
    require(len(raw) <= 65536, "control file bound")
    text = raw.decode("utf-8", "strict")
    fields, current = {}, None
    for line in text.splitlines():
        if line.startswith((" ", "\t")):
            require(current is not None, "control orphan continuation")
            fields[current] += "\n" + line
        elif line:
            key, sep, value = line.partition(":")
            require(sep and re.fullmatch("[A-Za-z0-9-]+", key) and key not in fields, "control field syntax/duplicate")
            fields[key] = value.strip()
            current = key
        else:
            current = None
    return {k: fields.get(k) for k in ("Package", "Version", "Architecture")}


def validate_package(raw, pin):
    exact(raw, pin["deb_bytes"], pin["deb_sha256"], "deb " + pin["package"])
    entries = ar_entries(raw, pin["ar"])
    control = expand_xz(entries["control.tar.xz"], pin["control_framing"]["expanded_bytes"], pin["control_tar_sha256"])
    control_rows, control_bodies = parse_tar(control, pin["control_framing"])
    require("control" in control_bodies, "control member missing")
    require(control_identity(control_bodies["control"]) == pin["control_fields"], "control Package/Version/Architecture pin")
    data = expand_xz(entries["data.tar.xz"], pin["data_tar_bytes"], pin["data_tar_sha256"])
    rows, bodies = parse_tar(data, pin["data_framing"])
    require(rows == pin["members"], "all data member tuples/order pin")
    selected = {}
    indexed = {x["name"]: x for x in rows}
    for item in pin["selected"]:
        path = clean_relative(item["path"])
        require(path not in selected and item["raw_tar_path"] == "./" + path, "selected path duplicate/raw path")
        row = indexed.get(item["raw_tar_path"])
        require(item["kind"] == "regular" and item["tar_type"] == "0", "selected kind pin")
        require(row == {"name": item["raw_tar_path"], "type": "0", "mode": item["mode"], "bytes": item["bytes"], "sha256": item["sha256"], "linkname": ""}, "selected full member pin")
        selected[path] = bodies[path]
    ignored = [{"path": r["name"], "target": r["linkname"], "mode": r["mode"], "materialized": False} for r in rows if r["type"] == "2"]
    return selected, {"package": pin["package"], "deb_sha256": pin["deb_sha256"], "control_tar_sha256": sha(control), "data_tar_sha256": sha(data), "control_identity": pin["control_fields"], "control_members": control_rows, "ignored_links": ignored}


def relocate_cfg(raw):
    exact(raw, CFG_BYTES, CFG_SHA, "original autom4te.cfg")
    lines = raw.splitlines(keepends=True)
    locations = tuple(i + 1 for i, line in enumerate(lines) if line == CFG_OLD)
    require(locations == CFG_LINES and raw.count(CFG_OLD) == 4, "cfg exact four lines")
    require(raw.count(b"--prepend-include '/usr/share/autoconf'") == 4, "cfg literal occurrence count")
    changed = list(lines)
    for line_number in CFG_LINES:
        changed[line_number-1] = CFG_NEW
    derived = b"".join(changed)
    require(derived != raw and derived.count(CFG_NEW) == 4, "cfg replacement accounting")
    exact(derived, CFG_DERIVED_BYTES, CFG_DERIVED_SHA, "derived autom4te.cfg")
    require(derived.replace(CFG_NEW, CFG_OLD) == raw, "cfg inverse projection")
    diff = [{"line": n, "before": CFG_OLD.decode("ascii").rstrip("\n"), "after": CFG_NEW.decode("ascii").rstrip("\n")} for n in CFG_LINES]
    return derived, {"source": CFG_PATH, "source_bytes": len(raw), "source_sha256": sha(raw), "derived": "relocation/autom4te.cfg", "derived_bytes": len(derived), "derived_sha256": sha(derived), "replacements": 4, "line_diff": diff}


def open_absolute_dir(path):
    require(path.startswith("/") and not path.endswith("/"), "absolute directory syntax")
    clean_relative(path[1:])
    fd = os.open("/", DIRECTORY_FLAGS)
    try:
        for part in path[1:].split("/"):
            nxt = os.open(part, DIRECTORY_FLAGS, dir_fd=fd)
            os.close(fd); fd = nxt
        return fd
    except BaseException:
        os.close(fd)
        raise


def state(st):
    return (st.st_dev, st.st_ino, st.st_mode, st.st_nlink, st.st_size, st.st_mtime_ns, st.st_ctime_ns)


def read_fixed_at(parent_fd, name, size, digest):
    require(clean_relative(name) == name and "/" not in name, "input basename")
    fd = os.open(name, READ_FLAGS, dir_fd=parent_fd)
    try:
        before = os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and before.st_size == size, "input regular single-link size")
        chunks, total = [], 0
        while total <= size:
            chunk = os.read(fd, min(65536, size + 1 - total))
            if not chunk: break
            chunks.append(chunk); total += len(chunk)
        raw = b"".join(chunks)
        exact(raw, size, digest, name)
        require(state(os.fstat(fd)) == state(before), "input changed while reading")
        require(state(os.stat(name, dir_fd=parent_fd, follow_symlinks=False)) == state(before), "input path replacement")
        return raw, state(before)
    finally:
        os.close(fd)


class FreshWriter:
    """Descriptor-relative exclusive writes, all files 0600, no archive links."""
    def __init__(self, root):
        require(root == OUTPUT_ROOT, "fixed output root")
        parent, leaf = root.rsplit("/", 1)
        parent_fd = open_absolute_dir(parent)
        try:
            os.mkdir(leaf, 0o700, dir_fd=parent_fd)
            self.fd = os.open(leaf, DIRECTORY_FLAGS, dir_fd=parent_fd)
        finally:
            os.close(parent_fd)
        self.total, self.files = 0, {}

    def write(self, path, raw):
        clean_relative(path)
        require(path not in self.files and len(raw) <= MAX_FILE_BYTES, "writer duplicate/per-file cap")
        require(self.total + len(raw) <= MAX_OUTPUT_BYTES, "writer aggregate cap")
        parts, current = path.split("/"), os.dup(self.fd)
        try:
            for part in parts[:-1]:
                try:
                    os.mkdir(part, 0o700, dir_fd=current)
                except FileExistsError:
                    pass
                nxt = os.open(part, DIRECTORY_FLAGS, dir_fd=current)
                os.close(current); current = nxt
            fd = os.open(parts[-1], os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600, dir_fd=current)
            try:
                offset = 0
                while offset < len(raw):
                    written = os.write(fd, raw[offset:offset+65536])
                    require(written > 0, "short write")
                    offset += written
                os.fsync(fd)
                s = os.fstat(fd)
                require(stat.S_ISREG(s.st_mode) and stat.S_IMODE(s.st_mode) == 0o600 and s.st_nlink == 1 and s.st_size == len(raw), "output inode/mode")
            finally:
                os.close(fd)
            again, _ = read_fixed_at(current, parts[-1], len(raw), sha(raw))
            require(again == raw, "output readback")
        finally:
            os.close(current)
        self.total += len(raw)
        self.files[path] = {"bytes": len(raw), "sha256": sha(raw), "mode": "0o600"}

    def close(self):
        os.close(self.fd)


def load_pins():
    here = str(Path(__file__).absolute().parent)
    fd = open_absolute_dir(here)
    try:
        raw, _ = read_fixed_at(fd, "PINS.json", PINS_BYTES, PINS_SHA256)
    finally:
        os.close(fd)
    p = json_unique(raw)
    require(p["input_root"] == INPUT_ROOT and p["output_root"] == OUTPUT_ROOT, "fixed roots")
    require(p["selected_count"] == SELECTED_COUNT and p["selected_bytes"] == SELECTED_BYTES, "fixed totals")
    require(len(p["packages"]) == 5, "fixed package count")
    return p


def require_actual_review(pins):
    # No caller boolean, environment switch, default acceptance, or fallback.
    review = pins["actual_identity_review"]
    require(isinstance(review, dict), "ACTUAL_IDENTITY_REVIEW_PENDING")
    require(set(review) == {"path", "bytes", "sha256"}, "actual review binding schema")
    parent, leaf = review["path"].rsplit("/", 1)
    fd = open_absolute_dir(parent)
    try:
        raw, _ = read_fixed_at(fd, leaf, review["bytes"], review["sha256"])
        manifest = json_unique(raw)
        require(manifest["schema"] == "FINITE_ACTUAL_ACQUISITION_REVIEW_V1", "actual review schema")
        records = {}
        for name in ("SUMMARY.json", "PACKAGES.json"):
            pin = manifest["files"][name]
            data, _ = read_fixed_at(fd, name, pin["bytes"], pin["sha256"])
            records[name] = json_unique(data)
        summary = records["SUMMARY.json"]
        require(summary["verdict"] == "PASS_ACTUAL_FIVE_OPAQUE_PACKAGE_BYTES_ONLY", "actual identity review verdict")
        require(summary["package_count"] == 5 and summary["package_bytes"] == 2466616, "actual identity review totals")
        require(summary["outer_exit"] == 0 and summary["cleanup_confirmed"] is True and summary["original_sources_and_snapshot_rechecked"] is True, "actual review terminal checks")
        require(summary["unpack_install_source_native_execution"] is False, "actual review scope")
        reviewed = [{"name": p["deb_filename"], "bytes": p["deb_bytes"], "sha256": p["deb_sha256"]} for p in pins["packages"]]
        require([{k: p[k] for k in ("name", "bytes", "sha256")} for p in records["PACKAGES.json"]] == reviewed, "actual review package identity binding")
        return records
    finally:
        os.close(fd)


def stage_fixed():
    """Parent-only actual API. Caller owns finite process limits and alarm.

    No subprocess, shell, native tool, network, package install or chmod here.
    All package/control/data validation precedes fresh output creation.
    Independent SOURCE acceptance and finite parent entrypoint are still required.
    """
    pins = load_pins()
    require_actual_review(pins)
    input_fd = open_absolute_dir(INPUT_ROOT)
    writer = None
    try:
        selected, package_reports, input_states = {}, [], {}
        for pin in pins["packages"]:
            raw, before = read_fixed_at(input_fd, pin["deb_filename"], pin["deb_bytes"], pin["deb_sha256"])
            members, report = validate_package(raw, pin)
            require(not set(selected).intersection(members), "cross-package selected collision")
            selected.update(members); package_reports.append(report)
            input_states[pin["deb_filename"]] = before
        require(len(selected) == SELECTED_COUNT and sum(map(len, selected.values())) == SELECTED_BYTES, "selected aggregate")
        require(sum(len(p["ignored_links"]) for p in package_reports) == 6, "ignored link count")
        derived, relocation = relocate_cfg(selected[CFG_PATH])
        writer = FreshWriter(OUTPUT_ROOT)
        for path, raw in sorted(selected.items()):
            writer.write(path, raw)
        writer.write("relocation/autom4te.cfg", derived)
        for pin in pins["packages"]:
            _, after = read_fixed_at(input_fd, pin["deb_filename"], pin["deb_bytes"], pin["deb_sha256"])
            require(after == input_states[pin["deb_filename"]], "package input changed after staging")
        report = {"status": "STAGING_EVIDENCE_PENDING_PARENT_ACCEPTANCE", "pins_sha256": PINS_SHA256, "selected_count": SELECTED_COUNT, "selected_bytes": SELECTED_BYTES, "files": writer.files.copy(), "packages": package_reports, "relocation": relocation, "all_original_input_stats_and_hashes_unchanged": True, "package_tools_executed": False, "all_output_file_modes": "0o600", "qualification": "NOT_RUN"}
        encoded = (json.dumps(report, indent=2, sort_keys=True) + "\n").encode()
        require(len(encoded) <= MAX_REPORT_BYTES, "report cap")
        writer.write("STAGING_REPORT.json", encoded)
        return {"status": report["status"], "report_sha256": sha(encoded), "report_bytes": len(encoded), "output_files": len(writer.files), "output_bytes": writer.total}
    finally:
        if writer is not None:
            writer.close()
        os.close(input_fd)


if __name__ == "__main__":
    raise SystemExit("SOURCE candidate has no actual CLI; parent-reviewed finite entrypoint required")
