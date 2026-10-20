"""Fixed owner archive reuse and direct driver commands; no native action on import."""
from pathlib import Path

MIB = 1024**2
TREE_PIN = {'bytes': 138896, 'sha256': 'cd79027b5105f5f00e95c6b719785be083b0d584d6168e6af352f7a354698856'}
RECEIPT_PIN = {'bytes': 155088, 'sha256': '31a8cf47e11b92fe304f735733f15f6b9ab496b22b41d155f566f1f16d187b4e'}
REVIEW_PIN = {'bytes': 9476, 'sha256': '14bb3cbebaa5002dad596c235db675cec66904a60e0ec8c8101d735ac853f1b1'}
REVIEW_MANIFEST_PIN = {'bytes': 786, 'sha256': '0a832dcb156af5f8df8620b2b43846dd0071bd36afdf42c0b9e3091a7fafbdcd'}
BUILD_PIN = {'bytes': 1582, 'sha256': '0020d763acee29b67133a627e94209bc66786ae25587523c8af232ec01ed6007'}
LOG_PIN = {'bytes': 32385, 'sha256': 'e698e29fadb7d10248454d8875e7748891d07392f6d67f0051377a09aa40aa9c'}
DEP_PIN = {'bytes': 1272, 'sha256': '9f7f8238eda595ee82071974f3c117f88c9389cc373a9a5c1d1edfad306455fc'}
MAKE_PIN = {'bytes': 2617, 'sha256': '1ec9850e6e21d0263c011db5e7b94e68d4feb23cc168c816b02bac6e68f0789b'}
OLD_ELF_PIN = {'bytes': 12718080, 'sha256': 'a91ff84921ba6b116b762a3f4eb384f1518be88e3feca562c1ee2996b6ba4fa1'}
FILES = {'include/verilated.h': {'bytes': 62071, 'root': 'verilator', 'sha256': '9ffa8ea44968c2b7767bd1fb0b7965f492e4d943014c4228601e4e91f4c426a7'}, 'include/verilated_config.h': {'bytes': 1209, 'root': 'verilator', 'sha256': 'f777e30008f72120fc8ff6105c90a917d0b6f7fc6a0ea9f65a65db2bb9bd0eaa'}, 'include/verilated_funcs.h': {'bytes': 161483, 'root': 'verilator', 'sha256': '52934dd05dc975b58bb509fcfd48bd85bbe1e35e6fb64e398a9c6cb372df5517'}, 'include/verilated_types.h': {'bytes': 90766, 'root': 'verilator', 'sha256': '784fdbf202f7c305fcde8e34813c418897596c214f3a017274d87ed3cb8d6ae7'}, 'include/verilatedos.h': {'bytes': 30602, 'root': 'verilator', 'sha256': '32ef26e058747b19e9c53209ac0ba9a8f48d7e1a2f53006680eddb64e90ee879'}, 'include/vltstd/svdpi.h': {'bytes': 20201, 'root': 'verilator', 'sha256': '478f1b254420b06f3827df55490a729ec76e106de626d8d0135c35dc37732ff6'}, 'obj/VQwenOwnerKernel.h': {'bytes': 15738, 'root': 'owner', 'sha256': '2bd3ec76a30248db7d05a4b9940cb3d9a7b9fa51baf06dab015e9fa1f052261c'}, 'obj/VQwenOwnerKernel__ALL.a': {'bytes': 17138904, 'root': 'owner', 'sha256': 'fdd9b4afd8a18a8b62c88cd65bc25a1b3cc9c665c2fe526be675c03467012e1c'}, 'obj/VQwenOwnerKernel___024root.h': {'bytes': 4630258, 'root': 'owner', 'sha256': 'a9371ed20684a6b5635de6203918cd33b910d856bd83618cf4a33c9dda398aaf'}, 'obj/verilated.o': {'bytes': 1355928, 'root': 'owner', 'sha256': '5c12889ef6d43e30d18eecbf052a8b8e36fd735f9e64419156cf24b9382de0e9'}, 'obj/verilated_dpi.o': {'bytes': 203888, 'root': 'owner', 'sha256': '40fb64777bf5ed2ff6490c51479efa8841169159f6c508373d06bffc79244da2'}, 'obj/verilated_threads.o': {'bytes': 440560, 'root': 'owner', 'sha256': 'ae51c8cee28cc7dacaccbbe06c3a4bc73864103b224ff7bc058baabe6efdea49'}}
COMPILE_FLAGS = ['-MMD', '-DVERILATOR=1', '-DVM_COVERAGE=0', '-DVM_SC=0', '-DVM_TIMING=0', '-DVM_TRACE=0', '-DVM_TRACE_FST=0', '-DVM_TRACE_VCD=0', '-DVM_TRACE_SAIF=0', '-DVM_VPI=0', '-faligned-new', '-fcf-protection=none', '-Wno-bool-operation', '-Wno-int-in-bool-context', '-Wno-shadow', '-Wno-sign-compare', '-Wno-subobject-linkage', '-Wno-tautological-compare', '-Wno-uninitialized', '-Wno-unused-but-set-parameter', '-Wno-unused-but-set-variable', '-Wno-unused-parameter', '-Wno-unused-variable', '-DVM_PREFIX_INCLUDE=<VQwenOwnerKernel.h>', '-DVM_PREFIX_INCLUDE_DPI=<VQwenOwnerKernel__Dpi.h>', '-std=c++17', '-O0']


