"""Pure, unexecuted iDMA build description. No IO, acquisition or executor API.

The caller must read and hash the catalog once, parse those same bytes, and pass
the resulting object. Historical byte pins describe prior local observations;
they do not qualify a reconstruction in a new toolchain or working directory.
"""
import copy
import hashlib
import json
import re
from pathlib import PurePosixPath

CATALOG_SHA256 = "6e42a0cc0b03d0010d40b8dcea4fb1f48597fb8e297ee2aae1e6571e3eda2d36"
CANONICAL_SHA256 = "8b0b9a61464cb67e5fb8c85b33c77e5f9996a4a690122fc49895dee7c288bb12"
PREFIX = "candidates/chisel_hybrid_host_20261106/native"
RECIPE = PREFIX + "/build_recipe"
DESCRIPTION_SHA256 = "10b900c3490f8e22c36c28f0451498fe3807b44f56b70c8bc20f76d73365efde"


def need(value, message):
    if not value:
        raise ValueError(message)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def relative(path):
    need(isinstance(path, str) and path != "" and "\\" not in path, "relative path type")
    p = PurePosixPath(path)
    need(not p.is_absolute() and str(p) == path and all(x not in ("", ".", "..") for x in p.parts), "canonical relative path")
    return path


def validate(catalog):
    need(type(catalog) is dict, "catalog object")
    need(hashlib.sha256(canonical(catalog)).hexdigest() == CANONICAL_SHA256, "exact source catalog identity")
    need(catalog["schema"] == "IDMA_PORTABLE_SOURCE_CONTRACT_V1", "catalog schema")
    units = catalog["ordered_rtl_units"]
    need(len(units) == 296 and len(catalog["include_headers"]) == 18, "exact source closure")
    names = []
    for row in units + catalog["include_headers"]:
        path = row.get("repository", row.get("path"))
        relative(path)
        need(re.fullmatch(r"[0-9a-f]{64}", row["sha256"]) is not None, "source digest")
        need(type(row["bytes"]) is int and row["bytes"] > 0, "source byte length")
    for row in units:
        names.append(PurePosixPath(row.get("repository", row.get("path"))).name)
    need(len(names) == len(set(names)), "duplicate unit basename")
    need(sum(r.get("artifact") == "idma_export" for r in units) == 294, "original export unit count")
    need(units[-2]["artifact"] == "tc_clk" and units[-1]["repository"] == "rtl/integration/idma_backend_rw_axi_flat_wrap.sv", "original ordered tail")
    need(catalog["defines"] == ["TARGET_ASIC", "TARGET_RTL", "TARGET_SYNTHESIS", "TARGET_VERILATOR"], "original defines")
    need(len(catalog["include_directories"]) == 8, "original include order")
    need(len(catalog["leaf_warning_sites"]) == 28 and len(catalog["adapter_warning_sites"]) == 145, "finite diagnostic source catalog")
    need(catalog["adapter_parameters"] == dict(maxBeats=16, streaming=True, streamCutThrough=True, burstWrites=True, commitTailRead=False), "original adapter parameters")
    need(len(catalog["native_sources"]) == 6, "exact six published native sources")
    need("/workspace/" not in canonical(catalog).decode() and "/home/" not in canonical(catalog).decode(), "private path excluded")
    return {"status": "PASS_SOURCE_CONTRACT_ONLY", "ordered_units": 296, "include_headers": 18, "execution_authority": False}


def unit_path(row):
    if "repository" in row:
        return "{repo}/" + row["repository"]
    if row["artifact"] in ("tc_clk", "adapter_sv"):
        return "{artifact:" + row["artifact"] + "}"
    return "{artifact:" + row["artifact"] + "}/" + row["path"]


def render_filelist(catalog):
    """Return text only; never create a file or resolve a tool/artifact path."""
    validate(catalog)
    lines = ["+define+" + x for x in catalog["defines"]]
    lines += ["+incdir+{artifact:idma_export}/" + x for x in catalog["include_directories"]]
    lines += [unit_path(x) for x in catalog["ordered_rtl_units"]]
    return "\n".join(lines) + "\n"


