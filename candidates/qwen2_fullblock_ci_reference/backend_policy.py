"""Explicit candidate backend setting at an existing pre-arithmetic boundary."""
import sys
START='official-holder-construction-and-raw-bindings'
CHECK=frozenset((START,'official-prefix-execution','official-tail-execution','observations29-and-semantic-validation','source-and-raw-boundary-after'))

def before_stage(recipe,stage):
    profile=recipe.dependency('candidates/qwen2_fullblock_ci_execution/runtime_profile.py')
    if profile.mkldnn_enabled() is not False:return
    if stage not in CHECK:return
    torch=sys.modules.get('torch')
    recipe.need(torch is not None,'backend policy requires initialized Torch')
    if stage==START:torch.backends.mkldnn.enabled=False
    recipe.need(torch.backends.mkldnn.enabled is False,'explicit ATen GEMM candidate backend drift')
