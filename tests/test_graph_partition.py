from heteronpu.graph_partition import *
def p():return GraphPartitioner(CapabilityManifest(frozenset(x.policy for x in DEFAULT_PATTERNS)))
def test_qwen2():assert [s.policy for s in p().partition(qwen2_synthetic_graph()).segments]==['rmsnorm_projection','attention_op','swi_glu']
def test_qwen38():
 r=p().partition(qwen38_synthetic_graph());assert [s.policy for s in r.segments][:4]==['ple_policy','gated_residual_policy','qsa_policy','moe_policy'];assert r.fallback_segments[0].fallback_reason=='unsupported_op:vision_patch_embed'
def test_deterministic():assert p().partition(qwen38_synthetic_graph()).program_sha256==p().partition(qwen38_synthetic_graph()).program_sha256
def test_report():assert partition_report()['status']=='PASS'