def describe(catalog):
    validate(catalog)
    native = "{repo}/" + PREFIX + "/idma/"
    recipe = "{repo}/" + RECIPE + "/"
    vr = "{artifact:verilator_root}"
    leaf = "{build}/idma/leaf_obj"
    adapter = "{build}/idma/adapter_obj"
    stages = []

    def stage(name, cwd, argv, inputs, outputs, conditions):
        stages.append(dict(id="idma_" + name, cwd=cwd, argv=argv, inputs=inputs, outputs=outputs,
                           preconditions=conditions, unexecuted=True))

    common = ["No execution authority from this description; separate bounded operational admission required.",
              "Exact tool/helper/ELF/include/runtime closure verified before use, sanitized environment, one compiler job.",
              "Substitute only declared approved roots, with no shell evaluation or whitespace/control characters in filelist roots; other escaping needs separate review.",
              "No RTL changes, no settle/convergence limit changes, no source or clock-scheduling substitution."]
    diagnostic = ["Portable full ordered diagnostic-byte gate is unresolved. Site counts alone never authorize -Wno-fatal.",
                  "Require native exit zero, no unexpected diagnostic byte, preserved complete output and strict cleanup before compile."]
    for kind, directory, top, prefix, extra, count in (
        ("leaf", leaf, "idma_backend_rw_axi_flat_wrap", "Vidma_backend_rw_axi_flat_wrap", [], 28),
        ("adapter", adapter, "OriginalIdmaAdapterProbe", "VOriginalIdmaAdapterProbe", ["{artifact:adapter_sv}"], 145),
    ):
        if kind == "adapter":
            stage("emit_adapter", "{build}/idma/adapter_emission",
                  ["{tool:java}", "-XX:-UsePerfData", "-XX:ActiveProcessorCount=1", "-XX:ReservedCodeCacheSize=128m",
                   "-XX:-HeapDumpOnOutOfMemoryError", "-XX:ErrorFile=/dev/null", "-Xss4m", "-Xmx1g", "-cp",
                   "{artifact:adapter_emitter_classpath}", catalog["adapter_emission_main"], "rtl"],
                  ["idma_original_emitter_sources", "idma_original_emitter_classes", "idma_original162_and_helpers"],
                  ["idma_adapter_sv"], common + ["Blocked: exact original emitter sources/classes/Maven closure are not supplied by the six-native-file bundle.",
                  "Preserve original maxBeats16/streaming/cut-through/burstWrites/commitTailRead=false configuration and verify high/Ext/low identity. Source-location differences require review, not normalization."])
        stage("generate_" + kind, "{build}/idma/" + kind + "_generation",
              ["{tool:verilator_bin}", "--cc", "--Mdir", directory, "--top-module", top,
               "--prefix", prefix, "-CFLAGS", "-fPIC", "-f", "{artifact:idma_filelist}"] + extra + ["-Wno-fatal"],
              ["idma_296_rtl_units", "idma_18_headers", "idma_filelist"] + (["idma_adapter_sv"] if extra else []),
              ["idma_" + kind + "_generated"], common + diagnostic + ["Set VERILATOR_ROOT to the exact declared matching runtime; inherit 8 MiB stack.", "Prior diagnostic site count " + str(count) + "; no blanket warning suppression."])
        mk = "idma_without_pch.mk" if kind == "leaf" else "adapter_without_pch.mk"
        stage("archive_" + kind, "{build}/idma/" + kind + "_archive",
              ["{tool:make}", "--silent", "-C", directory, "-f", recipe + mk, "-j1",
               "CXX={tool:cxx}", "LINK={tool:cxx}", "AR={tool:ar}", "RANLIB={tool:ranlib}",
               "PERL={tool:perl}", "PYTHON3={tool:python} -I -S -B", "OBJCACHE=", "OPT_FAST=-O1", "OPT_SLOW=-O1",
               prefix + "__ALL.a", "SHELL={tool:shell}", "RM={tool:rm}"],
              ["idma_" + kind + "_generated", "idma_" + kind + "_no_pch", "idma_" + kind + "_syntax_status", "idma_verilator_runtime"], ["idma_" + kind + "_archive"],
              common + ["Preserve generated include/make/compiler semantics. No-PCH removes only precompiled-header prerequisites/forced includes; original header content remains included.",
                        "The generated makefile dispatches uname/cat/xargs/rm/ar and verilator_includer; each executable/interpreter/helper must be qualified."])

    def includes(directory):
        return ["-I" + directory, "-I" + vr + "/include", "-I" + vr + "/include/vltstd"]
    stage("syntax_leaf", "{build}/idma/leaf_syntax", ["{tool:cxx}", "-std=c++17", "-fsyntax-only"] + includes(leaf) + [native + "abi_checks.cpp"],
          ["idma_leaf_generated", "idma_native_sources", "idma_verilator_runtime"], ["idma_leaf_syntax_status"], common + ["Syntax-only; no object, link or model loading. Require zero diagnostics."])
    stage("syntax_adapter", "{build}/idma/adapter_syntax", ["{tool:cxx}", "-std=c++17", "-fsyntax-only"] + includes(adapter) + [native + "adapter_abi_checks.cpp", native + "original_adapter_rtl_frame_endpoint.cpp"],
          ["idma_adapter_generated", "idma_native_sources", "idma_verilator_runtime"], ["idma_adapter_syntax_status"], common + ["All82 generated storage assertions; syntax-only and zero diagnostics."])
    for name, directory, source, archive, output, shared in (
        ("cabi_library", leaf, "retained_idma_leaf.cpp", "Vidma_backend_rw_axi_flat_wrap__ALL.a", "libretained_idma.so", True),
        ("direct_executable", leaf, "direct_trace.cpp", "Vidma_backend_rw_axi_flat_wrap__ALL.a", "idma_direct_trace", False),
        ("adapter_endpoint", adapter, "original_adapter_rtl_frame_endpoint.cpp", "VOriginalIdmaAdapterProbe__ALL.a", "original_adapter_rtl_frame_endpoint", False),
    ):
        argv = ["{tool:cxx}", "-std=c++17", "-O1", "-fPIC", "-pthread"] + includes(directory)
        if shared:
            argv += ["-shared", "-Wl,-z,defs"]
        argv += [native + source, directory + "/" + archive, vr + "/include/verilated.cpp", vr + "/include/verilated_threads.cpp", "-o", "{build}/idma/bin/" + output]
        stage("link_" + name, "{build}/idma/link_" + name, argv,
              ["idma_native_sources", "idma_adapter_archive" if directory == adapter else "idma_leaf_archive", "idma_verilator_runtime"],
              ["idma_" + name], common + ["No RPATH/RUNPATH flags are present in accepted iDMA link argv; do not invent an absolute path or silently change loader policy.",
              "No executable/library load. Inspect actual ELF dependency paths and symbols separately before any future runtime."])

    inputs = [{"path": PREFIX + "/" + x["path"], "sha256": x["sha256"], "role": "idma_native_" + PurePosixPath(x["path"]).name.replace(".", "_")} for x in catalog["native_sources"]]
    inputs += [{"path": RECIPE + "/" + x["path"], "sha256": x["sha256"], "role": "idma_leaf_no_pch" if x["path"].startswith("idma_") else "idma_adapter_no_pch"} for x in catalog["no_pch_fragments"]]
    inputs += [{"path": "rtl/integration/idma_backend_rw_axi_flat_wrap.sv", "sha256": catalog["ordered_rtl_units"][-1]["sha256"], "role": "idma_original_wrapper"},
               {"path": PREFIX + "/SOURCES.json", "sha256": catalog["published_native_map_sha256"], "role": "idma_published_native_map"},
               {"path": RECIPE + "/idma_source_contract.json", "sha256": CATALOG_SHA256, "role": "idma_source_contract"}]
    result = dict(schema="PORTABLE_NATIVE_RECIPE_FRAGMENT_V1", component="idma", status="UNRUN_PORTABLE_BUILD_RECIPE",
                  repository_commit=catalog["repository_commit"], inputs=inputs, tools=copy.deepcopy(catalog["tools"]), stages=stages,
                  aggregate_roles={"idma_native_sources": [row["role"] for row in inputs[:6]]},
                  prerequisite_roles={
                    "idma_296_rtl_units": {"status": "UNRESOLVED", "description": "Exact ordered 294 export units, tc_clk and repository wrapper from the source contract; hashes alone do not provide their bytes."},
                    "idma_18_headers": {"status": "UNRESOLVED", "description": "Exact 18 provider include headers from the source contract."},
                    "idma_filelist": {"status": "UNRESOLVED", "description": "Verified render_filelist text with reviewed root substitutions; no file is created by this module."},
                    "idma_original_emitter_sources": {"status": "UNRESOLVED", "description": "Original Scala emitter/helper source closure and source-info identity, not a behavioral provider."},
                    "idma_original_emitter_classes": {"status": "UNRESOLVED", "description": "Exact 13 original emitter classes, separately built and qualified from the selected sources."},
                    "idma_original162_and_helpers": {"status": "UNRESOLVED", "description": "Original 162-class closure, graph/modulecache helpers and ordered Maven inputs."},
                    "idma_verilator_runtime": {"status": "UNRESOLVED", "description": "Matching complete Verilator include/make/runtime/helper closure; selected historical hashes are not complete acquisition or qualification."}},
                  artifacts={
                    "idma_export": {"status": "UNRESOLVED_RECONSTRUCTION", "role": "Original294 RTL units plus18 headers, full927-member source-manifest verification required", "existing_repository_route": catalog["provider_export"]},
                    "tc_clk": {"status": "UNRESOLVED_PROVIDER_ROLE", "role": "Exact original tc_clk.sv from separately pinned Matrix provider reconstruction", "sha256": catalog["ordered_rtl_units"][-2]["sha256"]},
                    "verilator_root": {"status": "UNRESOLVED_TOOL_INSTALLATION", "role": "Matching pinned Verilator runtime, include tree, makefile and includer", "selected_identity_rows": copy.deepcopy(catalog["verilator_runtime"])},
                    "qualified_tool_path": {"status": "UNRESOLVED_TOOL_SEARCH_PATH", "role": "Sanitized PATH resolving every implicit make helper to its verified byte identity; historical PATH was /usr/bin:/bin"},
                    "idma_filelist": {"status": "UNMATERIALIZED_TEXT", "role": "Exact render_filelist(catalog) result with only declared root substitutions"},
                    "adapter_sv": {"status": "UNGENERATED", "role": "Original adapter emitter output; no behavioral replacement"},
                    "adapter_emitter_classpath": {"status": "UNRESOLVED_CLASS_CLOSURE", "role": "Original162 + modulecache/graph helpers +13 emitter classes and exact ordered Maven jars"}},
                  generated_contract={"source_contract_sha256": CATALOG_SHA256, "rtl_units": 296, "include_headers": 18,
                    "leaf_top": "idma_backend_rw_axi_flat_wrap", "adapter_top": "OriginalIdmaAdapterProbe",
                    "leaf_header": "Vidma_backend_rw_axi_flat_wrap.h", "adapter_header": "VOriginalIdmaAdapterProbe.h",
                    "prior_leaf_archive_objects": 22, "prior_adapter_archive_objects": 24,
                    "wrapper_parameters": copy.deepcopy(catalog["wrapper_parameters"]), "adapter_parameters": copy.deepcopy(catalog["adapter_parameters"]),
                    "native_abi": {"version": 1, "response_words": 17, "request_words": 25, "response_bits": 532, "request_bits": 785},
                    "unexpected_nonconvergence": "FAILURE", "clock_policy": "Unchanged explicit clock assignment, threads(1) before model construction"},
                  prior_outputs=copy.deepcopy(catalog["prior_outputs"]),
                  portability_deltas=["Only symbolic location substitution is proposed. No build has tested these relocated paths.",
                    "No hardware, scalar arithmetic, flags, wrapper parameters or scheduling substitutions.",
                    "Historical output hashes are comparison anchors, not a claim that fresh outputs already exist or must be silently normalized.",
                    "Source filenames can affect emitted source-info metadata. Any difference requires explicit reviewed identity accounting."],
                  unresolved_prerequisites=["Exact source export reconstruction and Bender/uv/tool bootstrap qualification; historical downloadable artifact availability is not assumed.",
                    "Matching complete Verilator/compiler/linker/helper/ELF/include/runtime closure and qualified source-relative search paths.",
                    "Portable full ordered warning-byte gates for28 leaf and145 adapter diagnostics; source-site catalog alone is insufficient.",
                    "Exact original adapter Scala emitter/class/Maven closure and source-location identity proof.",
                    "Separately admitted fresh build, ELF inspection and finite runtime requalification; existing resource reservations remain unchanged."],
                  environment={"PATH": "{artifact:qualified_tool_path}", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8",
                               "PYTHONDONTWRITEBYTECODE": "1", "VERILATOR_ROOT": vr, "MAKEFLAGS": "-j1"},
                  execution_authority=False, readiness=False,
                  qualification={"portable_build_executed": False, "runtime_executed": False, "broad_adapter_gate": False, "host_or_numerical_acceptance": False})
    order = ["idma_generate_leaf", "idma_syntax_leaf", "idma_archive_leaf",
             "idma_link_cabi_library", "idma_link_direct_executable", "idma_emit_adapter",
             "idma_generate_adapter", "idma_syntax_adapter", "idma_archive_adapter", "idma_link_adapter_endpoint"]
    by_id = {s["id"]: s for s in stages}
    result["stages"] = stages = [by_id[name] for name in order]
    ids = [s["id"] for s in stages]
    outputs = [x for s in stages for x in s["outputs"]]
    need(len(ids) == len(set(ids)) and len(outputs) == len(set(outputs)), "duplicate stage/output role")
    validate_role_order(result)
    return result


