from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

PACKAGE = Path(__file__).resolve().parents[1]
VERIFY = PACKAGE / "scripts" / "verify_generated_rtl.py"


def write_catalog(path: Path, names: tuple[str, ...]) -> None:
    body = "\n".join(f'    "{name}",' for name in names)
    path.write_text(
        "object HeteroOperatorPrimitiveCatalog {\n"
        "  val names: Seq[String] = Seq(\n"
        f"{body}\n"
        "  )\n"
        "}\n"
    )


def test_generated_rtl_verifier_passes_complete_catalog(tmp_path: Path) -> None:
    names = ("alpha", "beta")
    catalog = tmp_path / "Catalog.scala"
    rtl = tmp_path / "rtl"
    rtl.mkdir()
    write_catalog(catalog, names)
    (rtl / "catalog.txt").write_text("alpha\nbeta\n")
    for name in names:
        (rtl / f"{name}.sv").write_text(
            "// generated fixture\n" * 8
            + f"module {name}(input logic clock);\n  logic keep; assign keep = clock;\nendmodule\n"
        )
    result = subprocess.run(
        [sys.executable, str(VERIFY), "--rtl-dir", str(rtl), "--catalog", str(catalog)],
        check=False,
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr + result.stdout
    report = json.loads((rtl / "rtl_generation_audit.json").read_text())
    assert report["status"] == "PASS_GENERATED_RTL_CATALOG"
    assert report["expected_count"] == report["verified_count"] == 2
    assert not report["failures"]


def test_generated_rtl_verifier_rejects_missing_or_truncated_output(tmp_path: Path) -> None:
    names = ("alpha", "beta")
    catalog = tmp_path / "Catalog.scala"
    rtl = tmp_path / "rtl"
    rtl.mkdir()
    write_catalog(catalog, names)
    (rtl / "catalog.txt").write_text("alpha\nbeta\n")
    (rtl / "alpha.sv").write_text("module alpha; endmodule\n")
    result = subprocess.run(
        [sys.executable, str(VERIFY), "--rtl-dir", str(rtl), "--catalog", str(catalog)],
        check=False,
        text=True,
        capture_output=True,
    )
    assert result.returncode != 0
    report = json.loads((rtl / "rtl_generation_audit.json").read_text())
    assert report["status"] == "FAIL_GENERATED_RTL_CATALOG"
    assert any("too-small RTL" in failure for failure in report["failures"])
    assert any("missing RTL" in failure for failure in report["failures"])
