"""Fixed PC01 capsule source-only cold checks; no C++ compilation or execution.

Run through run_cold.py, which size/SHA-pins this exact buffer before compile/exec.
The Python models below test a specification tied to fixed C++ bytes by static
checks. They are not execution, ABI, Verilator, RTL, native-I/O or numerical proof.
The five production sources, three metadata files and 31 pinned repository
members are read once per source-loading pass. Originals are also reconstructed
in memory with reversible PROJECTION hunks; no source or repository is modified.
"""
import ast
import copy
import hashlib
import json
from pathlib import Path
import re
import sys
import unittest

QUALIFICATION = "PYTHON_MOCK_AND_PINNED_STATIC_ONLY_CPP_NOT_COMPILED_OR_EXECUTED"
METADATA_PINS = {
    "PRODUCTION_MANIFEST.json": (911, "e49b1959b50097320daebf2ecbd16eeed3d3e21ebff8d8b3a34346384ce0ff8c"),
    "PROJECTION.json": (9155, "ab485cd055e906a9ad831bb9b8134dadaa28addf7dfdae3c15e88bf50e2d3ad5"),
    "SOURCE_PINS.json": (6547, "868b1b8e5f2ca4b973e0a569e51b13647f2cc84191ccf736b7adcef0a541c1bc"),
}
PREDICATES = (
    "phase_runtime", "n0_published", "qraw_unpublished", "root_nonnull",
    "reset_clear", "reset_required_clear", "context_error_clear", "context_finish_clear",
)
EXPRESSIONS = (
    "owner_.phase_==Phase::Runtime", "owner_.published_", "!owner_.qraw_published_",
    "model_.rootp", "!model_.reset", "!model_.io_resetRequired",
    "!model_.contextp()->gotError()", "!model_.contextp()->gotFinish()",
)
SITES = ("SETTLE_ENTRY", "LOW_EVAL_POST", "RISE_ENTRY", "HIGH_EVAL_POST")
ENUM_SITES = ("SettleEntry", "LowEvalPost", "RiseEntry", "HighEvalPost")
MAX64 = (1 << 64) - 1
MAX32 = (1 << 32) - 1


def demand(condition, message):
    # Never use assert: the same gates and checks must run under python -O.
    if not condition:
        raise RuntimeError(message)


def pin_buffer(data, pin, label):
    size, digest = pin
    demand(isinstance(data, bytes), "pin requires immutable bytes: " + label)
    demand(len(data) == size, "size drift: " + label)
    demand(hashlib.sha256(data).hexdigest() == digest, "SHA256 drift: " + label)
    return data


def load_sources(root):
    metadata = {}
    for name, pin in METADATA_PINS.items():
        raw = (root / name).read_bytes()
        metadata[name] = json.loads(pin_buffer(raw, pin, name).decode("utf-8"))
    manifest = metadata["PRODUCTION_MANIFEST.json"]
    demand(manifest["qualification"] == "SOURCE_ONLY_NOT_COMPILED_OR_EXECUTED", "qualification drift")
    sources = {}
    for name, pin in manifest["sources"].items():
        demand(name.startswith("bridge/") and ".." not in Path(name).parts, "unsafe production member")
        raw = (root / name).read_bytes()
        # Decode exactly the immutable bytes that have just passed size/SHA.
        sources[name] = pin_buffer(raw, (pin["bytes"], pin["sha256"]), name).decode("utf-8")
    demand(len(sources) == 5, "production member count drift")
    return metadata, sources


def load_repo_sources(root, metadata):
    result = {}
    for name, pin in metadata["SOURCE_PINS.json"]["sources"].items():
        demand(not Path(name).is_absolute() and ".." not in Path(name).parts, "unsafe repository member")
        raw = (root / name).read_bytes()
        result[name] = pin_buffer(raw, (pin["bytes"], pin["sha256"]), name).decode("utf-8")
    demand(len(result) == 31, "original repository member count drift")
    return result