def inventory(g, value):
    g.need(set(value)=={'root','entries'} and type(value['entries']) is list and len(value['entries'])==608,
           'REUSE_EXACT_TREE_SHAPE')
    entries={}
    for row in value['entries']:
        name=row['path']; parts=name.split('/')
        g.need(type(name) is str and all(x not in ('','.','..') for x in parts) and not name.startswith('/') and name not in entries,
               'REUSE_SAFE_UNIQUE_MEMBER')
        if row['type']=='directory':
            g.need(set(row)=={'path','mode','type'} and row['mode']==0o700,'REUSE_DIRECTORY')
            entries[name]={'kind':'directory','mode':'0o700'}
        else:
            mode=0o700 if name=='obj/VQwenOwnerKernel' else 0o600
            g.need(set(row)=={'path','mode','type','bytes','sha256'} and row['type']=='file' and row['mode']==mode,
                   'REUSE_REGULAR_MEMBER')
            entries[name]={'kind':'regular','mode':oct(mode),'bytes':row['bytes'],'sha256':row['sha256']}
    members=[x for x in entries.values() if x['kind']=='regular']
    g.need(len(members)==599 and sum(x['bytes'] for x in members)==493245462,'REUSE_EXACT_TOTALS')
    return {'root':value['root'],'entries':dict(sorted(entries.items())),'files':599,'bytes':493245462}


def stable(g, fs, tree):
    g.need(fs.tree_inventory(Path(tree['root']),512*MIB,599,608,128*MIB)==tree,'REUSE_ORIGINAL_TREE_DRIFT')


def accept(g, fs, cfg, sup):
    g.need(set(cfg)=={'root','inventory','receipt','review','review_manifest','verilator_root'},'REUSE_BINDING_KEYS')
    root=g.clean(cfg['root']);g.clean(cfg['verilator_root'])
    tree=inventory(g,g.decode(g.checked(Path(cfg['inventory']),TREE_PIN,MIB)))
    g.need(tree['root']==str(root) and Path(cfg['receipt'])==root/'EXECUTION_RESULT.json','REUSE_ROOT_BINDING')
    g.checked(Path(cfg['review_manifest']),REVIEW_MANIFEST_PIN,MIB)
    review=g.checked(Path(cfg['review']),REVIEW_PIN,MIB)
    g.need(b'ACCEPT_ACTUAL_OWNER_CACHE_BUILD_NATURAL_ZERO_RUNTIME_RESET_REQUIRED_HIGH_ONLY' in review,'REUSE_ACTUAL_REVIEW_SCOPE')
    receipt=g.decode(g.checked(Path(cfg['receipt']),RECEIPT_PIN,MIB))
    g.need(receipt['status']=='INCOMPLETE' and receipt['failure_type']=='ValueError' and
           receipt['failure_boundary'] is None and receipt['failure_code'] is None and
           [x['name'] for x in receipt['stages']]==['build','run'] and
           receipt['generation_executed'] is False and receipt['generation_cache_reused'] is True and
           receipt['binary']['identity']==OLD_ELF_PIN,'REUSE_PRIOR_SCOPE')
    build=g.decode(g.checked(root/'phases/build/native.json',BUILD_PIN,MIB))
    g.need(build==receipt['stages'][0]['record'],'REUSE_BUILD_RECORD')
    sup.natural_success(build,receipt['stages'][0]['usage'])
    g.checked(root/'phases/build/native.log',LOG_PIN,MIB)
    g.checked(root/'obj/owner_micro.d',DEP_PIN,MIB)
    g.checked(root/'obj/VQwenOwnerKernel.mk',MAKE_PIN,MIB)
    stable(g,fs,tree)
    return tree,receipt


