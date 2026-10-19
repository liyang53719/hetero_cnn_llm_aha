"""Pure source/tiny mocks; no subprocess, native compiler, real SV or network."""
import sys
if not (sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode):
    raise SystemExit('Use -I -S -B')
import ast
import copy
import builtins
import hashlib
import json
import os
from pathlib import Path
import tempfile
import types
import unittest
from unittest import mock
HERE = Path(__file__).absolute().parent
SOURCE = HERE / 'host_execution.py'
SIZE = 46046
SHA = 'e128cfe0ba74e2cb78498f41b3ef7ff4b7eb41df37ea6f13be8e45f440e670cd'
RAW = SOURCE.read_bytes()
def load(raw):
    if len(raw) != SIZE or hashlib.sha256(raw).hexdigest() != SHA:
        raise ValueError('source identity before compile')
    m = types.ModuleType('verified_host_execution_cold'); m.__file__ = str(SOURCE)
    exec(compile(raw, str(SOURCE), 'exec', dont_inherit=True), m.__dict__)
    return m
g = load(RAW)
if len(sys.argv) < 3 or sys.argv[1] != '--repo':
    raise SystemExit('Supply --repo ABSOLUTE_REPO')
REPO = Path(sys.argv[2]); del sys.argv[1:3]
PINS, BUFFERS, SUPPORT, LEXICAL = g.load(REPO)
PORTS = g.unique_json(BUFFERS[g.CONTRACT])['HOST_PORTS']
LEAF = 'qwen2_matrix_command_endpoint_cold'
CHILD = 'V' + LEAF
SV = '/tmp/fresh-same-job/HostBlockCollection.sv'
LOG = b'HOST93_RESET_OK asserted_high_edges=4 released_high_edges=4\nHOST93_LAUNCH_OK handshakes=1 high_edge=0 further_eval_calls=0\nHOST93_SHORT_PASS reset_and_launch_only=1\n'

def wrapper():
    return ('class '+CHILD+'_container: public '+CHILD+' {\npublic:\nlong long m_seqnum;\n'+CHILD+'_container(const char* scopep__V):\n'+CHILD+'(scopep__V), m_seqnum{0} {}\n};\n'+ '\n'.join('void '+LEAF+'_protectlib_'+s+'();' for s in ('create','combo_update','seq_update','final'))+'\n').encode()

def generated(root):
    def put(name, text):
        p=root/name; p.parent.mkdir(parents=True, exist_ok=True, mode=0o700);p.write_bytes(text if isinstance(text,bytes) else text.encode());p.chmod(0o600)
    put('obj/V'+LEAF+'__hierMkArgs.f','--lib-create '+LEAF+' --hierarchical-child 1 --top-module-encoded '+LEAF+' -GENABLE_ACCUMULATOR_SEED=1\n')
    put('obj/VHostBlockTop__hierMkArgs.f',CHILD+'/'+LEAF+'.sv '+SV+'\n')
    put('obj/VHostBlockTop.mk','include VHostBlockTop_hier.mk\n')
    put('obj/VHostBlockTop_hier.mk','VM_HIER_LIBS = '+CHILD+'/lib'+LEAF+'.a\n'+CHILD+'.mk\n')
    put('obj/'+CHILD+'/'+LEAF+'.cpp',wrapper())
    put('obj/'+CHILD+'/'+LEAF+'.sv','chandle handle__V;\n'+'\n'.join(LEAF+'_protectlib_'+s for s in ('create','combo_update','seq_update','final')))
    put('obj/VHostBlockTop___024root.h','\n'.join('    void* HostBlockTop__DOT__owner__DOT__matrix__DOT__leaves_'+str(i)+'__DOT__handle___05FV;' for i in range(8)))
    put('obj/VHostBlockTop__Syms.cpp','\n'.join('scope'+str(i)+'.configure(this, name(), "HostBlockTop.owner.matrix.leaves_'+str(i)+'");' for i in range(8)))
    header=[]
    for name,(direction,width) in PORTS.items():
        kind='W' if width>64 else '64' if width>32 else '' if width>16 else '16' if width>8 else '8'
        header.append('VL_'+('IN' if direction=='input' else 'OUT')+kind+'(&'+name+','+str(width-1)+',0'+(',16' if width==512 else '')+');')
    put('obj/VHostBlockTop.h','\n'.join(header))

def tree(root):
    return SUPPORT.tree_inventory(root, 4*1024**2, 256, 512, 1024**2)

def witness(root, compiled=False):
    return g.generated_witness(SUPPORT,tree(root),LEXICAL,PORTS,compiled,SV)

def filelist():
    sources=sorted(g.DROP)+['idma/source_'+str(i)+'.sv' for i in range(292)]
    return ('\n'.join(['+define+'+n for n in g.DEFINES]+['+incdir+@ROOT@/include'+str(i) for i in range(8)]+['@ROOT@/'+n for n in sources])+'\n').encode()


def generation_inputs(base):
    idma_entries = {'rtl/source_' + str(i) + '.sv': {'kind': 'regular',
                    'bytes': len(str(i)), 'sha256': g.sha(str(i).encode())} for i in range(293)}
    retained_entries = {'retained_' + str(i) + '.sv': {'kind': 'regular',
                        'bytes': len(str(i)), 'sha256': g.sha(str(i).encode())} for i in range(13)}
    sources = [str(base / 'idma/sources' / name) for name in idma_entries]
    sources += [str(base / 'retained/source' / name) for name in retained_entries] + [SV]
    return {'sv': {'path': SV, 'bytes': 4, 'sha256': g.sha(b'host')},
            'idma_tree': {'entries': idma_entries}, 'retained_tree': {'entries': retained_entries},
            'sources': sources, 'includes': ['include' + str(i) for i in range(8)],
            'defines': dict(g.DEFINES)}


def diagnostic_run(base, phase, callback):
    before = generation_inputs(base)
    with mock.patch.object(g, 'closure', return_value=before), \
         mock.patch.object(g, 'verify_tools', return_value={}), \
         mock.patch.object(g, 'verify_emission', return_value={}), \
         mock.patch.object(g, 'generated_witness', side_effect=RuntimeError('no diagnostic witness')):
        return g.run(REPO, base / 'work', phase,
                     {'verilator_root': '/tmp/tools', 'backend': {'path': '/tmp/tools/bin/verilator_bin'},
                      'configured_runtime': {}, 'host_programs': {}}, {'sv': {}},
                     base / 'idma', base / 'retained', base / 'config',
                     stop_after_generation=True, diagnostic_callback=callback)


