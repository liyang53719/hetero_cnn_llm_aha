"""Dtype policy is keyed by producer identity, never by a consumer's root role."""
FP32_BOUNDARY_OPERATIONS = frozenset({'oproj', 'down', 'attn_residual', 'residual'})

def fp32_boundary_indices(commands):
    indices = set()
    for command in commands:
        if command['operation'].rsplit('.', 1)[-1] not in FP32_BOUNDARY_OPERATIONS:
            continue
        binding = command['root_bindings'][str(command['roots']['dst'])]
        if binding['kind'] != 'ggml_node':
            raise ValueError('FP32 boundary requires a concrete produced tensor')
        indices.add(int(binding['index']))
    return frozenset(indices)

def node_dtype(binding, fp32_indices):
    if binding['kind'] != 'ggml_node':
        raise ValueError('node_dtype only classifies graph node tensors')
    return 'FP32' if int(binding['index']) in fp32_indices else 'BF16'
