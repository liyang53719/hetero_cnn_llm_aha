"""Bounded source contract, not hardware execution or full archival verification."""
from pathlib import Path
import argparse
import hashlib
import json

C = Path(__file__).resolve().parent
W = C.parent
parser=argparse.ArgumentParser(add_help=False)
parser.add_argument('--original-router-source',type=Path,required=True)
args,unittest_args=parser.parse_known_args()
ORIGINAL=args.original_router_source
ORIGINAL_SHA = "aa9d28733ef6e101ad4f3ccb51e3844787970b0292427b847cdae230585be5dc"
OLD_ROLE = "  val role=j.tag(15,0)===1.U || j.tag(15,0)===4.U || j.tag(15,0)===7.U\n"
NEW_ROLE = """  // Private semantic marker from the original Commands' validated official
  // profile0 Q/K/V roles. Guard remaps tag to a persistent physical sequence;
  // low tag bits are transport identity, never a public21 arithmetic selector.
  // Keep the original shape rejection and K-window/pair-reverse recipe below.
  // A matching shape alone does not select this route or create authority.
  val role=j.public21Reduction
"""


def need(condition, message):
    if not condition:
        raise ValueError(message)


def check(source=None):
    old = ORIGINAL.read_text()
    need(hashlib.sha256(ORIGINAL.read_bytes()).hexdigest() == ORIGINAL_SHA,
         "exact reconstructed original source")
    new = (C / "source/Public21QkvReductionRouter.scala").read_text() if source is None else source
    need(old.count(OLD_ROLE) == 1, "one original selector")
    need(new == old.replace(OLD_ROLE, NEW_ROLE),
         "only the private semantic selector and its explanation changed")
    need(new.count("val role=j.public21Reduction") == 1,
         "one marker selector")
    need("val role=j.tag" not in new, "physical tag never selects arithmetic")
    # Exact whole-source comparison above also preserves all numerical, debt,
    # resident-resource, and terminal routing logic. These are useful named gates.
    for text in (
        "val malformed=io.job.valid && role && !shape",
        "io.ordinaryJob.valid:=io.job.valid && !role && jobAllowed",
        "reduction.io.dense.request.valid:=io.job.valid && role && shape && jobAllowed",
        "reduction.io.dense.request.bits.job:=j",
        "reduction.io.dense.request.bits.identity:=j.tag+1.U",
        "reduction.io.dense.request.bits.kRanges(0).end:=1024.U",
        "reduction.io.dense.request.bits.kRanges(1).end:=1536.U",
        "reduction.io.dense.request.bits.pairReverse:=true.B",
        "io.done.valid:=Mux(state===reducing,reduction.io.dense.result.valid,",
        "when(io.done.fire || io.residentHost.result.fire){state:=idle}",
        "val cancel=fault || io.residentHost.abort || io.backendReset",
    ):
        need(text in new, "preserved " + text)
    return dict(status="PASS_EXACT_ROUTER_SOURCE_DELTA_NOT_DUT",
                source_sha256=hashlib.sha256(new.encode()).hexdigest(),
                original_sha256=ORIGINAL_SHA,
                physical_tag_rewritten=False,
                numerical_recipe_changed=False,
                marker_authority="Original Commands validated profile0 QKV semantic role; parent binding must be independently checked.",
                historical_transitive_graph_verified=False)


if __name__ == "__main__":
    print(json.dumps(check(), indent=2))