def buffers(g, cfg):
    roots={'owner':g.clean(cfg['root']),'verilator':g.clean(cfg['verilator_root'])}
    out={}
    for name,row in FILES.items():
        out[name]=g.checked(roots[row['root']]/name,{k:row[k] for k in ('bytes','sha256')},32*MIB,fixed_leaf=Path(name).name)
    archive=out['obj/VQwenOwnerKernel__ALL.a']
    g.need(archive.startswith(b'!<arch>\n') and not archive.startswith(b'!<thin>\n'),'REUSE_REGULAR_ARCHIVE')
    g.need(len(out)==12 and sum(map(len,out.values()))==24151608,'REUSE_FIXED_COPY_COUNT')
    return out


def stage(g, fs, relink, work, raw):
    g.need(set(raw)==set(FILES),'REUSE_FIXED_COPY_COUNT')
    result={}
    for name,data in raw.items():
        row=FILES[name];relink.write_exact(work/name,data)
        expected={k:row[k] for k in ('bytes','sha256')};expected['mode']='0o600'
        g.need(fs.identity(work/name,32*MIB)==expected,'REUSE_COPY_READBACK');result[name]=expected
    return result


def commands(catalog, work, n0, wq):
    obj=work/'obj';inc=work/'include'
    start=[catalog['programs']['g++'],'-B',str(work/'compiler-search')+'/']
    compile_argv=start+COMPILE_FLAGS+['-I',str(obj),'-I',str(inc),'-I',str(inc/'vltstd'),
        '-I',str(work/'fixtures'),'-c','-o',str(obj/'owner_micro.o'),str(work/'fixtures/owner_micro.cpp')]
    link_argv=start+[str(obj/name) for name in ('owner_micro.o','verilated.o','verilated_dpi.o','verilated_threads.o','VQwenOwnerKernel__ALL.a')]
    link_argv+=['-pthread','-lpthread','-latomic','-o',str(obj/'VQwenOwnerKernel')]
    return {'compile':compile_argv,'link':link_argv,'run':[str(obj/'VQwenOwnerKernel'),str(n0),str(wq)]}


def dependency_closure(g, raw, work):
    # One fixed compiler-produced rule; no general Makefile interpretation.
    text=raw.decode('ascii').replace('\\\n',' ')
    g.need(text.count(':')==1,'REUSE_DEPENDENCY_RULE')
    target,body=text.split(':',1)
    expected=[work/'fixtures/owner_micro.cpp',work/'obj/VQwenOwnerKernel.h']
    expected += [work/'include'/n for n in ('verilated.h','verilated_config.h','verilatedos.h','verilated_types.h','verilated_funcs.h','vltstd/svdpi.h')]
    expected += [work/'obj/VQwenOwnerKernel___024root.h']
    expected += [work/'fixtures'/n for n in ('sha256.hpp','owner_observations.inc','owner_inputs.inc')]
    g.need(target.strip()==str(work/'obj/owner_micro.o') and body.split()==[str(p) for p in expected],
           'REUSE_DEPENDENCY_EXACT_CLOSURE')
    return {'members':12,'exact_order':True,'all_user_inputs_staged':True,'old_driver_object_reused':False}
