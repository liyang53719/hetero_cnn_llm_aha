from heteronpu.policy_lowering import lower_layer,lower_qwen38_model,qwen38_policy_lowering_report

def test_gdn_layer_compiles():
 x=lower_layer(0,'linear_attention')
 assert len(x['compiled']['commands'])>20
 assert all(int(c['word_hex'],16)<1<<128 for c in x['compiled']['commands'])

def test_qsa_has_primitive_qk_pv_softmax():
 x=lower_layer(3,'qwen_sparse_attention')
 names={o['opcode'] for o in x['spec']['operations']}
 assert {'matrix_qk','matrix_pv','sfu_softmax'}<=names

def test_model_deterministic_and_segmented():
 pattern=tuple('qwen_sparse_attention' if (i+1)%4==0 else 'linear_attention' for i in range(48))
 a=lower_qwen38_model(pattern);b=lower_qwen38_model(pattern)
 assert a['program_sha256']==b['program_sha256']
 assert a['segment_count']==48
 assert max(len(x['compiled']['commands']) for x in a['layers'])<65535

def test_report():
 r=qwen38_policy_lowering_report();assert r['status']=='PASS';assert r['gdn_layers']==36;assert r['qsa_layers']==12