class Cold(unittest.TestCase):
    def test_01_same_buffer_before_compile(self):
        for raw in (RAW+b'x',b'X'+RAW[1:]):
            with mock.patch.object(builtins,'compile',side_effect=RuntimeError('no compile')) as compiler:
                with self.assertRaisesRegex(ValueError,'before compile'):load(raw)
                compiler.assert_not_called()

    def test_02_no_native_or_network_imports_assert(self):
        nodes=list(ast.walk(ast.parse(RAW)))
        imports={a.name for n in nodes if isinstance(n,(ast.Import,ast.ImportFrom)) for a in n.names}
        self.assertFalse(imports & {'subprocess','requests','urllib','socket'})
        self.assertFalse(any(isinstance(n,ast.Assert) for n in nodes))

    def test_03_fixed_307_command(self):
        sources,includes,defines=g.parse_filelist(filelist())
        selected=[s for s in sources if s not in g.DROP]+['retained'+str(i)+'.sv' for i in range(13)]+[g.CLOCK,SV]
        self.assertEqual(len(selected),307)
        commands=g.commands(Path('/tmp/work'),{'path':'/tmp/tool/bin/verilator_bin'},{'sources':selected,'includes':includes,'defines':defines},Path('/tmp/config'))
        cmd=commands['host93_cpp_generate'];self.assertNotIn('--build',cmd);self.assertNotIn('-Wno-fatal',cmd)
        for flag,value in [('--threads','1'),('--build-jobs','1'),('--verilate-jobs','1'),('--output-split','3000'),('--output-split-cfuncs','200')]:self.assertEqual(cmd[cmd.index(flag)+1],value)
        self.assertEqual(commands['host93_cpp_compile'][0],'/usr/bin/make')
        self.assertEqual(commands['host93_reset_launch'],['/tmp/work/obj/VHostBlockTop'])

    def test_04_filelist_failclosed(self):
        for bad in (filelist()+b'-f /escape\n',filelist().replace(b'TARGET_ASIC',b'UNKNOWN'),filelist().replace(b'@ROOT@/deps/axi_stream/src/axi_stream_cut.sv\n',b''),filelist()+b'@ROOT@/../escape\n'):
            with self.assertRaises(ValueError):g.parse_filelist(bad)

    def test_05_scoped_constructor(self):
        result=g.initialized_endpoint(wrapper(),LEAF,LEXICAL);self.assertEqual(result['m_seqnum_initializer'],0)
        for bad in (wrapper().replace(b'm_seqnum{0}',b'm_seqnum{1}'),wrapper().replace(b'm_seqnum{0}',b'/*m_seqnum{0}*/'),b'namespace fake {\n'+wrapper()+b'}\n',wrapper()+wrapper()):
            with self.assertRaises(ValueError):g.initialized_endpoint(bad,LEAF,LEXICAL)

    def test_06_new_generated_positive(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);generated(root);result=witness(root)
            self.assertEqual(result['host_ports'],83);self.assertEqual(len(result['scopes']),8)
            self.assertFalse(result['eight_runtime_handles_verified'])

    def test_07_new_witness_wrong_initializer_scope_port_make(self):
        cases=[('obj/'+CHILD+'/'+LEAF+'.cpp',b'm_seqnum{0}',b'm_seqnum{7}'),('obj/VHostBlockTop___024root.h',b'leaves_7',b'leaves_8'),('obj/VHostBlockTop.h',b'io_launch_bits_descriptors,24,0',b'io_launch_bits_descriptors,23,0'),('obj/VHostBlockTop_hier.mk',b'VM_HIER_LIBS',b'OTHER')]
        for name,old,new in cases:
            with tempfile.TemporaryDirectory() as td:
                root=Path(td);generated(root);p=root/name;raw=p.read_bytes();self.assertIn(old,raw);p.write_bytes(raw.replace(old,new));
                with self.assertRaises(ValueError):witness(root)

    def test_08_missing_child_archive(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);generated(root)
            with self.assertRaises(ValueError):witness(root,True)

    def test_09_exact_limited_markers(self):
        self.assertEqual(g.check_log(LOG)['scope'],'REAL_RESET_AND_ONE_LAUNCH_EDGE_ONLY')
        for bad in (LOG.replace(b'handshakes=1',b'handshakes=2'),LOG.replace(b'high_edge=0',b'high_edge=16'),LOG+b'extra\n',LOG.replace(b'further_eval_calls=0',b'further_eval_calls=1')):
            with self.assertRaises(ValueError):g.check_log(bad)

    def test_10_cpp_direct_and_stop_boundary(self):
        text=BUFFERS['short_launch.cpp'].decode()
        self.assertIn('#include "VHostBlockTop.h"',text);self.assertIn('canonical_host_wiring_v1::launch_payload(d)',text)
        self.assertNotIn('dpi_forwarders',text);self.assertNotIn('.final()',text)
        self.assertIn('const bool fire = d.io_launch_valid && d.io_launch_ready;',text)
        tail=text[text.index('if (fire) {'):text.index('throw std::runtime_error("launch handshake bound")')]
        self.assertNotIn('evaluate(',tail);self.assertIn('return 0;',tail)
        for name,(direction,width) in PORTS.items():
            if direction=='input':self.assertIn('d.'+name,text)

    def test_11_limits(self):
        self.assertEqual(g.LIMITS['host93_cpp_generate']['work_seconds'],540)
        self.assertEqual(g.LIMITS['host93_cpp_compile']['work_seconds'],1740)
        self.assertEqual(g.LIMITS['host93_reset_launch']['as_bytes'],2*1024**3)
        self.assertEqual(g.LIMITS['host93_cpp_generate']['tree_bytes'],512*1024**2)

    def test_12_mixed_scope_fresh_rejection(self):
        with self.assertRaises(ValueError):
            g.run('/tmp/repo','/tmp/repo/work',lambda *x:None,{'verilator_root':'/tmp/tools'},{},Path('/tmp/idma'),Path('/tmp/retained'),Path('/tmp/config'))

    def test_13_mock_three_phase_end_to_end(self):
        with tempfile.TemporaryDirectory() as td:
            base=Path(td);work=base/'work';seen=[]
            before={'sv':{'path':SV},'sources':['s'+str(i) for i in range(307)],'includes':['i'+str(i) for i in range(8)],'defines':dict(g.DEFINES)}
            def phase(name,argv,cwd,environment,limits):
                seen.append(name)
                if name=='host93_cpp_generate':generated(work)
                if name=='host93_cpp_compile':
                    for p,data in [(work/'obj'/CHILD/('lib'+LEAF+'.a'),b'archive'),(work/'obj/VHostBlockTop__ALL.a',b'toparchive'),(work/'obj/VHostBlockTop',b'\x7fELFfake')]:p.write_bytes(data);p.chmod(0o700 if p.name=='VHostBlockTop' else 0o600)
                return {'record':{'exit_code':0,'cleanup_confirmed':True},'raw_log':LOG if name=='host93_reset_launch' else b'','usage':{},'evidence_root':str(base/name)}
            with mock.patch.object(g,'closure',return_value=before),mock.patch.object(g,'verify_tools',return_value={}),mock.patch.object(g,'verify_emission',return_value={}):
                result=g.run(REPO,work,phase,{'verilator_root':'/tmp/tools','backend':{'path':'/tmp/tools/bin/verilator_bin'},'configured_runtime':{},'host_programs':{}},{'sv':{}},base/'idma',base/'retained',base/'config')
            self.assertEqual(seen,list(g.LIMITS));self.assertEqual(result['source_count'],307)
            self.assertTrue((work/'RESULT.json').is_file());self.assertFalse((work/'FAILED.json').exists())

    def test_14_mock_failure_no_compile(self):
        with tempfile.TemporaryDirectory() as td:
            base=Path(td);work=base/'work';seen=[]
            before={'sv':{'path':SV},'sources':['s']*307,'includes':['i']*8,'defines':dict(g.DEFINES)}
            def phase(name,*args):seen.append(name);raise RuntimeError('synthetic failure')
            with mock.patch.object(g,'closure',return_value=before),mock.patch.object(g,'verify_tools',return_value={}),mock.patch.object(g,'verify_emission',return_value={}):
                with self.assertRaisesRegex(RuntimeError,'synthetic failure'):
                    g.run(REPO,work,phase,{'verilator_root':'/tmp/tools','backend':{'path':'/tmp/tools/bin/verilator_bin'},'configured_runtime':{},'host_programs':{}},{'sv':{}},base/'idma',base/'retained',base/'config')
            self.assertEqual(seen,['host93_cpp_generate']);self.assertTrue((work/'FAILED.json').is_file())


    def test_15_generation_only_success_one_phase_callback_no_cpp_or_elf(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td); seen = []; callbacks = []
            def phase(name, argv, cwd, environment, limits):
                seen.append(name)
                self.assertNotIn('-Wno-fatal', argv)
                self.assertEqual(limits, g.LIMITS['host93_cpp_generate'])
                return {'record': {'exit_code': 0, 'cleanup_confirmed': True},
                        'raw_log': b'', 'usage': {}, 'evidence_root': str(base / name)}
            result = diagnostic_run(base, phase, lambda work, sources: callbacks.append((work, sources)))
            self.assertEqual(seen, ['host93_cpp_generate'])
            self.assertEqual(len(callbacks), 1); self.assertEqual(callbacks[0][0], base / 'work')
            self.assertEqual(len(callbacks[0][1]), 307)
            self.assertTrue(result['diagnostic_only']); self.assertFalse(result['host_qualification_claim'])
            self.assertEqual(list(result['phases']), seen)
            self.assertNotIn('elf', result); self.assertNotIn('generated_witness', result)
            self.assertNotIn('qualification', result)
            self.assertTrue((base / 'work/GENERATION_ONLY_RESULT.json').is_file())
            self.assertTrue((base / 'work/INPUTS_AFTER.json').is_file())
            self.assertFalse((base / 'work/RESULT.json').exists())
            self.assertFalse((base / 'work/FAILED.json').exists())
            self.assertEqual(list((base / 'work/obj').iterdir()), [])

    def test_16_generation_failure_callback_preserves_native_exception(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td); seen = []; callbacks = []; failure = RuntimeError('native generation failure')
            def phase(name, *args):
                seen.append(name)
                raise failure
            with self.assertRaises(RuntimeError) as caught:
                diagnostic_run(base, phase, lambda work, sources: callbacks.append((work, sources)))
            self.assertIs(caught.exception, failure)
            self.assertEqual(seen, ['host93_cpp_generate']); self.assertEqual(len(callbacks), 1)
            self.assertTrue((base / 'work/FAILED.json').is_file())
            self.assertFalse((base / 'work/GENERATION_ONLY_RESULT.json').exists())
            self.assertEqual(list((base / 'work/obj').iterdir()), [])

    def test_17_callback_failure_does_not_mask_native_exception(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td); failure = RuntimeError('original native failure'); callbacks = []
            def phase(*args): raise failure
            def callback(work, sources):
                callbacks.append(work)
                raise ValueError('secondary callback failure')
            with self.assertRaises(RuntimeError) as caught: diagnostic_run(base, phase, callback)
            self.assertIs(caught.exception, failure); self.assertEqual(len(callbacks), 1)
            failed = json.loads((base / 'work/FAILED.json').read_text())
            self.assertEqual(failed['error']['message'], 'original native failure')

    def test_18_callback_failure_after_native_success_fails_gate(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td); seen = []; callbacks = []
            def phase(name, *args):
                seen.append(name)
                return {'record': {'exit_code': 0, 'cleanup_confirmed': True},
                        'raw_log': b'', 'usage': {}, 'evidence_root': str(base / name)}
            def callback(work, sources):
                callbacks.append(work)
                raise ValueError('callback failed after native success')
            with self.assertRaisesRegex(ValueError, 'callback failed after native success'):
                diagnostic_run(base, phase, callback)
            self.assertEqual(seen, ['host93_cpp_generate']); self.assertEqual(len(callbacks), 1)
            self.assertTrue((base / 'work/FAILED.json').is_file())
            self.assertFalse((base / 'work/GENERATION_ONLY_RESULT.json').exists())

    def test_19_generation_option_explicit_bool_and_callback_pairing(self):
        for stop, callback in ((1, lambda *x: None), (0, None), ('true', lambda *x: None),
                               (None, None), (True, None), (True, 42), (False, lambda *x: None)):
            with mock.patch.object(g, 'load', side_effect=RuntimeError('must guard before loading')) as loader:
                with self.assertRaises(ValueError):
                    g.run('/tmp/repo', '/tmp/work', lambda *x: None, {}, {}, '/tmp/idma',
                          '/tmp/retained', '/tmp/config', stop_after_generation=stop,
                          diagnostic_callback=callback)
                loader.assert_not_called()

    def test_20_exact_307_diagnostic_aliases_and_hashes(self):
        base = Path('/tmp/diagnostic-inputs'); before = generation_inputs(base)
        sources = g.generation_source_map(before, base / 'idma', base / 'retained')
        self.assertEqual(len(sources), 307)
        self.assertEqual([row['path'] for row in sources], before['sources'])
        self.assertEqual(len({row['id'] for row in sources}), 307)
        self.assertEqual(sum(row['id'].startswith('idma/') for row in sources), 293)
        self.assertEqual(sum(row['id'].startswith('retained/') for row in sources), 13)
        for row in sources:
            self.assertEqual(set(row), {'path', 'id', 'bytes', 'sha256'})
            self.assertFalse(row['id'].startswith('/')); self.assertNotIn(str(base), row['id'])
            if row['id'].startswith('idma/'):
                expected = before['idma_tree']['entries'][row['id'][5:]]
            elif row['id'].startswith('retained/'):
                expected = before['retained_tree']['entries'][row['id'][9:]]
            else:
                self.assertEqual(row['id'], 'host/HostBlockCollection.sv'); expected = before['sv']
            self.assertEqual(row['bytes'], expected['bytes']); self.assertEqual(row['sha256'], expected['sha256'])
        for bad_path in ('/tmp/not-in-verified-closure.sv', '/tmp/diagnostic-inputs/idma/sources/../escape.sv'):
            bad = dict(before); bad['sources'] = before['sources'][:-1] + [bad_path]
            with self.assertRaises(ValueError): g.generation_source_map(bad, base / 'idma', base / 'retained')
        bad = dict(before); bad['sources'] = before['sources'][:-1] + [before['sources'][0]]
        with self.assertRaises(ValueError): g.generation_source_map(bad, base / 'idma', base / 'retained')
        before['idma_tree']['entries']['rtl/source_0.sv']['sha256'] = 'not-a-digest'
        with self.assertRaises(ValueError): g.generation_source_map(before, base / 'idma', base / 'retained')

    def test_21_nonzero_generation_record_still_calls_callback_and_fails(self):
        for callback_fails in (False, True):
            with tempfile.TemporaryDirectory() as td:
                base = Path(td); seen = []; callbacks = []
                def phase(name, *args):
                    seen.append(name)
                    return {'record': {'exit_code': 1, 'cleanup_confirmed': True},
                            'raw_log': b'warning fatal', 'usage': {}, 'evidence_root': str(base / name)}
                def callback(work, sources):
                    callbacks.append(work)
                    if callback_fails: raise RuntimeError('secondary callback failure')
                with self.assertRaisesRegex(ValueError, 'phase failed or cleanup unconfirmed'):
                    diagnostic_run(base, phase, callback)
                self.assertEqual(seen, ['host93_cpp_generate']); self.assertEqual(len(callbacks), 1)
                self.assertTrue((base / 'work/FAILED.json').is_file())
                self.assertEqual(list((base / 'work/obj').iterdir()), [])

    def assert_receipt_failure_preserves(self, native_failure):
        with tempfile.TemporaryDirectory() as td:
            base=Path(td);failure=RuntimeError('original failure');original_save=g.save
            def save(path, value):
                if path.name=='FAILED.json':raise OSError('receipt disk failure')
                return original_save(path,value)
            def phase(name,*args):
                if native_failure:raise failure
                return {'record':{'exit_code':0,'cleanup_confirmed':True},'raw_log':b'', 'usage':{},'evidence_root':str(base/name)}
            def callback(work,sources):
                if not native_failure:raise failure
            with mock.patch.object(g,'save',side_effect=save), self.assertRaises(RuntimeError) as caught:
                diagnostic_run(base,phase,callback)
            self.assertIs(caught.exception,failure)
    def test_22_failed_receipt_preserves_native_exception(self):
        self.assert_receipt_failure_preserves(True)
    def test_23_failed_receipt_preserves_callback_exception(self):
        self.assert_receipt_failure_preserves(False)




