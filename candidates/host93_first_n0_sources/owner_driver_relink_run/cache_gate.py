"""Accept exactly one failed-parent, successful-generation cache without regenerating."""
from pathlib import Path

MIB = 1024**2
TREE_PIN = {'bytes': 121623, 'sha256': '627b9e8d809da06a00a54d55dae065abf9fa777535570ba3ab0c8124cd238cfa'}
RECEIPT_PIN = {'bytes': 191163, 'sha256': 'b0211d4e00b3d8cf5b9829d3e4be54d840348a92cadce7e777287f58db6e15bf'}
REVIEW_PIN = {'bytes': 4666, 'sha256': 'c2816c97363998f17e782f19245051cf507f45a8b98543302998cea2438e33ee'}
REVIEW_MANIFEST_PIN = {'bytes': 282, 'sha256': 'd8a40602b4d5a500801f374ec93efc5be7b455fd87ae2a12ab07b01a205c6828'}
CHILD = 'Vbf16_context_lane_cluster16_rev8b_b_candidate_3'
LEAF = 'bf16_context_lane_cluster16_rev8b_b_candidate_3'
NO_GENERATION = "VM_HIER_VERILATOR=/bin/sh -c 'exit 97'"
OLD_TARGETS = ('VQwenOwnerKernel.mk', CHILD + '/' + LEAF + '.sv', CHILD + '/' + CHILD + '.mk')


def inventory(g, value):
    g.need(set(value) == {'root', 'entries'} and type(value['entries']) is list and len(value['entries']) == 536,
           'CACHE_EXACT_TREE_SHAPE')
    entries = {}
    for row in value['entries']:
        name = row['path']; parts = name.split('/')
        g.need(type(name) is str and all(x not in ('','.','..') for x in parts) and
               not name.startswith('/') and name not in entries, 'CACHE_SAFE_UNIQUE_MEMBER')
        if row['type'] == 'directory':
            g.need(set(row) == {'path','mode','type'} and row['mode'] == 0o700, 'CACHE_DIRECTORY')
            entries[name] = {'kind':'directory','mode':'0o700'}
        else:
            g.need(set(row) == {'path','mode','type','bytes','sha256'} and row['type']=='file' and
                   row['mode']==0o600, 'CACHE_REGULAR_MEMBER')
            entries[name] = {'kind':'regular','mode':'0o600','bytes':row['bytes'],'sha256':row['sha256']}
    files = [x for x in entries.values() if x['kind']=='regular']
    g.need(len(files)==528 and sum(x['bytes'] for x in files)==80670440, 'CACHE_EXACT_TOTALS')
    return {'root':value['root'],'entries':dict(sorted(entries.items())), 'files':528,'bytes':80670440}


def stable(g, fs, tree):
    g.need(fs.tree_inventory(Path(tree['root']), 96*MIB, 528, 536, 16*MIB) == tree,
           'CACHE_ORIGINAL_TREE_DRIFT')


def accept(g, fs, cfg, sup, expected_argv):
    g.need(set(cfg)=={'root','inventory','receipt','review','review_manifest'},'CACHE_BINDING_KEYS')
    root = g.clean(cfg['root'])
    raw = g.checked(Path(cfg['inventory']), TREE_PIN, MIB)
    tree = inventory(g, g.decode(raw))
    g.need(tree['root']==str(root) and Path(cfg['receipt'])==root/'EXECUTION_RESULT.json', 'CACHE_ROOT_BINDING')
    g.checked(Path(cfg['review_manifest']), REVIEW_MANIFEST_PIN, MIB)
    review = g.checked(Path(cfg['review']), REVIEW_PIN, MIB)
    g.need(b'Verdict: ACCEPT_ACTUAL_OWNER_GENERATION_NATURAL_ZERO_POSTFLIGHT_HEADER_BOUND_FAILURE_ONLY.' in review,
           'CACHE_ACTUAL_REVIEW_SCOPE')
    receipt = g.decode(g.checked(Path(cfg['receipt']), RECEIPT_PIN, MIB))
    g.need(receipt['status']=='INCOMPLETE' and receipt['failure_type']=='ValueError' and
           receipt['failure_boundary'] is None and receipt['failure_code'] is None and
           len(receipt['stages'])==1 and receipt['stages'][0]['name']=='generate' and
           receipt['stages'][0]['record']['argv']==expected_argv, 'CACHE_GENERATION_SCOPE')
    stage = receipt['stages'][0]
    sup.natural_success(stage['record'], stage['usage'])
    selected = {n:x for n,x in tree['entries'].items() if n.startswith(('obj/','fixtures/')) and x['kind']=='regular'}
    g.need(len(selected)==523 and sum(x['bytes'] for x in selected.values())==80364750 and
           sum(n.startswith('obj/') for n in selected)==516 and
           not any(n.endswith(('.o','.a','.gch','.so')) for n in selected), 'CACHE_SOURCE_ONLY_MEMBERS')
    stable(g,fs,tree)
    return tree, receipt


def stage_objects(g, fs, relink, tree, work):
    """Copy verified source buffers only. The original absolute fixture references stay pinned."""
    for name, row in tree['entries'].items():
        if not name.startswith('obj/') or row['kind']!='regular':
            continue
        wanted = {k:row[k] for k in ('bytes','sha256')}
        raw = g.checked(Path(tree['root'])/name, wanted, 16*MIB, fixed_leaf=Path(name).name)
        relink.write_exact(work/name, raw)
        g.need(fs.identity(work/name,16*MIB)=={k:row[k] for k in ('bytes','sha256','mode')},
               'CACHE_COPY_READBACK')
    stable(g,fs,tree)
    return {n:{k:x[k] for k in ('bytes','sha256','mode')} for n,x in tree['entries'].items()
            if n.startswith('obj/') and x['kind']=='regular'}


def build_command(g, original, work):
    g.need(original[0]=='/usr/bin/make' and original[-1]=='VQwenOwnerKernel' and
           original.count('-f')==1 and original[original.index('-f')+1]=='VQwenOwnerKernel.mk' and
           original.count('-j1')==1 and not any(x in original for x in ('hier_build','hier_verilation','hier_launch_verilator')),
           'CACHE_EXACT_TOP_BUILD')
    extra = [part for target in OLD_TARGETS for part in ('-o', target)]
    # command-line variables propagate to the sole child library make; -o need not.
    # That child's fixed makefile has no hierarchy include or generation recipe.
    return original[:-1] + extra + [NO_GENERATION, 'VM_HIER_RUN_DIR='+str(work), original[-1]]
