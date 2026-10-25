"""Exact identity-lookup derivative normal-source bridge binding, not a copied observer or lease helper."""
import hashlib
import importlib
import importlib.util
from pathlib import Path
import sys
import types

PACKAGE = '_qualified_selective_line'
MODULES = ('capture', 'monitor', 'service_trace', 'bridge')

def need(ok, message):
    if not ok:raise ValueError(message)

def pinned(path, files):
    path=Path(path).resolve(strict=True);raw=path.read_bytes();pin=files[str(path)]
    need(len(raw)==pin['bytes'] and hashlib.sha256(raw).hexdigest()==pin['sha256'],'source drift '+path.name)
    return path

def create_candidate_namespace(config):
    root=Path(config['selective_root']).resolve(strict=True)
    need(PACKAGE not in sys.modules and not any(n.startswith(PACKAGE+'.') for n in sys.modules),'fresh candidate namespace required')
    module=types.ModuleType(PACKAGE);module.__path__=[str(root)];sys.modules[PACKAGE]=module
    return module

def load_source_gate(config):
    path=pinned(config['project_code_gate_source'],config['files'])
    name='_selective_existing_project_code_gate'
    need(name not in sys.modules,'single normal source gate load')
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);sys.modules[name]=module;spec.loader.exec_module(module)
    need(Path(module.__file__).resolve()==path,'project code gate origin')
    return module

def load_candidate(config):
    root=Path(config['selective_root']).resolve(strict=True)
    files={name:config['files'][str(root/name)] for name in ('capture.py','monitor.py','service_trace.py','bridge.py','SOURCE_PINS.json')}
    for name in files:pinned(root/name,config['files'])
    # Reuse the original complete-source exec attestation, not a custom importer.
    source_gate=load_source_gate(config)
    package=create_candidate_namespace(config)
    with source_gate.ProjectCodeGate(root,files) as gate:
        modules={name:importlib.import_module(PACKAGE+'.'+name) for name in MODULES}
    need({e['relative'] for e in gate.events}=={name+'.py' for name in MODULES},'complete normal candidate module exec closure')
    for name,module in modules.items():
        need(Path(module.__file__).resolve()==root/(name+'.py'),'candidate module origin')
        pinned(root/(name+'.py'),config['files'])
    return modules,dict(status='NORMAL_FULL_SOURCE_IDENTITY_LOOKUP_BINDING_ONLY',module_exec_events=gate.events,
        files=files,helper_source=config['project_code_gate_source'],namespace=PACKAGE,
        ast_definition_test=False,candidate_arithmetic_executed=False)

def make_capture(modules, owner, rows, base_fields, bindings):
    monitor,bridge=modules['monitor'],modules['bridge']
    capture=bridge.make_observation(monitor,owner,rows,base_fields,bindings,selective_lines=True)
    need(capture.selective_lines is True and capture.ast_test is False,'normal source selective opt-in')
    need(type(capture)._line is monitor.Observation._line and
         type(capture)._return is monitor.Observation._return,'frame-sensitive callbacks must not be wrapped')
    need(type(capture).__enter__.__code__.co_filename==bridge.__file__ and
         type(capture).stop.__code__.co_filename==bridge.__file__,'original bridge lifetime implementation')
    need(capture.monitor_masks.__func__ is monitor.Observation.monitor_masks,'original per-code mask builder')
    need(set(capture.codes)=={'run','work','consume','matrix','op','tick','client'},'seven original source-bound roles')
    return capture

def mask_snapshot(capture, *, installed, previous=None):
    mon=sys.monitoring
    expected=capture.monitor_masks()
    need(type(expected) is dict and len(expected)==7,'selective exact per-code mask map')
    for role,code in capture.codes.items():
        required=mon.events.PY_RETURN | (0 if role in ('op','consume','tick') else mon.events.LINE)
        need(expected[code]==required,'candidate role mask differs')
    if installed:
        slot=capture.tool
        need(slot in (3,4) and mon.get_tool(slot)==capture._monitor_label and not mon.get_events(slot),'candidate installed lease ownership')
        need(capture._monitor_masks==expected and set(capture._monitor_codes)==set(expected),'reviewed per-code installation ledger')
        need(all(mon.get_local_events(slot,code)==value for code,value in expected.items()),'actual installed local masks differ')
        need(capture._monitor_callbacks[mon.events.LINE].__func__ is type(capture)._line and
             capture._monitor_callbacks[mon.events.PY_RETURN].__func__ is type(capture)._return,'registered direct callback identities')
    else:
        need(previous is not None and capture.closed and capture.tool is None and capture.error is None and
             capture._stop_attempted and not capture._monitor_owned,'candidate monitor terminal cleanup')
        slot=previous['slot']
        need(mon.get_tool(slot) is None and not mon.get_events(slot) and
             all(mon.get_local_events(slot,code)==0 for code in expected),'candidate local masks or lease remain')
    return dict(phase='installed' if installed else 'cleaned',slot=slot,
        role_masks={role:expected[code] for role,code in capture.codes.items()},
        role_code_identity={role:dict(file=code.co_filename,qualname=code.co_qualname,first_line=code.co_firstlineno) for role,code in capture.codes.items()},
        local_masks_verified=True,callback_getter_available=False,callbacks_bound_directly=True)

def compare_three(arms, compare_pair, compare_fields):
    need(len(arms)==3 and [a['observer_variant'] for a in arms]==['off','original','selective_identity_r1'],'exact three fixed arms')
    need(all(a['terminal_acked'] and a['resources_released'] for a in arms),'all three real terminals required')
    first=compare_pair(arms[:2]);second=compare_pair([arms[0],arms[2]])
    compare_fields(arms[1]['capture_fields'],arms[2]['capture_fields'])
    need(arms[2]['selective_binding']['status']=='NORMAL_FULL_SOURCE_IDENTITY_LOOKUP_BINDING_ONLY' and
         [v['phase'] for v in arms[2]['selective_masks']]==['installed','cleaned'],'candidate normal binding and actual mask lifecycle')
    return dict(status='PASS_THREE_ARM_OUTPUT_TEN_FIELD_FULL_SERVICE_CONTROL_EQUIVALENCE',
        controls=[first,second],ten_fields_equal=True,cost_probe_used=False,
        fixed_order_not_statistical_benchmark=True,performance_adopted=False,
        no_hardware_utilization_or_cycle_inference=True)