class DerivedFifoClosureCold(unittest.TestCase):
    def fixture(self, variant, mutate=None):
        idma, retained, config = map(Path, ('/tmp/cluster-idma', '/tmp/cluster-retained', '/tmp/cluster-config'))
        sources = sorted(g.DROP) + [g.FIFO_PATH] + ['source/s'+str(i)+'.sv' for i in range(291)]
        admitted = {name:'1'*64 for name in sources + [g.CLOCK] + ['include/h'+str(i)+'.svh' for i in range(17)]}
        admitted[g.FIFO_PATH] = g.FIFO_BASE[1]
        extra = ['idma.f.in','SHA256SUMS.json','SOURCE_CLOSURE.json'] + ['meta'+str(i)+'.json' for i in range(4)]
        sums = {**admitted, **{name:'2'*64 for name in extra}}
        sums.update({'unselected/'+str(i):'3'*64 for i in range(927-len(sums))})
        actual = {name:{'kind':'regular','bytes':0,'sha256':digest,'mode':'0o600'} for name,digest in sums.items() if not name.startswith('unselected/')}
        actual['SHA256SUMS.json']['sha256'] = g.IDMA_META['SHA256SUMS.json'][1]
        fifo = g.FIFO_SPLIT if variant else g.FIFO_BASE
        actual[g.FIFO_PATH].update(bytes=fifo[0],sha256=fifo[1])
        itree = {'root':str(idma/'sources'),'entries':actual,'bytes':3072200+(251 if variant else 0)}
        expected13 = {'retained/r'+str(i)+'.sv':'4'*64 for i in range(13)}
        rtree = {'root':str(retained/'source'),'entries':{n:{'kind':'regular','bytes':0,'sha256':v,'mode':'0o600'} for n,v in expected13.items()},'bytes':0}
        content = {name:(g.CLUSTER_HIERARCHY if name=='hierarchy.vlt' and variant else b'old fixed fixture') for name in g.CONFIG_NAMES}
        ctree = {'root':str(config),'entries':{n:{'kind':'regular','bytes':len(raw),'sha256':g.sha(raw),'mode':'0o600'} for n,raw in content.items()},'bytes':sum(map(len,content.values()))}
        ctree['entries']['MANIFEST.json']={'kind':'regular','bytes':1,'sha256':'5'*64,'mode':'0o600'}
        manifest={'readonly_count':610,'precision_warning_directives':21,'sv':{'bytes':g.SV_PIN[0],'sha256':g.SV_PIN[1]},'files':{n:{'bytes':v['bytes'],'sha256':v['sha256']} for n,v in ctree['entries'].items() if n!='MANIFEST.json'}}
        state={'actual':actual,'tree':itree,'sums':sums,'admitted':admitted,'content':content}
        if mutate: mutate(state)
        encoded=lambda obj:json.dumps(obj).encode()
        def read(p,size,digest):
            p=Path(p)
            if p==idma/'sources/SHA256SUMS.json':return encoded(sums)
            if p==idma/'sources/SOURCE_CLOSURE.json':return encoded({'admitted_input_hashes':admitted,'initial_filelist_defines':g.DEFINES})
            if p==idma/'sources/idma.f.in':return b'fixed mocked filelist'
            if p==config/'hierarchy.vlt':
                raw=content['hierarchy.vlt']
                if len(raw)!=size or g.sha(raw)!=digest:raise ValueError('wrong fixed hierarchy bytes')
                return raw
            raise ValueError('unexpected fixture read')
        trees={str(idma/'sources'):itree,str(retained/'source'):rtree,str(config):ctree}
        support=types.SimpleNamespace(tree_inventory=lambda root,*args:trees[str(root)],identity=lambda *args:{'bytes':g.SV_PIN[0],'sha256':g.SV_PIN[1],'mode':'0o600'})
        buffers={g.RETAINED_PLAN:encoded({'expected13':expected13,'source_order':list(expected13)})}
        with mock.patch.object(g,'small_read',side_effect=read),mock.patch.object(g,'json_current',return_value=(manifest,None)),mock.patch.object(g,'parse_filelist',return_value=(sources,['include/'+str(i) for i in range(8)],g.DEFINES)):
            return g.closure(support,idma,retained,config,{'path':'/tmp/same-host.sv','bytes':g.SV_PIN[0],'sha256':g.SV_PIN[1]},buffers,fifo_valid_split=variant)

    def test_original_and_exact_derived_closures(self):
        for variant in (False,True):
            result=self.fixture(variant)
            self.assertEqual(len(result['sources']),307)
            self.assertEqual(len(result['idma_tree']['entries']),319)
            self.assertEqual(result['idma_tree']['bytes'],3072200+(251 if variant else 0))
    def test_derived_rejects_base_wrong_identity_or_other_change(self):
        edits=(lambda x:x['actual'][g.FIFO_PATH].update(bytes=g.FIFO_BASE[0],sha256=g.FIFO_BASE[1]),
               lambda x:x['actual'][g.FIFO_PATH].update(bytes=4663),
               lambda x:x['actual'][g.FIFO_PATH].update(sha256='0'*64),
               lambda x:x['sums'].update({g.FIFO_PATH:'0'*64}),
               lambda x:x['admitted'].update({g.FIFO_PATH:'0'*64}),
               lambda x:x['actual']['source/s0.sv'].update(sha256='0'*64),
               lambda x:x['actual'].pop('source/s0.sv'),
               lambda x:x['tree'].update(bytes=3072200),
               lambda x:x['content'].update({'hierarchy.vlt':b'`verilator_config\nhier_block -module "qwen2_matrix_command_endpoint"\n'}))
        for index,edit in enumerate(edits):
            with self.subTest(index=index):
                with self.assertRaises(ValueError):self.fixture(True,edit)
    def test_default_rejects_derived_fifo(self):
        with self.assertRaises(ValueError):self.fixture(False,lambda x:x['actual'][g.FIFO_PATH].update(bytes=g.FIFO_SPLIT[0],sha256=g.FIFO_SPLIT[1]))
    def test_generation_only_calls_use_exact_derived_flag(self):
        import ast
        source=ast.parse(RAW)
        run=next(n for n in source.body if isinstance(n,ast.FunctionDef) and n.name=='run')
        calls=[n for n in ast.walk(run) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='closure']
        self.assertEqual(len(calls),5)
        self.assertEqual(sum(any(k.arg=='fifo_valid_split' and isinstance(k.value,ast.Name) and k.value.id=='variant' for k in c.keywords) for c in calls),5)



