"""Fresh combined-library child; original strict build/verification unchanged.

Call only in the composed tree under a separately reviewed external deadline.
This file itself does not launch, impose a new process group, or grant admission.
"""
from pathlib import Path
from . import prepare

def plan():
 from ..official_bf16 import dense_silu as original
 prepare.verify_installed()
 return dict(status='PREPARATION_ONLY',translation_units=list(original.TRANSLATION_UNITS),
  flags=list(original.STRICT_FLAGS),sources={n:prepare.digest(prepare.ROOT/n) for n in original.SOURCE_CLOSURE},
  compiler_timeout_seconds=30,external_supervisor_required=True,full_public_admitted=False)

def build(out):
 from ..official_bf16 import dense_silu as original
 before=prepare.verify_installed()
 # The supervisor must own this child and compiler as ONE process group.
 library,receipt=original.build_library(Path(out))
 verified=original.verify_library(receipt)
 if prepare.verify_installed()!=before:raise ValueError('M16 source changed during combined build')
 return library,verified
