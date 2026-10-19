"""Pure source-check and same-buffer loader refusals; actual entry is not called."""
import sys
if not (sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode):raise SystemExit('require -I -S -B')
import ast,builtins,io,json,os,tempfile,types
from pathlib import Path
from contextlib import redirect_stdout
from unittest import mock
checks=[]
def need(ok,why):
    if not ok:raise ValueError(why)
def rejects(fn,why):
    try:fn()
    except (ValueError,OSError):return
    raise ValueError('missing rejection '+why)
args=['--repo',str(REPO),'--consumer-source',str(CONSUMER_SOURCE)]
with mock.patch.object(entry,'module',side_effect=AssertionError('source-check compiled source module')),redirect_stdout(io.StringIO()) as output:
    need(entry.main(['--source-check']+args)==0,'source check exit zero')
value=json.loads(output.getvalue());need(value['status']=='SOURCE_ONLY_LOCAL_CONTINUATION' and value['native_started'] is False,'source-check truthful only')
checks.append('inprocess_frozen_source_check_all_local_dependency_consumer_pins_without_module_exec')
for name,expected in entry.LOCAL_PINS.items():
    raw=(ROOT/name).read_bytes();need(entry.read(ROOT/name,expected)==raw,'same-buffer positive control')
    for kind in ('same_size_hash','short','symlink','hardlink','parent_symlink'):
        with tempfile.TemporaryDirectory(dir=ROOT) as t:
            root=Path(t);path=root/name
            if kind=='same_size_hash':path.write_bytes(bytes([raw[0]^1])+raw[1:])
            elif kind=='short':path.write_bytes(raw[:-1])
            elif kind=='symlink':target=root/'target';target.write_bytes(raw);path.symlink_to(target)
            elif kind=='hardlink':target=root/'target';target.write_bytes(raw);os.link(target,path)
            else:
                target=root/'real';target.mkdir();(target/name).write_bytes(raw);link=root/'link';link.symlink_to(target,target_is_directory=True);path=link/name
            with mock.patch.object(builtins,'compile',side_effect=AssertionError('unchecked source reached compile')):
                rejects(lambda:entry.read(path,expected),name+' '+kind)
        checks.append(name+'_'+kind+'_before_compile')
for mode in ([],['--source-check','--execute-fixed-continuation']):
    with mock.patch.object(entry,'read',side_effect=AssertionError('bad mode reached source read')):
        rejects(lambda:entry.main(mode+args),'entry mode')
checks.append('neither_or_both_modes_refused_before_any_source_read')
for extra in ([],['--started','nan','--deadline','6600'],['--started','0','--deadline','6601'],['--started','1e99','--deadline','1e99']):
    with mock.patch.object(entry,'read',side_effect=AssertionError('bad timing reached source read')),mock.patch.object(entry.signal,'signal',side_effect=AssertionError('bad timing changed signal')):
        rejects(lambda:entry.main(['--execute-fixed-continuation']+args+extra),'invalid actual deadline')
checks.append('missing_nonfinite_wrong_total_future_actual_timing_rejected_before_read_or_signal')
raw=(ROOT/'source_entry.py').read_bytes();seen=[]
def importer(name,*args,**kwargs):
    seen.append(name)
    if name=='sys':return types.SimpleNamespace(flags=types.SimpleNamespace(isolated=False,no_site=True,dont_write_bytecode=True))
    raise AssertionError('source imported before isolated flags')
try:exec(compile(raw,'flag_guard','exec'),{'__builtins__':dict(vars(builtins),__import__=importer)})
except SystemExit:pass
else:raise ValueError('isolation guard missing')
need(seen==['sys'],'isolation before imports/source reads');checks.append('isolated_no_site_no_bytecode_guard_first')
# Compile the unchanged nested binding decoder only, with synthetic JSON inputs.
main=next(n for n in ast.parse(raw).body if isinstance(n,ast.FunctionDef) and n.name=='main');decode=next(n for n in main.body if isinstance(n,ast.FunctionDef) and n.name=='decode')
lines=raw.splitlines(keepends=True);import textwrap
scope={'json':json,'need':need};exec(compile(textwrap.dedent(b''.join(lines[decode.lineno-1:decode.end_lineno]).decode()),'exact_binding_decoder','exec'),scope)
need(scope['decode'](b'{"repo":"synthetic"}')=={'repo':'synthetic'},'plain binding decoder')
for data in (b'{"x":1,"x":2}',b'{"x":NaN}',b'{"x":Infinity}'):
    rejects(lambda:scope['decode'](data),'duplicate/nonfinite private binding')
checks.append('same_ast_private_binding_decoder_rejects_duplicates_and_nonfinite')
print(json.dumps({'status':'PASS_CONTINUATION_ENTRY_SOURCE_ONLY','tests':len(checks),'checks':checks,'optimized':sys.flags.optimize,'native_started':False,'network_started':False},sort_keys=True))
TEST_RESULTS.append({'module':'test_entry_cold.py','tests':len(checks),'checks':checks})