CLUSTER_TEST_LEAF = g.CLUSTER_MODULE + '_3'

def cluster_fixture(root):
    leaf = CLUSTER_TEST_LEAF; child = 'V' + leaf
    with mock.patch.dict(globals(), {'LEAF': leaf, 'CHILD': child}):
        generated(root)
    p = root / ('obj/' + child + '__hierMkArgs.f')
    p.write_bytes(("--prefix " + child + " --mod-prefix " + child +
                   " --lib-create " + leaf + " --hierarchical-child 1 --top-module-encoded " + leaf +
                   " -GENABLE_ACCUMULATOR_SEED=1\\'h1\n").encode())
    (root / 'obj/VHostBlockTop___024root.h').write_bytes(b'unknown root syntax; must not be parsed\n')


def cluster_census(root):
    leaf = CLUSTER_TEST_LEAF; child = 'V' + leaf
    def ident(path):
        raw = (root / path).read_bytes()
        return {'bytes': len(raw), 'sha256': g.sha(raw)}
    return {'state': 'AVAILABLE', 'scan_complete': True,
            'counts': dict.fromkeys(('warning_headers','error_headers','fatal_summary_headers','example_paths','unparsed_headers'), 0),
            'records': [], 'by_rule': {}, 'omission': {'records':0,'examples':0},
            'caps': dict.fromkeys(('record_cap','example_cap','report_byte_cap','partial'), False),
            'wrapper': {'state':'AVAILABLE','module':g.CLUSTER_MODULE,'candidate_count':1,'hierarchical_child':1,
                        'top_references_wrapper':True,'syntax_state':'FINITE_PARSE_AVAILABLE',
                        'specialization':'UNKNOWN','combo_input_count':18,'combo_output_count':2,
                        'dpi_import_count':6,'combo_update_import_count':1,'combo_update_call_count':1,
                        'always_comb_count':2,'args_identity':ident('obj/'+child+'__hierMkArgs.f'),
                        'top_args_identity':ident('obj/VHostBlockTop__hierMkArgs.f'),
                        'wrapper_identity':ident('obj/'+child+'/'+leaf+'.sv'),
                        'cluster_structure': {'makegraph_state':'AVAILABLE','library_target_count':1,
                            'matching_library_target_count':1,'makegraph_identity':ident('obj/VHostBlockTop_hier.mk'),
                            'root_header_state':'UNRECOGNIZED_SYNTAX','instance_handle_count':None,
                            'handle_declaration_count':None,'expected_structure_observed':False}}}