def validate_role_order(description):
    """Check declared availability only; an unresolved role is never qualified."""
    rows = description["inputs"]
    roles = [row["role"] for row in rows]
    need(len(roles) == len(set(roles)), "unique source input roles")
    prerequisites = description["prerequisite_roles"]
    aggregates = description["aggregate_roles"]
    need(not (set(roles) & set(prerequisites)), "distinct prerequisite roles")
    known = set(roles) | set(prerequisites)
    for role, members in aggregates.items():
        need(role not in known and members and len(members) == len(set(members)), "distinct nonempty aggregate")
        need(all(member in known for member in members), "aggregate member available")
        known.add(role)
    for stage in description["stages"]:
        need(all(role in known for role in stage["inputs"]), "stage input available in producer order")
        for role in stage["outputs"]:
            need(role not in known, "unique output role")
            known.add(role)
    return {"status": "PASS_DECLARED_ROLE_ORDER_ONLY", "execution_authority": False}


def validate_description(candidate, catalog):
    """Reject any description drift, including types, fields, order and flags."""
    need(type(candidate) is dict, "description object")
    expected = describe(catalog)
    expected_bytes = canonical(expected)
    need(hashlib.sha256(expected_bytes).hexdigest() == DESCRIPTION_SHA256, "fixed description contract")
    need(canonical(candidate) == expected_bytes, "exact expected description")
    return {"status": "PASS_EXACT_UNRUN_DESCRIPTION_ONLY", "execution_authority": False}
