"""Pure source/tiny mocks; no subprocess, native compiler, real SV or network."""
import sys
if not (sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode):
    raise SystemExit('Use -I -S -B')
import ast
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
SIZE = 28183
SHA = '93c2305bd0fddc22a6a7113c5e1e7d6617152e13ec30f7a2a9bdb02cd4f38c88'
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

if __name__=='__main__':unittest.main()