def cluster_invoke(base, phase, callback):
    before = generation_inputs(base)
    with mock.patch.object(g, 'closure', return_value=before) as check_closure, \
         mock.patch.object(g, 'verify_tools', return_value={}), \
         mock.patch.object(g, 'verify_emission', return_value={}), \
         mock.patch.object(g, 'generated_witness', side_effect=RuntimeError('legacy endpoint witness forbidden')):
        result = g.run(REPO, base/'work', phase,
            {'verilator_root':'/tmp/tools','backend':{'path':'/tmp/tools/bin/verilator_bin'},
             'configured_runtime':{},'host_programs':{}}, {'sv':{}},
            base/'idma', base/'retained', base/'config', cluster_boundary=True, diagnostic_callback=callback)
        if not all(call.kwargs == {'fifo_valid_split':True} for call in check_closure.call_args_list):
            raise RuntimeError('derived closure not preserved at every gate')
        return result


class ClusterContinuation(unittest.TestCase):
    def execute_fixture(self, base, fail=None, mutate=None, callback_edit=None, callback_error=None):
        work = base/'work'; seen=[]; callbacks=[]
        failure = RuntimeError('native first failure')
        def phase(name, argv, cwd, environment, bound):
            seen.append(name)
            self.assertEqual(bound, g.LIMITS[name])
            if name == 'host93_cpp_generate': cluster_fixture(work)
            if name == fail: raise failure
            if name == 'host93_cpp_compile':
                leaf = CLUSTER_TEST_LEAF
                for name, data in [('obj/V'+leaf+'/lib'+leaf+'.a',b'archive'),
                                   ('obj/VHostBlockTop__ALL.a',b'toparchive'),
                                   ('obj/VHostBlockTop',b'\x7fELFfake')]:
                    p=work/name;p.write_bytes(data);p.chmod(0o700 if p.name=='VHostBlockTop' else 0o600)
            if mutate is not None: mutate(seen[-1],work)
            return {'record':{'exit_code':0,'cleanup_confirmed':True},
                    'raw_log':LOG if seen[-1]=='host93_reset_launch' else b'',
                    'usage':{},'evidence_root':str(base/seen[-1])}
        def callback(work, source_map):
            callbacks.append((work, source_map))
            if callback_error is not None: raise callback_error
            report=cluster_census(work)
            if callback_edit is not None: callback_edit(report)
            return report
        return lambda: cluster_invoke(base, phase, callback),seen,callbacks,failure

    def test_cluster_three_phases_same_closure_callback_once_unknown_handles(self):
        with tempfile.TemporaryDirectory() as td:
            base=Path(td); run,seen,callbacks,_=self.execute_fixture(base)
            original=g.generated_text
            def forbid_root(*args,**kwargs):
                self.assertNotEqual(args[2], 'obj/VHostBlockTop___024root.h')
                return original(*args,**kwargs)
            with mock.patch.object(g,'generated_text',side_effect=forbid_root): result=run()
            self.assertEqual(seen,list(g.LIMITS));self.assertEqual(len(callbacks),1)
            self.assertEqual(len(callbacks[0][1]),307)
            witness=result['generated_witness']
            self.assertIsNone(witness['instance_handle_count'])
            self.assertFalse(witness['runtime_handles_verified']);self.assertFalse(witness['root_header_parsed'])
            self.assertFalse(result['ram_or_weights_or_n0_or_full_block_claim'])
            self.assertEqual(result['qualification']['scope'],'REAL_RESET_AND_ONE_LAUNCH_EDGE_ONLY')
            self.assertFalse((base/'work/GENERATION_ONLY_RESULT.json').exists())

    def test_cluster_each_native_failure_stops_and_callback_only_generation(self):
        for failed in g.LIMITS:
            with self.subTest(failed=failed), tempfile.TemporaryDirectory() as td:
                run,seen,callbacks,failure=self.execute_fixture(Path(td),fail=failed)
                with self.assertRaises(RuntimeError) as caught:run()
                self.assertIs(caught.exception,failure)
                self.assertEqual(seen,list(g.LIMITS)[:list(g.LIMITS).index(failed)+1])
                self.assertEqual(len(callbacks),1)

    def test_cluster_native_exception_wins_callback_exception(self):
        with tempfile.TemporaryDirectory() as td:
            run,seen,callbacks,failure=self.execute_fixture(Path(td),fail='host93_cpp_generate',callback_error=ValueError('secondary'))
            with self.assertRaises(RuntimeError) as caught:run()
            self.assertIs(caught.exception,failure);self.assertEqual(len(callbacks),1)

    def test_cluster_callback_exception_blocks_compile(self):
        with tempfile.TemporaryDirectory() as td:
            secondary=ValueError('secondary')
            run,seen,callbacks,_=self.execute_fixture(Path(td),callback_error=secondary)
            with self.assertRaises(ValueError) as caught:run()
            self.assertIs(caught.exception,secondary);self.assertEqual(seen,['host93_cpp_generate'])

    def test_cluster_census_failure_blocks_compile_with_label(self):
        with tempfile.TemporaryDirectory() as td:
            run,seen,callbacks,_=self.execute_fixture(Path(td),callback_edit=lambda x:x.update(state='CONTRACT_ERROR'))
            with self.assertRaises(ValueError) as caught:run()
            self.assertEqual(seen,['host93_cpp_generate'])
            self.assertEqual(caught.exception.safe_contract_boundary,g.CLUSTER_CONTRACT_BOUNDARY)
            self.assertEqual(caught.exception.safe_contract_code,'CLUSTER_CENSUS')

    def test_cluster_census_rejects_each_count_cap_and_shape(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);cluster_fixture(root);report=cluster_census(root)
            self.assertTrue(g.validate_cluster_census(report))
            edits=[lambda x:x.update(state='CONTRACT_ERROR'),lambda x:x.update(scan_complete=False),
                   lambda x:x['wrapper'].update(candidate_count=2),lambda x:x['wrapper'].update(candidate_count=True),
                   lambda x:x['wrapper'].update(module='qwen2_matrix_command_endpoint'),
                   lambda x:x['wrapper'].update(top_references_wrapper=False),
                   lambda x:x['wrapper'].update(syntax_state='UNRECOGNIZED_SYNTAX'),
                   lambda x:x['wrapper']['cluster_structure'].update(library_target_count=2),
                   lambda x:x['wrapper']['cluster_structure'].update(makegraph_state='UNRECOGNIZED_SYNTAX')]
            edits += [lambda x,k=k:x['counts'].update({k:1}) for k in report['counts']]
            edits += [lambda x,k=k:x['caps'].update({k:True}) for k in report['caps']]
            edits += [lambda x,k=k:x['wrapper'].update({k:99}) for k in ('combo_input_count','combo_output_count','dpi_import_count','combo_update_import_count','combo_update_call_count','always_comb_count')]
            for edit in edits:
                bad=copy.deepcopy(report);edit(bad)
                with self.assertRaises(ValueError) as caught:g.validate_cluster_census(bad)
                self.assertEqual(caught.exception.safe_contract_code,'CLUSTER_CENSUS')
            for bad in (None,{},[],{'state':'AVAILABLE','scan_complete':True},
                        {**report,'counts':None}, {**report,'caps':None}, {**report,'wrapper':None}):
                with self.assertRaises(ValueError):g.validate_cluster_census(bad)

    def test_cluster_witness_rejects_args_link_initializer_abi_artifacts(self):
        leaf=CLUSTER_TEST_LEAF;child='V'+leaf
        cases=[('obj/'+child+'__hierMkArgs.f',b'--hierarchical-child 1',b'--hierarchical-child 2','CLUSTER_CHILD_ARGS'),
               ('obj/'+child+'__hierMkArgs.f',b'\n',b' -GENABLE_ACCUMULATOR_SEED=1\n','CLUSTER_CHILD_ARGS'),
               ('obj/VHostBlockTop__hierMkArgs.f',SV.encode(),b'/tmp/other.sv','CLUSTER_TOP_LINK'),
               ('obj/VHostBlockTop.mk',b'include',b'omit','CLUSTER_LIBRARY_GRAPH'),
               ('obj/'+child+'/'+leaf+'.cpp',b'm_seqnum{0}',b'm_seqnum{1}','CLUSTER_INITIALIZER'),
               ('obj/'+child+'/'+leaf+'.cpp',b'_protectlib_final',b'_missing_final','CLUSTER_INITIALIZER'),
               ('obj/VHostBlockTop.h',b'io_launch_bits_descriptors,24,0',b'io_launch_bits_descriptors,23,0','CLUSTER_ABI')]
        for name,old,new,code in cases:
            with self.subTest(code=code,name=name),tempfile.TemporaryDirectory() as td:
                root=Path(td);cluster_fixture(root);p=root/name;raw=p.read_bytes();self.assertIn(old,raw);p.write_bytes(raw.replace(old,new))
                with self.assertRaises(ValueError) as caught:g.cluster_generated_witness(SUPPORT,tree(root),LEXICAL,PORTS,cluster_census(root),False,SV)
                self.assertEqual(caught.exception.safe_contract_code,code)
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);cluster_fixture(root)
            with self.assertRaises(ValueError) as caught:g.cluster_generated_witness(SUPPORT,tree(root),LEXICAL,PORTS,cluster_census(root),True,SV)
            self.assertEqual(caught.exception.safe_contract_code,'CLUSTER_ARTIFACTS')

    def test_cluster_census_identity_binding_rejects_drift(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);cluster_fixture(root);report=cluster_census(root)
            p=root/('obj/V'+CLUSTER_TEST_LEAF+'/'+CLUSTER_TEST_LEAF+'.sv');p.write_bytes(p.read_bytes()+b'\n')
            with self.assertRaises(ValueError) as caught:g.cluster_generated_witness(SUPPORT,tree(root),LEXICAL,PORTS,report,False,SV)
            self.assertEqual(caught.exception.safe_contract_code,'CLUSTER_INITIALIZER')

    def test_cluster_generated_source_drift_during_compile_stops_reset(self):
        def mutate(phase,work):
            if phase=='host93_cpp_compile':
                p=work/'obj/VHostBlockTop.h';p.write_bytes(p.read_bytes()+b'\n')
        with tempfile.TemporaryDirectory() as td:
            run,seen,callbacks,_=self.execute_fixture(Path(td),mutate=mutate)
            with self.assertRaisesRegex(ValueError,'generated source changed after phase'):run()
            self.assertEqual(seen,list(g.LIMITS)[:2])

    def test_cluster_elf_drift_around_reset_rejected(self):
        def mutate(phase,work):
            if phase=='host93_reset_launch':(work/'obj/VHostBlockTop').write_bytes(b'\x7fELFchanged')
        with tempfile.TemporaryDirectory() as td:
            run,seen,callbacks,_=self.execute_fixture(Path(td),mutate=mutate)
            with self.assertRaisesRegex(ValueError,'ELF changed around execution'):run()
            self.assertEqual(seen,list(g.LIMITS))

    def test_cluster_flags_rejected_before_load(self):
        for stop,cluster,callback in ((True,True,lambda *x:None),(False,1,lambda *x:None),(False,None,None),(False,True,None),(False,True,42)):
            with mock.patch.object(g,'load',side_effect=RuntimeError('must not load')) as loader:
                with self.assertRaises(ValueError):
                    g.run('/tmp/repo','/tmp/work',lambda *x:None,{}, {}, '/tmp/idma','/tmp/retained','/tmp/config',stop_after_generation=stop,cluster_boundary=cluster,diagnostic_callback=callback)
                loader.assert_not_called()

    def test_cluster_constructor_scope_and_comments_fail_closed(self):
        with mock.patch.dict(globals(),{'LEAF':CLUSTER_TEST_LEAF,'CHILD':'V'+CLUSTER_TEST_LEAF}):raw=wrapper()
        self.assertEqual(g.initialized_cluster(raw,LEXICAL,CLUSTER_TEST_LEAF)['m_seqnum_initializer'],0)
        for bad in (raw+raw,b'namespace fake {\n'+raw+b'}\n',raw.replace(b'm_seqnum{0}',b'/*m_seqnum{0}*/')):
            with self.assertRaises(ValueError):g.initialized_cluster(bad,LEXICAL,CLUSTER_TEST_LEAF)


    def test_cluster_parameter_hash_and_all_finite_prefixes(self):
        expected = hashlib.sha512((g.CLUSTER_MODULE+'_ENABLE_ACCUMULATOR_SEED=1').encode('ascii')).hexdigest()
        self.assertEqual(g.CLUSTER_PARAMETER_HASH,expected)
        for length in range(1,128):
            self.assertTrue(g.valid_cluster_leaf(g.CLUSTER_MODULE+'_'+expected[:length]))
        for suffix in ('','a','3a','30C',expected,expected+'0','../3','_3'):
            self.assertFalse(g.valid_cluster_leaf(g.CLUSTER_MODULE+'_'+suffix))
        self.assertFalse(g.valid_cluster_leaf(g.CLUSTER_MODULE))
        self.assertFalse(g.valid_cluster_leaf(None))
        for length in (1,2,64,127):
            with self.subTest(length=length),tempfile.TemporaryDirectory() as td, \
                 mock.patch.dict(globals(),{'CLUSTER_TEST_LEAF':g.CLUSTER_MODULE+'_'+expected[:length]}):
                root=Path(td);cluster_fixture(root)
                result=g.cluster_generated_witness(SUPPORT,tree(root),LEXICAL,PORTS,cluster_census(root),False,SV)
                self.assertEqual(result['leaf'],CLUSTER_TEST_LEAF)
                self.assertEqual(result['accumulator_seed_parameter'],1)

    def test_cluster_rejects_unsuffixed_nonprefix_and_excessive_child(self):
        for leaf in (g.CLUSTER_MODULE,g.CLUSTER_MODULE+'_a',g.CLUSTER_MODULE+'_3a',
                     g.CLUSTER_MODULE+'_'+g.CLUSTER_PARAMETER_HASH,g.CLUSTER_MODULE+'_30C'):
            with self.subTest(leaf=leaf),tempfile.TemporaryDirectory() as td, \
                 mock.patch.dict(globals(),{'CLUSTER_TEST_LEAF':leaf}):
                root=Path(td);cluster_fixture(root)
                with self.assertRaises(ValueError) as caught:
                    g.cluster_generated_witness(SUPPORT,tree(root),LEXICAL,PORTS,cluster_census(root),False,SV)
                self.assertEqual(caught.exception.safe_contract_code,'CLUSTER_CHILD_ARGS')

    def test_cluster_requires_exact_one_typed_seed_argument(self):
        original=b"-GENABLE_ACCUMULATOR_SEED=1\\'h1"
        alternatives=(b'',b'-GENABLE_ACCUMULATOR_SEED=0',b"-GENABLE_ACCUMULATOR_SEED=1\\'h0",
                      b'-GENABLE_ACCUMULATOR_SEED=1',b"-GENABLE_ACCUMULATOR_SEED=32\\'h1",
                      b"-GENABLE_ACCUMULATOR_SEED=1\\'b1",b'-G ENABLE_ACCUMULATOR_SEED=1',
                      original+b' '+original,original+b' -GUNKNOWN=1',
                      original+b' --hierarchical-params-file /tmp/unknown')
        for replacement in alternatives:
            with self.subTest(replacement=replacement),tempfile.TemporaryDirectory() as td:
                root=Path(td);cluster_fixture(root)
                p=root/('obj/V'+CLUSTER_TEST_LEAF+'__hierMkArgs.f');raw=p.read_bytes()
                self.assertIn(original,raw);p.write_bytes(raw.replace(original,replacement))
                with self.assertRaises(ValueError) as caught:
                    g.cluster_generated_witness(SUPPORT,tree(root),LEXICAL,PORTS,cluster_census(root),False,SV)
                self.assertEqual(caught.exception.safe_contract_code,'CLUSTER_CHILD_ARGS')

    def test_cluster_child_prefix_aliases_must_all_match(self):
        for flag in ('--prefix','--mod-prefix','--lib-create','--top-module-encoded'):
            with self.subTest(flag=flag),tempfile.TemporaryDirectory() as td:
                root=Path(td);cluster_fixture(root)
                p=root/('obj/V'+CLUSTER_TEST_LEAF+'__hierMkArgs.f');raw=p.read_bytes()
                name=('V' if flag in ('--prefix','--mod-prefix') else '')+CLUSTER_TEST_LEAF
                old=(flag+' '+name).encode();self.assertIn(old,raw)
                p.write_bytes(raw.replace(old,(flag+' '+name+'0').encode()))
                with self.assertRaises(ValueError) as caught:
                    g.cluster_generated_witness(SUPPORT,tree(root),LEXICAL,PORTS,cluster_census(root),False,SV)
                self.assertEqual(caught.exception.safe_contract_code,'CLUSTER_CHILD_ARGS')

    def test_cluster_mismatched_wrapper_constructor_or_archive_is_rejected(self):
        leaf=CLUSTER_TEST_LEAF;child='V'+leaf
        for name,old,new,code in (
                ('obj/VHostBlockTop__hierMkArgs.f',(child+'/'+leaf+'.sv').encode(),b'Vother/other.sv','CLUSTER_TOP_LINK'),
                ('obj/'+child+'/'+leaf+'.cpp',(child+'_container').encode(),(child+'0_container').encode(),'CLUSTER_INITIALIZER')):
            with self.subTest(code=code),tempfile.TemporaryDirectory() as td:
                root=Path(td);cluster_fixture(root);p=root/name;p.write_bytes(p.read_bytes().replace(old,new))
                with self.assertRaises(ValueError) as caught:
                    g.cluster_generated_witness(SUPPORT,tree(root),LEXICAL,PORTS,cluster_census(root),False,SV)
                self.assertEqual(caught.exception.safe_contract_code,code)
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);cluster_fixture(root)
            for name in ('obj/'+child+'/lib'+leaf+'0.a','obj/VHostBlockTop__ALL.a','obj/VHostBlockTop'):
                (root/name).write_bytes(b'artifact')
            with self.assertRaises(ValueError) as caught:
                g.cluster_generated_witness(SUPPORT,tree(root),LEXICAL,PORTS,cluster_census(root),True,SV)
            self.assertEqual(caught.exception.safe_contract_code,'CLUSTER_ARTIFACTS')

if __name__=='__main__':unittest.main()
