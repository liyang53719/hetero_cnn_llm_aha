"""Pure fresh terminal identity construction; caller authenticates all inputs.

No source loading, tensor decoding, process execution or receipt authority.
"""
PROFILE = 'qwen2-public-pv16-packed-m128-same-host-v1'

def prerequisite_view(value, receipt_sha256):
    return dict(m16_completion_verified=True,m128_verdict_inherited=False,old_pass_inherited=False,
        full_29_node_acceptance=False,receipt_sha256=receipt_sha256,attempt_nonce=value['attempt_nonce'],
        ci=value['ci'],host_sha256=value['host_sha256'],runtime_identity_sha256=value['runtime_identity_sha256'],
        source_manifest_sha256=value['source_manifest_sha256'],metadata_sha256={k:v['sha256'] for k,v in value['records'].items()},
        compile_receipt_sha256=value['library']['receipt']['sha256'],library_sha256=value['library']['binary']['sha256'])


def terminal_identity(manifest, producer, qualified, m16, manifest_sha256):
    origin=dict(schema=1,profile=PROFILE,origin=manifest['producer_workspace'],
        origin_manifest_sha256=manifest['producer_manifest']['sha256'],
        producer_receipt_sha256=manifest['producer_receipt']['sha256'],
        m16_prerequisite_sha256=manifest['m16_prerequisite']['sha256'],attempt_nonce=qualified['attempt_nonce'],
        payload_bytes_hashed=True,actual_chain_executed=False,old_pass_inherited=False,full_29_node_acceptance=False)
    return dict(native_result_sha256=producer['native']['result']['sha256'],origin_identity=origin,
        m16_prerequisite=prerequisite_view(m16,manifest['m16_prerequisite']['sha256']),
        library=manifest['library'],entry_manifest_sha256=manifest_sha256)