def between(text, start, end):
    demand(text.count(start) == 1, "ambiguous start: " + start)
    return text.split(start, 1)[1].split(end, 1)[0]


def strip_space(text):
    return re.sub(r"\s+", "", text)


def reverse_projection(metadata, sources):
    projection = metadata["PROJECTION.json"]
    source_pins = metadata["SOURCE_PINS.json"]["sources"]
    restored = dict(sources)
    changed = set()
    for hunk in reversed(projection["hunks"]):
        name = "bridge/" + hunk["path"]
        demand(restored[name].count(hunk["after"]) == 1, "nonunique reverse hunk: " + name)
        restored[name] = restored[name].replace(hunk["after"], hunk["before"], 1)
        changed.add(name)
    demand(len(changed) == 4, "not exactly four changed originals")
    for name in changed:
        original_name = projection["original_root"] + "/" + name.removeprefix("bridge/")
        pin = source_pins[original_name]
        pin_buffer(restored[name].encode("utf-8"), (pin["bytes"], pin["sha256"]), "reconstructed " + name)
    forward = dict(restored)
    for hunk in projection["hunks"]:
        name = "bridge/" + hunk["path"]
        demand(forward[name].count(hunk["before"]) == 1, "nonunique forward hunk: " + name)
        forward[name] = forward[name].replace(hunk["before"], hunk["after"], 1)
    demand(forward == sources, "projection roundtrip differs")
    return restored, changed


class IdentityFailure(Exception):
    code = "PC1_022"


class Sample:
    def __init__(self):
        self.known_mask = 0
        self.true_mask = 0
        self.first_false = 8

    def probe(self, index, value):
        self.known_mask |= 1 << index
        if value:
            self.true_mask |= 1 << index
        elif self.first_false == 8:
            self.first_false = index
        return bool(value)

    def value(self, index):
        if not self.known_mask & (1 << index):
            return None
        return bool(self.true_mask & (1 << index))


class PoisonRoot:
    def read(self, name):
        raise RuntimeError("invalid root was dereferenced: " + name)


class Root:
    def __init__(self, value=19):
        self.value = value
        self.reads = []

    def read(self, name):
        self.reads.append(name)
        return self.value


class CapsuleModel:
    """Small fixed-scalar model; mutable object freezes its first copied sample."""
    def __init__(self):
        self.present = False
        self.ack0_valid = False
        self.n0_sha256 = bytes(32)
        self.values = {}

    def capture_ack0(self, observed_hash):
        demand(len(observed_hash) == 32, "observed digest must be 32 bytes")
        self.ack0_valid = True
        self.n0_sha256 = bytes(observed_hash)
        self.values.update(ack0s=1, n0_cycles=100, n0_jobs=1, n0_dones=1,
                           n0_committed=786432, n0_b=12288)

    def freeze(self, sample, site, edge, owner_phase, captured_root, current_root,
               captured_context, current_context):
        if self.present:
            return
        self.sample = copy.copy(sample)
        self.site = site
        self.root_valid = captured_root is not None and current_root is captured_root
        self.context_valid = captured_context is not None and current_context is captured_context
        self.values.update(owner_phase=owner_phase, edge=edge)
        if self.root_valid:
            for key in ROOT_KEYS:
                self.values[key] = captured_root.read(key)
        self.present = True


class SchedulerModel:
    def __init__(self, capsule=None):
        self.phase = 3  # Runtime; fixed enum is checked statically.
        self.capsule = capsule or CapsuleModel()
        self.root = Root()
        self.captured_root = self.root
        self.context = object()
        self.captured_context = self.context
        self.calls = []
        self.events = []

    def identity(self, site, values):
        sample = Sample()
        for index in range(8):
            self.calls.append(index)
            value = values(index) if callable(values) else values[index]
            if not sample.probe(index, value):
                self.capsule.freeze(sample, site, 313, self.phase,
                                    self.captured_root, self.root,
                                    self.captured_context, self.context)
                self.events.append("freeze")
                raise IdentityFailure("PC1 actual identity or stopped")
        return sample

    def checked_identity(self, site, values):
        try:
            if self.phase == 4:
                raise RuntimeError("runtime permanently poisoned")
            return self.identity(site, values)
        except Exception:
            self.phase = 4
            self.events.append("poison")
            raise


