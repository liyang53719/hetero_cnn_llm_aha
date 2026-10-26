"""Exact four-function stat parser extraction; no supervisor, process or native execution."""
from pathlib import Path
import hashlib,json,os

def need(ok, message):
    if not ok:
        raise ValueError(message)

def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            h.update(block)
    return h.hexdigest()

def pin(path):
    path = Path(path)
    result = dict(path=str(path), bytes=path.stat().st_size, sha256=digest(path), resolved_path=str(path.resolve()))
    if path.is_symlink():
        result['symlink_target'] = os.readlink(path)
    return result

def structure_check(root,manifest):
    root=Path(root);p=root/'reports/stat.json'
    need(p.is_file() and not p.is_symlink(),'regular stat JSON')
    with p.open('rb') as f:raw=f.read(2*1024**2+1)
    need(len(raw)<=2*1024**2,'small stat JSON cap')
    def unique(pairs):
        d={}
        for k,v in pairs:need(k not in d,'duplicate JSON key');d[k]=v
        return d
    data=json.loads(raw,object_pairs_hook=unique)
    need(type(data) is dict and set(data)=={'creator','invocation','modules','design'},'fixed stat JSON schema')
    need(data['creator'].startswith('Yosys 0.52 ') and data['invocation']=='stat -json ','fixed stat invocation')
    rawmods=data['modules'];need(type(rawmods) is dict and 1<=len(rawmods)<=10000,'bounded module statistics')
    def norm(n):
        need(type(n) is str and 0<len(n)<=4096,'bounded module/type name')
        return n[1:] if n.startswith('\\') else n
    mods={};edges=0
    for name,row in rawmods.items():
        name=norm(name);need(name not in mods,'unambiguous normalized module')
        need(type(row) is dict and row.get('num_processes')==0 and type(row.get('num_processes')) is int,'proc fully converted each declared module')
        cells=row.get('num_cells_by_type');need(type(cells) is dict,'cell type map')
        normalized={}
        for key,value in cells.items():
            key=norm(key);need(key not in normalized,'ambiguous normalized cell type');normalized[key]=value
        cells=normalized;edges+=len(cells)
        need(edges<=100000 and all(type(v) is int and 1<=v<=2**32-1 for v in cells.values()),'bounded counts/edges')
        need(type(row.get('num_cells')) is int and sum(cells.values())==row['num_cells'],'cell count sum')
        mods[name]=cells
    top=manifest['top'];need(top in mods,'exact complete top in statistics')
    memo={};busy=set()
    def expand(name,depth=0):
        need(depth<=100 and name not in busy,'acyclic bounded hierarchy')
        if name in memo:return memo[name]
        busy.add(name);result={name:1}
        for child,count in mods[name].items():
            if child in mods:
                for target,n in expand(child,depth+1).items():
                    result[target]=result.get(target,0)+count*n
                    need(result[target]<=2**40,'bounded expanded multiplicity')
            else:need(child.startswith('$'),'unresolved non-internal module '+child)
        busy.remove(name);memo[name]=result;return result
    counts=expand(top)
    need(counts.get('qwen2_matrix_command_endpoint')==8,'full original eight endpoints, not leaf')
    expected=['HeteroBF16FmaPre','HeteroBF16FmaMul','HeteroBF16FmaPost','HeteroBF16FmaRound']
    for family in expected:need(counts.get(family)==4096,'full 4096 arithmetic lane stage '+family)
    endpoint=expand('qwen2_matrix_command_endpoint')
    for family in expected:need(endpoint.get(family)==512,'each endpoint has512 lane stages')
    design=root/'reports/design.json';need(design.is_file() and not design.is_symlink() and 0<design.stat().st_size<=manifest['caps']['single_file_hard_bytes'],'retained opaque full JSON')
    log=root/'worker.log'
    with log.open('rb') as f:lograw=f.read(manifest['caps']['log_hard_bytes']+1)
    need(len(lograw)<=manifest['caps']['log_hard_bytes'] and b'ERROR:' not in lograw,'bounded native log without error')
    return dict(status='PASS_FULL4096_YOSYS_HIERARCHY_PROC_CHECK_ONLY',module_count=len(mods),reachable_types=len(counts),expanded_module_multiplicity=counts,endpoint_count=8,lane_stages_per_endpoint=512,physical_mac_slots_source_bound=4096,stat_pin=pin(p),opaque_design_pin=pin(design),native_check_assert_and_simcheck=True,technology_mapping=False,PPA=False,numerical=False,unified_five_profile_top=False,RTL_arithmetic_modified=False)
