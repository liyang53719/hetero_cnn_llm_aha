"""Explicit cold workload admission and output geometry; no arithmetic."""
STAGES=(('n0',1536),('qr',1536),('kr',256),('v',256),('q',1536),('k',256),('att',1536),('o',1536),('r',1536),('n1',1536),('gate',8960),('up',8960),('act',8960),('down',1536),('y',1536))
COMPILE_WALL_SECONDS=10
RUN_WALL_SECONDS={16:30,128:45}
INPUT_PINS={
    16:dict(summary_sha256='1543618fb894864d1e8a97605b69b424518e9d209ee38de3aa4064ba3367b3bd',
            snapshot_sha256='88cc7fe74bbe0a982490f138c99928314c325ded5de73fc50296d5c0cf5c17e2',
            input_x_sha256='271b8498d6c764d48a7f63fb3f314a49b3bafb7b8f62e15bf70fb2595777349c',
            readonly_sha256='0a94ea142c28a6c1ce4b8ad928caecee9c5721bb6e4bc0eb097eebd8202aabf8'),
    128:dict(summary_sha256='25b947ff774412685d9691de0a06f1a1cf489388557db357013bf7911c11681a',
             snapshot_sha256='5b9247588ddddcada1e669034c3e8e0a17ffb39c6c6aef3ffd1bb5e49c6924ab',
             input_x_sha256='ddcdcca67cb3e26007880a78074ea3eb70bf83e8d8060fa2258bb2c7644695df',
             readonly_sha256='e96def26157427fc60a44f1af7a9a8443010eb5327c1ccb9b93c3b0e70fcafe7'),
}

def cold_rows(rows,past_tokens=0):
    if type(rows) is not int or rows not in INPUT_PINS or type(past_tokens) is not int or past_tokens!=0:
        raise ValueError('only explicit cold M16/M128 rows with past_tokens=0 are admitted')
    return rows

def output_shapes(rows):
    m=cold_rows(rows)
    shapes={f'phase_{i}_{name}_recipe.f32le':(1,m,width) for i,(name,width) in enumerate(STAGES)}
    shapes.update({name+'.f32le':(1,m,2,128) for name in ('cache_k','cache_v')})
    shapes.update({name+'.f32le':(1,12,m,m) for name in ('scores','logits','softmax_fp32','prob')})
    shapes['silu.f32le']=(1,m,8960)
    return shapes

def output_inventory(rows):
    import math
    return {name:4*math.prod(shape) for name,shape in output_shapes(rows).items()}

def validate_sealed_inventory(rows,sealed):
    expected=output_inventory(rows)
    if set(sealed)!=set(expected) or any(record['bytes']!=expected[name] for name,record in sealed.items()):
        raise ValueError('sealed output inventory differs from complete cold workload shape')
    return expected

def validate_input_metadata(rows,cold,readonly):
    m=cold_rows(rows,cold['past_tokens']);pin=INPUT_PINS[m]
    if (cold['tokens']!=m or cold['inputs']['past_tokens']!=0 or
        cold['inputs']['token_ids']!=list(range(m)) or cold['inputs']['position_ids']!=list(range(m)) or
        cold['inputs']['intermediate_preloads']!=0 or readonly['intermediate_preloads']!=0 or
        cold['inputs']['readonly_sha256']!=pin['readonly_sha256'] or readonly['sha256']!=pin['readonly_sha256'] or
        cold['inputs']['input_x_sha256']!=pin['input_x_sha256'] or readonly['input_x_sha256']!=pin['input_x_sha256'] or
        readonly['bytes']!=188043264):
        raise ValueError('cold workload original input/arena identity differs')
    return pin