def bool_text(value):
    return "null" if value is None else "true" if value else "false"


def format_model(capsule, capacity=8192, buffer_present=True):
    """Exact text model using format/order read from the pinned C++ source.

    A zero return models snprintf failure/truncation, not C++ execution.
    """
    if not capsule.present or not buffer_present or capacity == 0:
        return b""
    sample = capsule.sample
    values = (capsule.site, sample.known_mask, sample.true_mask, sample.first_false,
              bool_text(capsule.root_valid), bool_text(capsule.context_valid),
              bool_text(capsule.ack0_valid)) + tuple(bool_text(sample.value(i)) for i in range(8))
    text = PREFIX_FORMAT % values
    for key, field, validity in NUMBER_FIELDS:
        valid = not validity or getattr(capsule, validity)
        text += ',"' + key + '":' + (str(capsule.values.get(field, 0)) if valid else "null")
    text += ',"n0_sha256":' + ('"' + capsule.n0_sha256.hex() + '"' if capsule.ack0_valid else "null")
    text += SUFFIX_FORMAT
    raw = text.encode("ascii")
    return raw if len(raw) < capacity else b""  # room for the C terminator


class MockIO:
    def __init__(self, save_ok=True, write_ok=True, flush_ok=True):
        self.save_ok, self.write_ok, self.flush_ok = save_ok, write_ok, flush_ok
        self.saved = []
        self.writes = []
        self.flushes = 0

    def save(self, data):
        self.saved.append(data)
        return self.save_ok

    def write(self, data):
        self.writes.append(data)
        return len(data) if self.write_ok else 0

    def flush(self):
        self.flushes += 1
        return 0 if self.flush_ok else -1


def emit_model(capsule, stream, capacity=8192):
    if not capsule.present or stream is None:
        return
    data = format_model(capsule, capacity)
    if data:
        stream.write(data)  # C fwrite/fflush error results deliberately ignored.
        stream.flush()


def terminal_model(capsule, io, code="PC1_022", exit_code=1, capacity=8192):
    # Model false/short-write/EOF results, not invented exceptions from C stdio.
    terminal = {"status": "CONTRACT_ERROR", "code": code, "numeric_comparison": "NOT_RUN"}
    io.save(terminal)
    emit_model(capsule, io, capacity)
    return terminal, exit_code


def failed_scheduler(index=7, site="SETTLE_ENTRY"):
    scheduler = SchedulerModel()
    if index == 0:
        scheduler.phase = 2
    if index == 3:
        scheduler.root = None
    try:
        scheduler.checked_identity(site, [i != index for i in range(8)])
    except IdentityFailure:
        return scheduler
    raise RuntimeError("injected failure was not observed")


class ColdTests(unittest.TestCase):
    def test_all_fixed_bytes_and_reversible_originals(self):
        self.assertEqual(len(CHANGED), 4)
        self.assertEqual(set(SOURCES) - CHANGED, {"bridge/include/pc01_failure_capsule.hpp"})
        self.assertEqual(METADATA["SOURCE_PINS.json"]["unchanged_original_members"], 24)
        self.assertEqual(METADATA["SOURCE_PINS.json"]["future_assembled_members"], 29)

    def test_31_original_repository_members_samebuffer_pinned(self):
        self.assertEqual(len(REPO_SOURCES), 31)
        base = METADATA["PROJECTION.json"]["original_root"] + "/"
        for member in CHANGED:
            self.assertEqual(ORIGINALS[member], REPO_SOURCES[base + member.removeprefix("bridge/")])

    def test_no_new_snapshot_internal_fields(self):
        base = METADATA["PROJECTION.json"]["original_root"] + "/include/"
        registry = REPO_SOURCES[base + "n0_field_registry.inc"] + "\n" + REPO_SOURCES[base + "generated_binding.hpp"]
        registered = tuple(re.findall(r"registered\([^;]+;", registry))
        direct_fields = re.findall(r"=r\.([A-Za-z_0-9]+);", FREEZE)
        self.assertEqual(len(direct_fields), 23)
        self.assertEqual(len(set(direct_fields)), 23)
        for field in direct_fields:
            self.assertTrue(any(re.search(r"&r\." + re.escape(field) + r"\b", call) for call in registered), field)
        public_fields = re.findall(r"=model_\.([A-Za-z_0-9]+);", FREEZE)
        self.assertEqual(len(public_fields), 8)
        original_use = ORIGINALS["bridge/include/pc01_driver.hpp"] + ORIGINALS["bridge/include/pc1_model_scheduler.inc"]
        for field in public_fields:
            self.assertRegex(original_use, r"model_?\." + re.escape(field) + r"\b")

    def test_pin_rejects_same_size_mutation_and_size_drift(self):
        raw = b"abc"
        pin = (3, hashlib.sha256(raw).hexdigest())
        self.assertIs(pin_buffer(raw, pin, "positive"), raw)
        for bad in (b"abd", b"abcx"):
            with self.assertRaises(RuntimeError):
                pin_buffer(bad, pin, "negative")

    def test_original_eight_expressions_order_and_guard_are_identical(self):
        old = between(ORIGINALS["bridge/include/pc1_model_scheduler.inc"], "void identity()const {", "        void exact_job")
        old_expr = old.split("require(", 1)[1].split(',"PC1 actual identity or stopped"', 1)[0]
        self.assertEqual(strip_space(old_expr), "&&".join(EXPRESSIONS))
        new = between(SCHEDULER, "void identity(Pc01IdentitySite site,std::uint64_t edge)const {", "        void exact_job")
        expr = between(new, "const bool ok=", ";")
        expected = "&&".join("sample.probe(%d,%s)" % (i, e) for i, e in enumerate(EXPRESSIONS))
        self.assertEqual(strip_space(expr), expected)
        self.assertIn('require(ok,"PC1 actual identity or stopped");', new)
        self.assertLess(new.index("freeze_identity(sample,site,edge)"), new.index("require(ok"))
        # Both original context dereferences remain unguarded as in the source;
        # context-validity is diagnostic metadata, not an added identity guard.
        self.assertNotIn("context_valid", new)

    def test_sample_logic_and_validity_static(self):
        for token in (
            "unsigned known_mask=0, true_mask=0, first_false=8;",
            "known_mask|=1U<<index;if(value)true_mask|=1U<<index;else if(first_false==8)first_false=index;",
            'return !(known_mask&(1U<<index))?"null":(true_mask&(1U<<index))?"true":"false";',
            "std::array<std::uint8_t,32> n0_sha256{};",
        ):
            self.assertIn(token, HEADER)
        for enum_site, name in zip(ENUM_SITES, SITES):
            self.assertIn('case Pc01IdentitySite::%s:return "%s";' % (enum_site, name), HEADER)
        self.assertIn("d.root_valid=diagnostic_root_&&model_.rootp==diagnostic_root_;", FREEZE)
        self.assertIn("d.context_valid=diagnostic_context_&&model_.contextp()==diagnostic_context_;", FREEZE)
        assigned = set(re.findall(r"d\.([a-z0-9_]+)=", between(FREEZE, "if(d.root_valid) {", "            }")))
        self.assertEqual(assigned, set(ROOT_KEYS))

    def test_four_call_sites_and_unchanged_guard(self):
        sites = re.findall(r"identity\(Pc01IdentitySite::(\w+),edge\)", SCHEDULER)
        self.assertEqual(tuple(sites), ENUM_SITES)
        for token in (
            "owner_.checked([&]{identity(Pc01IdentitySite::SettleEntry,edge);require(!pending_",
            "model_.clock=0;model_.eval();identity(Pc01IdentitySite::LowEvalPost,edge);pre_=",
            "owner_.checked([&]{identity(Pc01IdentitySite::RiseEntry,edge);require(pending_",
            "model_.clock=1;model_.eval();identity(Pc01IdentitySite::HighEvalPost,edge);unchanged_inputs(true);",
        ):
            self.assertIn(token, SCHEDULER)
        for token in ("guard_.before_rising(edge,job_seen_&&!done_seen_);", "guard_.after_rising(edge);"):
            self.assertIn(token, SCHEDULER)
            self.assertIn(token, ORIGINALS["bridge/include/pc1_model_scheduler.inc"])

    def test_freeze_copy_before_poison_static(self):
        self.assertIn("enum class Phase { Filling, TokenIssued, InputView, Runtime, Poisoned };", RUNTIME)
        self.assertIn("catch(...) {phase_=Phase::Poisoned;throw;}", RUNTIME)
        self.assertIn("if(diagnostic_.present)return;", FREEZE)
        self.assertLess(FREEZE.index("if(diagnostic_.present)return;"), FREEZE.index("d.predicates=sample"))
        self.assertLess(FREEZE.index("d.predicates=sample"), FREEZE.index("d.present=true;"))
        self.assertIn("const auto& r=*diagnostic_root_;", FREEZE)
        guarded = between(FREEZE, "if(d.root_valid) {", "            }")
        self.assertIn("const auto& r=*diagnostic_root_;", guarded)
        self.assertEqual(FREEZE.count("*diagnostic_root_"), 1)
        self.assertNotIn("diagnostic_context_->", FREEZE)
        self.assertNotIn("fields_.read", FREEZE)
        self.assertNotIn("guard_.", FREEZE)

    def test_first_snapshot_immutable_after_all_later_sites(self):
        scheduler = failed_scheduler(5)
        before = copy.deepcopy(scheduler.capsule.__dict__)
        for site in SITES:
            with self.assertRaises(IdentityFailure):
                scheduler.identity(site, [False] * 8)
        self.assertEqual(scheduler.capsule.__dict__["values"], before["values"])
        self.assertEqual(scheduler.capsule.sample.__dict__, before["sample"].__dict__)
        self.assertEqual(scheduler.capsule.site, before["site"])
        self.assertEqual(scheduler.capsule.values["owner_phase"], 3)
        self.assertEqual(scheduler.phase, 4)
        self.assertEqual(scheduler.events[:2], ["freeze", "poison"])

    def test_sample_is_value_copy(self):
        scheduler = SchedulerModel()
        sample = Sample()
        sample.probe(0, False)
        scheduler.capsule.freeze(sample, SITES[0], 2, 3, scheduler.root, scheduler.root,
                                 scheduler.context, scheduler.context)
        sample.probe(7, True)
        self.assertEqual(scheduler.capsule.sample.known_mask, 1)
        self.assertIsNone(scheduler.capsule.sample.value(7))

    def test_success_and_nonidentity_failure_have_no_capsule(self):
        scheduler = SchedulerModel()
        scheduler.capsule.capture_ack0(bytes(range(32)))
        for site in SITES:
            sample = scheduler.checked_identity(site, [True] * 8)
            self.assertEqual(sample.known_mask, 255)
            self.assertEqual(sample.true_mask, 255)
            self.assertEqual(sample.first_false, 8)
        self.assertFalse(scheduler.capsule.present)
        self.assertEqual(format_model(scheduler.capsule), b"")
        io = MockIO()
        emit_model(scheduler.capsule, io)
        self.assertEqual((io.writes, io.flushes), ([], 0))
        scheduler.phase = 4
        with self.assertRaises(RuntimeError):
            scheduler.checked_identity(SITES[0], [True] * 8)
        self.assertFalse(scheduler.capsule.present)

    def test_root_context_validity_cross_product_without_invalid_deref(self):
        for root_valid in (False, True):
            for context_valid in (False, True):
                scheduler = SchedulerModel()
                if not root_valid:
                    scheduler.captured_root = PoisonRoot()
                    scheduler.root = None
                if not context_valid:
                    scheduler.context = None
                with self.assertRaises(IdentityFailure):
                    scheduler.checked_identity(SITES[0], [False] + [True] * 7)
                data = json.loads(format_model(scheduler.capsule))
                self.assertEqual(data["root_valid"], root_valid)
                self.assertEqual(data["context_valid"], context_valid)
                for key in ROOT_KEYS:
                    self.assertEqual(data[key], 19 if root_valid else None)
        # A changed non-null root and a missing captured root are also invalid.
        for captured, current in ((PoisonRoot(), Root()), (None, Root()), (None, None)):
            capsule = CapsuleModel()
            sample = Sample()
            sample.probe(0, False)
            capsule.freeze(sample, SITES[0], 0, 0, captured, current, None, None)
            self.assertFalse(capsule.root_valid)
            self.assertFalse(capsule.context_valid)

    def test_ack0_observed_hash_is_never_reference_comparison(self):
        scheduler = SchedulerModel()
        digest = bytes(range(32))
        scheduler.capsule.capture_ack0(digest)
        with self.assertRaises(IdentityFailure):
            scheduler.checked_identity(SITES[0], [True] * 7 + [False])
        data = json.loads(format_model(scheduler.capsule))
        self.assertEqual(data["n0_sha256"], digest.hex())
        self.assertEqual(data["ack0s"], 1)
        self.assertEqual(data["numeric_comparison"], "NOT_RUN")
        self.assertIsNone(data["root_cause"])
        self.assertIn("diagnostic.n0_sha256=result.actual_sha256;diagnostic.ack0_valid=true;", DRIVER)
        self.assertLess(DRIVER.index("diagnostic.ack0_valid=true;"), DRIVER.index("Pc1ModelScheduler pc1"))
        self.assertNotIn("reference", data)
        # Existing same-RAM integrity rehash is not mathematical/reference equality.
        self.assertIn('"PC1 same-RAM N0 changed after ACK0"', DRIVER)
        self.assertNotIn("==", between(DRIVER, "// Pre-PC1 provenance only;", "// Original N0 scheduler"))

    def test_ack0_unknown_is_null(self):
        data = json.loads(format_model(failed_scheduler().capsule))
        self.assertFalse(data["ack0_valid"])
        self.assertIsNone(data["n0_sha256"])
        for key, _, validity in NUMBER_FIELDS:
            if validity == "ack0_valid":
                self.assertIsNone(data[key])

    def test_save_and_emit_failures_keep_original_code_and_exit(self):
        capsule = failed_scheduler().capsule
        for save_ok in (False, True):
            for write_ok in (False, True):
                for flush_ok in (False, True):
                    io = MockIO(save_ok, write_ok, flush_ok)
                    terminal, exit_code = terminal_model(capsule, io)
                    self.assertEqual(terminal["code"], "PC1_022")
                    self.assertEqual(exit_code, 1)
                    self.assertEqual(len(io.saved), 1)
                    self.assertEqual(len(io.writes), 1)
                    self.assertEqual(io.flushes, 1)
        io = MockIO(False, False, False)
        terminal, exit_code = terminal_model(capsule, io, capacity=8)
        self.assertEqual((terminal["code"], exit_code), ("PC1_022", 1))
        self.assertEqual((io.writes, io.flushes), ([], 0))
        terminal = between(MAIN, "auto terminal=[&]", "    if(argc!=3)")
        self.assertIn('if(output_fd>=0)first_n0::exclusive_write(output_fd,"counts.json",text.data(),static_cast<std::size_t>(size));', terminal)
        self.assertIn("diagnostic.emit_noexcept(stdout);return exit_code;", terminal)
        self.assertIn('return terminal("CONTRACT_ERROR",exact_exception_code(error.what()),1);', MAIN)
        self.assertIn("void emit_noexcept(std::FILE* stream)const noexcept", HEADER)
        self.assertIn("(void)std::fwrite", HEADER)
        self.assertIn("(void)std::fflush", HEADER)

    def test_bounded_format_worst_case_and_every_capacity(self):
        capsule = failed_scheduler().capsule
        capsule.capture_ack0(bytes([255]) * 32)
        capsule.sample.known_mask = MAX32
        capsule.sample.true_mask = MAX32
        capsule.sample.first_false = MAX32
        capsule.root_valid = capsule.context_valid = capsule.ack0_valid = True
        capsule.values = {field: MAX64 for _, field, _ in NUMBER_FIELDS}
        capsule.site = max(SITES + ("UNKNOWN",), key=len)
        raw = format_model(capsule)
        self.assertTrue(raw.endswith(b"}\n"))
        self.assertLess(len(raw) + 1, 8192)
        self.assertEqual(len(raw), WORST_FORMAT_BYTES)
        parsed = json.loads(raw)
        self.assertEqual(parsed["matrix_poison"], MAX64)
        for capacity in range(len(raw) + 1):
            self.assertEqual(format_model(capsule, capacity), b"")
        self.assertEqual(format_model(capsule, len(raw) + 1), raw)
        self.assertEqual(format_model(capsule, 8192, False), b"")
        io = MockIO()
        emit_model(capsule, io, capacity=8)
        self.assertEqual((io.writes, io.flushes), ([], 0))
        emit_model(capsule, None)
        self.assertIn("std::array<char,8192> text{};", HEADER)
        self.assertIn("std::size_t(n)>=capacity-used", HEADER)
        self.assertIn("return ok?used:0;", HEADER)
        self.assertIn('static_assert(sizeof(Pc01FailureCapsule)<=1024,"bounded scalar snapshot storage");', HEADER)

    def test_format_fields_fixed_and_no_sensitive_payload(self):
        self.assertEqual(tuple(PREFIX_PREDICATE_KEYS), PREDICATES)
        self.assertEqual(len(NUMBER_FIELDS), 50)
        self.assertEqual(len(ROOT_KEYS), 31)
        self.assertEqual(len({field for _, field, _ in NUMBER_FIELDS}), 50)
        data = json.loads(format_model(failed_scheduler().capsule))
        for prohibited in ("path", "pointer", "exception", "tensor", "raw_values"):
            self.assertFalse(any(prohibited in key for key in data))
        self.assertEqual(data["code"], "PC1_022")
        self.assertEqual(data["sample_time"], "BEFORE_IDENTITY_REQUIRE_AND_CHECKED_POISON")


def make_failure_case(index, site):
    def test(self):
        scheduler = SchedulerModel()
        if index == 0:
            scheduler.phase = 2
        if index == 3:
            scheduler.root = None
        def values(position):
            if position > index:
                raise RuntimeError("short circuit incorrectly observed a later predicate")
            return position != index
        with self.assertRaisesRegex(IdentityFailure, "^PC1 actual identity or stopped$"):
            scheduler.checked_identity(site, values)
        capsule = scheduler.capsule
        self.assertTrue(capsule.present)
        self.assertEqual(scheduler.calls, list(range(index + 1)))
        self.assertEqual(capsule.sample.known_mask, (1 << (index + 1)) - 1)
        self.assertEqual(capsule.sample.true_mask, (1 << index) - 1)
        self.assertEqual(capsule.sample.first_false, index)
        self.assertEqual(capsule.site, site)
        self.assertEqual(capsule.values["owner_phase"], 2 if index == 0 else 3)
        self.assertEqual(capsule.root_valid, index != 3)
        self.assertEqual(scheduler.phase, 4)
        self.assertEqual(scheduler.events, ["freeze", "poison"])
        data = json.loads(format_model(capsule))
        self.assertEqual(data["site"], site)
        self.assertEqual(data["predicates"], {
            name: True if i < index else False if i == index else None
            for i, name in enumerate(PREDICATES)
        })
    return test


# Entrypoint-controlled bytes are required; direct path execution is unsupported.
demand(globals().get("_PINNED_TEST_BUFFER") is not None,
       "Use run_cold.py: this test must be size/SHA-pinned before Python compile/exec")
pin_buffer(_PINNED_TEST_BUFFER, _PINNED_TEST_PIN, "executed test buffer")
ROOT = Path(_PINNED_ROOT)
METADATA, SOURCES = load_sources(ROOT)
REPO_SOURCES = load_repo_sources(Path(_PINNED_REPO), METADATA)
ORIGINALS, CHANGED = reverse_projection(METADATA, SOURCES)
HEADER = SOURCES["bridge/include/pc01_failure_capsule.hpp"]
SCHEDULER = SOURCES["bridge/include/pc1_model_scheduler.inc"]
RUNTIME = SOURCES["bridge/include/runtime_ram.hpp"]
DRIVER = SOURCES["bridge/include/pc01_driver.hpp"]
MAIN = SOURCES["bridge/source/pc01_main.cpp"]
FREEZE = between(SCHEDULER, "void freeze_identity(", "        void identity(")
NUMBER_FIELDS = tuple((m.group(1), m.group(2), m.group(3) or "") for m in re.finditer(
    r'number\("([a-z0-9_]+)",([a-z0-9_]+)(?:,(ack0_valid|root_valid))?\);', HEADER))
ROOT_KEYS = tuple(field for _, field, validity in NUMBER_FIELDS if validity == "root_valid")
format_source = between(HEADER, '        append("{', "               site_name(site),")
literals = re.findall(r'"(?:\\.|[^"\\])*"', '"{' + format_source)
PREFIX_FORMAT = "".join(ast.literal_eval(token) for token in literals)
SUFFIX_FORMAT = ',"numeric_comparison":"NOT_RUN","root_cause":null}\n'
PREFIX_PREDICATE_KEYS = re.findall(r'"([a-z0-9_]+)":%s', PREFIX_FORMAT.split('"predicates":{')[1])
demand('append(",\\"numeric_comparison\\":\\"NOT_RUN\\",\\"root_cause\\":null}\\n");' in HEADER,
       "suffix drift")
# 50 uint64 scalar fields, uint32 metadata, full digest, longest fixed site.
_worst = failed_scheduler().capsule
_worst.capture_ack0(bytes([255]) * 32)
_worst.sample.known_mask = _worst.sample.true_mask = _worst.sample.first_false = MAX32
_worst.root_valid = _worst.context_valid = _worst.ack0_valid = True
_worst.site = max(SITES + ("UNKNOWN",), key=len)
_worst.values = {field: MAX64 for _, field, _ in NUMBER_FIELDS}
WORST_FORMAT_BYTES = 2330  # independently frozen expected byte count for this exact schema
demand(len(format_model(_worst)) == WORST_FORMAT_BYTES, "worst-case format size drift")
for _site in SITES:
    for _index in range(8):
        setattr(ColdTests, "test_first_failure_%s_%d" % (_site.lower(), _index), make_failure_case(_index, _site))


def run():
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(ColdTests)
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    print(json.dumps({"qualification": QUALIFICATION, "tests": result.testsRun,
                      "failures": len(result.failures), "errors": len(result.errors),
                      "source_files_pinned": 5, "metadata_files_pinned": 3,
                      "repository_files_pinned": 31, "new_internal_fields": 0,
                      "original_files_reconstructed_and_pinned": 4,
                      "predicate_site_cases": 32, "worst_format_bytes": WORST_FORMAT_BYTES,
                      "emit_capacity": 8192, "python_optimized": bool(sys.flags.optimize)},
                     sort_keys=True))
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(run())
