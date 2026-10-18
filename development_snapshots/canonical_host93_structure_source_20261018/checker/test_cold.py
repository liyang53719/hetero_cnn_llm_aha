"""Synthetic-only parser/checker tests; no Java, EDA, external model, or pyc load."""
import hashlib
from pathlib import Path
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
CHECKER_SHA256 = 'b3301dd40718e4b05fe7f233747235bff1ae3b142c38a2221a481310431bd2a0'
raw = (HERE / 'check_host_chirrtl.py').read_bytes()
if hashlib.sha256(raw).hexdigest() != CHECKER_SHA256:
    raise ValueError('fixed checker source drift')
C = {'__name__':'cold_checker', '__file__':str(HERE / 'check_host_chirrtl.py')}
exec(compile(raw, str(HERE / 'check_host_chirrtl.py'), 'exec'), C)


def channel(fields):
    return '{ flip ready : UInt<1>, valid : UInt<1>, bits : { ' + ', '.join(k+' : UInt<'+str(w)+'>' for k,w in fields.items()) + ' } }'


def fixture():
    """Synthetic full-shaped fixture, never an actual Host artifact or model."""
    rq = {'write':1,'address':64,'data':512,'mask':64,'tag':64}
    rs = {'data':512,'tag':64,'error':1}
    rec = {'tableBase':64,'tableLimit':64,'entryCount':25,'index':24,'requestTag':64}
    res = {'data':128,'requestTag':64,'status':8}
    # Build nested bundle+vector public IO, not pre-flattened pseudo-SV ports.
    tree = {}
    for name,(direction,width) in C['HOST_PORTS'].items():
        if name in ('clock','reset'): continue
        parts = name.split('_')[1:]; t = tree
        for part in parts[:-1]: t = t.setdefault(part,{})
        t[parts[-1]] = (direction,width)
    def typ(tree):
        if isinstance(tree,tuple):
            if tree[0] != "output": raise ValueError("fixture vector input unsupported")
            return "UInt<"+str(tree[1])+">"
        if set(tree) == set(str(i) for i in range(len(tree))):
            child = typ(tree['0'])
            if any(typ(value) != child for value in tree.values()): raise ValueError('nonuniform fixture vector')
            return child+'['+str(len(tree))+']'
        fields = []
        for name,value in tree.items():
            if isinstance(value,tuple): fields.append(('flip ' if value[0]=='input' else '')+name+' : UInt<'+str(value[1])+'>')
            else: fields.append(name+' : '+typ(value))
        return '{ '+', '.join(fields)+' }'
    mods = {}
    for path, module in C['EXPECTED_PATHS'].items(): mods[module] = []
    mods['HostBlockCollection'] = ['inst '+n+' of '+m for n,m in C['SIBLINGS'].items()]
    mods['HostBlockTop'] = []
    for path,module in C['EXPECTED_PATHS'].items():
        parent,_,name = path.rpartition('.')
        parentmodule = C['EXPECTED_PATHS'][parent] if parent else 'HostBlockTop'
        mods[parentmodule].append('inst '+name+' of '+module)
    for short,mod in [('endpoint','qwen2_matrix_command_endpoint'),('gate','tc_clk_gating')]:
        mods[mod] = []
        mods['QwenOwnerKernel'] += ['inst '+short+str(i)+' of '+mod for i in range(8)]
    for path,taps in C['TAPS'].items():
        mods[C['EXPECTED_PATHS'][path]] += ['wire '+name+' : '+t for name,t in taps.items()]
    for mod in list(C['SIBLINGS'].values())[1:]: mods[mod] = ['wire result : UInt<1>', 'connect result, UInt<1>(0h0)']
    ports = {
        'HostBlockTop': 'output io : '+typ(tree),
        'HostBlockCommands': 'output io : { memory : '+channel(rq)+', flip response : '+channel(rs)+' }',
        'QwenOwnerKernel': 'output io : { memory : '+channel(rq)+', flip response : '+channel(rs)+' }',
        'Record128Reader':'output io : { memory : '+channel(rq)+', flip response : '+channel(rs)+', flip request : '+channel(rec)+', result : '+channel(res)+' }',
        'TypedTensorReader':'output io : { record : '+channel(rec)+', flip recordResult : '+channel(res)+' }',
        'SharedMemoryArbiter':'output io : { flip requests : '+channel(rq)+'[2], responses : '+channel(rs)+'[2], memory : '+channel(rq)+', flip response : '+channel(rs)+' }',
        'RetainedIdmaWeightBurstAdapter':'output io : { flip request : '+channel(rq)+', response : '+channel(rs)+' }',
    }
    def route(mod,sink,source,fields):
        mods[mod] += ['connect '+source+'.ready, '+sink+'.ready', 'connect '+sink+'.valid, '+source+'.valid']
        mods[mod] += ['connect '+sink+'.bits.'+field+', '+source+'.bits.'+field for field in fields]
    for sink,source,fields in [
        ('hub.io.requests[0]','cmd.io.memory',rq),('cmd.io.response','hub.io.responses[0]',rs),
        ('hub.io.requests[1]','owner.io.memory',rq),('owner.io.response','hub.io.responses[1]',rs),
        ('dma.io.request','hub.io.memory',rq),('hub.io.response','dma.io.response',rs)]: route('HostBlockTop',sink,source,fields)
    route('HostBlockCommands','io.memory','reader.io.memory',rq)
    route('HostBlockCommands','reader.io.response','io.response',rs)
    mods['HostBlockCommands'] += ['connect reader.io.request.bits, tensor.io.record.bits', 'connect tensor.io.recordResult.bits, reader.io.result.bits']
    lines = ['FIRRTL version 3.3.0','circuit HostBlockCollection :']
    for name,body in mods.items():
        ext = name in ('qwen2_matrix_command_endpoint','tc_clk_gating','idma_backend_rw_axi_flat_wrap')
        lines.append('  '+('extmodule' if ext else 'module')+' '+name+' :')
        lines.append('    input clock : Clock')
        if name=='HostBlockTop': lines.append('    input reset : UInt<1>')
        if name in ports: lines.append('    '+ports[name])
        if ext: lines.append('    defname = '+name)
        else:
            for statement in body or ['skip']: lines.append('    '+statement)
    return ('\n'.join(lines)+'\n').encode()


def bulk_fixture():
    """Same tiny synthetic topology; eight channel routes use typed aggregates."""
    raw = fixture()
    for sink, source, fields in [
        ('hub.io.requests[0]', 'cmd.io.memory', C['REQUEST']),
        ('cmd.io.response', 'hub.io.responses[0]', C['RESPONSE']),
        ('hub.io.requests[1]', 'owner.io.memory', C['REQUEST']),
        ('owner.io.response', 'hub.io.responses[1]', C['RESPONSE']),
        ('dma.io.request', 'hub.io.memory', C['REQUEST']),
        ('hub.io.response', 'dma.io.response', C['RESPONSE']),
        ('io.memory', 'reader.io.memory', C['REQUEST']),
        ('reader.io.response', 'io.response', C['RESPONSE']),
    ]:
        lines = ['connect '+source+'.ready, '+sink+'.ready',
                 'connect '+sink+'.valid, '+source+'.valid']
        lines += ['connect '+sink+'.bits.'+field+', '+source+'.bits.'+field for field in fields]
        original = ''.join('    '+line+'\n' for line in lines).encode()
        if raw.count(original) != 1: raise ValueError('synthetic bulk route anchor')
        raw = raw.replace(original, ('    connect '+sink+', '+source+'\n').encode())
    return raw


class Cold(unittest.TestCase):
    def reject(self, raw, text=None):
        if text is None:
            with self.assertRaises((ValueError,UnicodeDecodeError)): C['check_bytes'](raw)
        else:
            with self.assertRaisesRegex(ValueError,text): C['check_bytes'](raw)

    def test_synthetic_complete_shape(self):
        raw = fixture(); result = C['check_bytes'](raw)
        self.assertEqual(result['sha256'],hashlib.sha256(raw).hexdigest())
        self.assertEqual(result['bytes'],len(raw))
        self.assertEqual(result['host_port_count'],83)
        self.assertEqual(result['observation_bundles'],9)
        self.assertEqual(result['observation_bits'],2604)
        self.assertFalse(result['job_launched'])
        self.assertFalse(result['rtl_verified'])
        self.assertFalse(result['tap_event_semantics_proved'])
        with tempfile.TemporaryDirectory() as td:
            p = Path(td)/'synthetic.fir'; p.write_bytes(raw)
            self.assertEqual(C['check'](p)['sha256'],result['sha256'])
            self.assertEqual(p.read_bytes(),raw)

    def test_primitive_named_reference_targets(self):
        # The parent observed this exact instance reference form in the actual
        # parser failure. This is separately constructed tiny synthetic text.
        suffix = b'''    inst add of AddRecFN
    regreset head : UInt<8>, clock, UInt<1>(0h0), UInt<8>(0h0)
    regreset tail : UInt<1>, clock, UInt<1>(0h0), UInt<1>(0h0)
    connect add.io.subOp, UInt<1>(0h0)
    connect head, UInt<8>(0h0)
    connect tail, UInt<1>(0h0)
    invalidate add.io.subOp
    invalidate head
    invalidate tail
  module AddRecFN :
    input io : { subOp : UInt<1> }
    skip
'''
        raw = fixture() + suffix
        result = C['check_bytes'](raw)
        self.assertEqual(result['status'], 'PASS')
        self.assertEqual(result['sha256'], hashlib.sha256(raw).hexdigest())
        circuit, modules = C['parse_ir'](raw.decode())
        drivers = modules['HeteroBF16FmaRound']['connects']
        for target in ('add.io.subOp', 'head', 'tail'):
            self.assertEqual(sum(lhs == target for lhs, rhs, conditional in drivers), 2)
            self.assertIn((target, None, False), drivers)

    def test_reference_target_call_literal_boundary(self):
        for keyword in (b'connect', b'invalidate'):
            for target in (b'add(a, b)', b'head(a, 1)', b'tail(a, 1)',
                           b'UInt<1>(0h0)', b'SInt<1>(0h0)', b'UInt(0h0)',
                           b'foo(a)'):
                with self.subTest(keyword=keyword, target=target):
                    statement = keyword + b' ' + target
                    if keyword == b'connect': statement += b', UInt<1>(0h0)'
                    self.reject(fixture() + b'    ' + statement + b'\n',
                                keyword.decode() + ' target must be a reference')

    def test_bulk_forward_and_flipped_ready(self):
        raw = bulk_fixture()
        result = C['check_bytes'](raw)
        self.assertEqual(result['status'], 'PASS')
        self.assertEqual(result['metadata_direct_request_response_routes'], 8)
        self.assertEqual(result['sha256'], hashlib.sha256(raw).hexdigest())
        self.assertIn(b'    connect hub.io.requests[0], cmd.io.memory\n', raw)
        self.assertNotIn(b'connect cmd.io.memory.ready, hub.io.requests[0].ready', raw)
        _, modules = C['parse_ir'](raw.decode())
        for dest, src in [('cmd.io.memory.ready', 'hub.io.requests[0].ready'),
                          ('hub.io.requests[0].valid', 'cmd.io.memory.valid'),
                          ('hub.io.requests[0].bits.data', 'cmd.io.memory.bits.data')]:
            C['require_direct'](modules, 'HostBlockTop', dest, src)

    def test_bulk_schema_flip_and_unknown_type_rejected(self):
        raw = bulk_fixture()
        header = b'output io : { memory : { flip ready : UInt<1>, valid : UInt<1>, bits : {'
        self.assertIn(header, raw)
        for changed in [
            header.replace(b'flip ready', b'ready'),
            header.replace(b'flip ready : UInt<1>', b'flip ready : UInt<2>'),
            header.replace(b'valid : UInt<1>,', b'valid : UInt<1>, extra : UInt<1>,'),
            header.replace(b'valid : UInt<1>,', b'valid : UInt<1>, flip extra : UInt<1>,'),
            header.replace(b'valid : UInt<1>,', b'valid : UInt,'),
        ]:
            with self.subTest(changed=changed): self.reject(raw.replace(header, changed, 1))
        anchor = b'    connect hub.io.requests[0], cmd.io.memory\n'
        self.reject(raw.replace(anchor, b'    connect hub.io.requests[0], unknownPort\n'))
        self.reject(raw.replace(anchor, b'    connect hub.io.requests[0], cmd.io.response\n'))
        # Both aggregate sides with the same unknown projected width still fail.
        unknown = raw.replace(b'data : UInt<128>, requestTag', b'data : UInt, requestTag')
        self.assertEqual(raw.count(b'data : UInt<128>, requestTag'), 2)
        self.reject(unknown, 'metadata aggregate leaf type mismatch')

    def test_bulk_reverse_overrides_and_invalidates_rejected(self):
        raw = bulk_fixture()
        anchor = b'    connect hub.io.requests[0], cmd.io.memory\n'
        for extra in [
            b'    connect cmd.io.memory.ready, hub.io.requests[0].ready\n',
            b'    connect cmd.io.memory.ready, UInt<1>(0h0)\n',
            b'    connect hub.io.requests[0].valid, cmd.io.memory.valid\n',
            b'    connect hub.io.requests[0].bits.data, UInt<512>(0h0)\n',
            b'    when UInt<1>(0h1) :\n      connect hub.io.requests[0].valid, cmd.io.memory.valid\n',
            b'    invalidate hub.io.requests[0].bits\n',
            b'    when UInt<1>(0h1) :\n      connect cmd.io.memory.ready, hub.io.requests[0].ready\n',
            anchor,
            b'    when UInt<1>(0h1) :\n      connect hub.io.requests[0], cmd.io.memory\n',
            b'    invalidate cmd.io.memory.ready\n',
            b'    invalidate cmd.io.memory\n',
            b'    when UInt<1>(0h1) :\n      invalidate cmd.io.memory.ready\n',
        ]:
            with self.subTest(extra=extra): self.reject(raw.replace(anchor, anchor + extra), 'metadata direct binding')

    def test_bulk_ground_rhs_is_not_reverse_driver(self):
        raw = bulk_fixture()
        anchor = b'    connect hub.io.requests[0], cmd.io.memory\n'
        backwards = b'    connect hub.io.requests[0].ready, cmd.io.memory.ready\n'
        self.reject(raw.replace(anchor, backwards), 'reverse ground metadata target')
        self.reject(raw.replace(anchor, anchor + backwards), 'reverse ground metadata target')

    def test_bulk_dynamic_rhs_alias_rejected(self):
        raw = bulk_fixture()
        anchor = b'    connect hub.io.requests[0], cmd.io.memory\n'
        extra = b'    connect cmd.io.response, hub.io.responses[io_pc]\n'
        changed = raw.replace(anchor, anchor + extra)
        _, modules = C['parse_ir'](changed.decode())
        self.assertIn(('cmd.io.response', '@dynamic:hub.io.responses', False), modules['HostBlockTop']['connects'])
        self.reject(changed, r'dynamic metadata driver hub.io.responses\[0\].ready')
        with self.assertRaisesRegex(ValueError, r'dynamic metadata driver hub.io.responses\[0\].ready'):
            C['require_direct'](modules, 'HostBlockTop', 'hub.io.responses[0].ready', 'cmd.io.response.ready')
        self.reject(raw.replace(anchor, anchor + b'    connect hub.io.requests[0], owner.io[io_pc]\n'), 'dynamic metadata driver')

    def test_flip_vector_nested_and_order(self):
        t = C['parse_type']('{ flip outer : { flip back : UInt<7>, normal : UInt<5>[2] }, plain : SInt<13> }')
        self.assertEqual(C['leaves'](t),{'outer.back':(False,'UInt',7),'outer.normal[0]':(True,'UInt',5),'outer.normal[1]':(True,'UInt',5),'plain':(False,'SInt',13)})
        mod={'ports':{'io':('input',t)}}
        self.assertEqual(C['flat_ports'](mod)['io_outer_normal_1'],['output',5])

    def test_83_mutations(self):
        for old,new in [(b'commands : UInt<16>',b'commands : UInt<17>'),(b'flip commandBase',b'commandBase'),(b'memoryAccepted',b'memoryAcceptEd'),(b'output io :',b'input io :')]:
            with self.subTest(new=new): self.reject(fixture().replace(old,new,1))

    def test_tap_mutations(self):
        for old,new in [(b'wire canonicalScoreTap',b'reg canonicalScoreTap'),(b'keyBase : UInt<16>',b'keyBase : UInt<17>'),(b'canonicalPvAckTap',b'canonicalPVAckTap'),(b'canonicalLoanContextTap : { active',b'canonicalLoanContextTap : { flip active')]:
            with self.subTest(new=new): self.reject(fixture().replace(old,new,1))
        self.reject(fixture()+b'    wire canonicalExtraTap : UInt<1>\n')

    def test_namespace_and_real_identities(self):
        for old,new in [(b'circuit HostBlockCollection',b'circuit ProductionBench'),(b'inst pre of HeteroBF16FmaPre',b'inst pre of HeteroBF16FmaMul'),(b'defname = tc_clk_gating',b'defname = FakeGate'),(b'inst endpoint7 of qwen2_matrix_command_endpoint\n',b''),(b'inst backend of idma_backend_rw_axi_flat_wrap',b'inst backEnd of idma_backend_rw_axi_flat_wrap')]:
            with self.subTest(new=new): self.reject(fixture().replace(old,new,1))
        self.reject(fixture()+b'  module HostBlockTop :\n    skip\n','duplicate')
        extra = fixture().replace(b'inst endpoint7 of qwen2_matrix_command_endpoint', b'inst endpoint7 of qwen2_matrix_command_endpoint\n    inst alias of AliasEndpoint') + b'  extmodule AliasEndpoint :\n    input clock : Clock\n    defname = qwen2_matrix_command_endpoint\n'
        self.reject(extra, 'alias count')
        self.reject(fixture()+b'  module Disconnected :\n    skip\n','orphan')

    def test_metadata_wrong_and_overridden(self):
        self.reject(fixture().replace(b'connect hub.io.requests[0].valid, cmd.io.memory.valid',b'connect hub.io.requests[0].valid, owner.io.memory.valid'))
        self.reject(fixture().replace(b'connect hub.io.requests[0].valid, cmd.io.memory.valid',b'connect hub.io.requests[0].valid, cmd.io.memory.valid\n    connect hub.io.requests[0].valid, UInt<1>(0h0)'))
        self.reject(fixture().replace(b'connect hub.io.requests[0].valid, cmd.io.memory.valid',b'when UInt<1>(0h1) :\n      connect hub.io.requests[0].valid, cmd.io.memory.valid'))
        self.reject(fixture().replace(b'connect reader.io.request.bits, tensor.io.record.bits',b'connect reader.io.request.bits, UInt<1>(0h0)'))
        self.reject(fixture().replace(b'connect hub.io.requests[0].valid, cmd.io.memory.valid',b'connect hub.io.requests[0].valid, cmd.io.memory.valid\n    connect hub.io.requests[io_pc].valid, UInt<1>(0h0)'))

    def test_unknown_syntax_fail_preserves_file(self):
        for syntax in [b'unknown foo',b'wire x : Probe<UInt<1>>',b'node x = mystery(UInt<1>(0h0))',b'wire x : { a : UInt<1>, a : UInt<2> }',b'wire x : UInt<1> junk',b'inst newone of Missing',b'connect foo, ???',b'else :\n      skip',b'connect add(a, b), UInt<1>(0h0)']:
            with self.subTest(syntax=syntax):
                raw=fixture()+b'    '+syntax+b'\n'
                with tempfile.TemporaryDirectory() as td:
                    path=Path(td)/'failed.fir';path.write_bytes(raw)
                    with self.assertRaises(ValueError):C['check'](path)
                    self.assertEqual(path.read_bytes(),raw)

    def test_reviewed_four_invalidate_drivers_rejected(self):
        raw = fixture()
        anchor = b'    connect hub.io.requests[0].valid, cmd.io.memory.valid\n'
        self.assertEqual(raw.count(anchor), 1)
        mutations = {
            'extra_leaf_invalidate': raw.replace(anchor, anchor + b'    invalidate hub.io.requests[0].valid\n'),
            'extra_aggregate_invalidate': raw.replace(anchor, anchor + b'    invalidate hub.io.requests[0].bits\n'),
            'extra_conditional_invalidate': raw.replace(anchor, anchor + b'    when UInt<1>(0h1) :\n      invalidate hub.io.requests[0].valid\n'),
            'extra_dynamic_invalidate': raw.replace(anchor, anchor + b'    invalidate hub.io.requests[io_pc].valid\n'),
        }
        for name, changed in mutations.items():
            with self.subTest(name=name):
                self.reject(changed, 'metadata direct binding|dynamic metadata driver')
        for target in (b'UInt<1>(0h0)', b'add(a, b)', b'foo?', b'foo(a)'):
            with self.subTest(target=target):
                self.reject(raw.replace(anchor, anchor + b'    invalidate ' + target + b'\n'))

    def test_unrelated_invalidate_remains_admitted(self):
        raw = fixture() + b'    wire unrelated : UInt<1>\n    invalidate unrelated\n'
        self.assertEqual(C['check_bytes'](raw)['status'], 'PASS')

    def test_reviewed_record_reader_external_stub_rejected(self):
        # Exact fifth mutation from the independent review, expectation corrected.
        lines = fixture().decode().splitlines()
        start = lines.index('  module Record128Reader :')
        end = next(i for i in range(start + 1, len(lines)) if lines[i].startswith('  ') and not lines[i].startswith('    '))
        block = lines[start:end]
        ports = [line for line in block[1:] if line.startswith('    input ') or line.startswith('    output ')]
        changed = ('\n'.join(lines[:start] + ['  extmodule Record128Reader :'] + ports + ['    defname = ExternalReaderStub'] + lines[end:]) + '\n').encode()
        self.reject(changed, 'hierarchy definition kind')

    def test_inline_donttouch_annotation_profile(self):
        payload = b'[\n  {"class":"firrtl.transforms.DontTouchAnnotation","target":"~HostBlockCollection|HostBlockTop>io"}\n]'
        annotated = fixture().replace(b'circuit HostBlockCollection :\n', b'circuit HostBlockCollection :%[' + payload + b']\n', 1)
        result = C['check_bytes'](annotated)
        self.assertEqual(result['annotation_count'], 1)
        self.assertEqual(result['annotation_bytes'], len(payload))
        self.assertEqual(result['annotation_sha256'], hashlib.sha256(payload).hexdigest())
        self.assertEqual(result['sha256'], hashlib.sha256(annotated).hexdigest())
        normalized, info = C['strip_inline_annotations'](annotated.decode())
        self.assertEqual(annotated.count(b'\n'), normalized.count('\n'))
        self.assertEqual(C['check_bytes'](fixture())['annotation_count'], 0)
        self.assertIsNone(C['check_bytes'](fixture())['annotation_sha256'])
        for changed in [
            payload.replace(b'"class":', b'"extra":0,"class":'),
            payload.replace(b'"class":', b'"target":"~HostBlockCollection|X","class":'),
            payload.replace(b'firrtl.transforms.DontTouchAnnotation', b'unknown.Annotation'),
            payload.replace(b'"~HostBlockCollection|HostBlockTop>io"', b'null'),
            payload.replace(b'~HostBlockCollection|', b'~Other|'),
            b'[0]', b'{}', b'[NaN]', b'[[[]]]', payload[:-1],
        ]:
            with self.subTest(changed=changed):
                self.reject(fixture().replace(b'circuit HostBlockCollection :\n', b'circuit HostBlockCollection :%[' + changed + b']\n', 1))
        for ending in [b'garbage]\n', b']]\n', b'] garbage\n', b']\nunknown\n', b']', b']\n\n']:
            with self.subTest(ending=ending):
                self.reject(fixture().replace(b'circuit HostBlockCollection :\n', b'circuit HostBlockCollection :%[' + payload + ending, 1))
        old = C['MAX_ANNOTATION_BYTES']; C['MAX_ANNOTATION_BYTES'] = 8
        try: self.reject(annotated)
        finally: C['MAX_ANNOTATION_BYTES'] = old
        old = C['MAX_ANNOTATIONS']; C['MAX_ANNOTATIONS'] = 0
        try: self.reject(annotated, 'array/count/type')
        finally: C['MAX_ANNOTATIONS'] = old

    def test_known_expression_and_statement_syntax(self):
        suffix = b'''    wire x : UInt
    reg r : UInt<4>, clock
    regreset rr : UInt<1>, clock, UInt<1>(0h0), UInt<1>(0h0)
    node n = bits(add(UInt<4>(0h1), UInt<4>(0h2)), 3, 0)
    smem m : UInt<32>[16], undefined
    read mport mp = m[UInt<4>(0h0)], clock
    when eq(rr, UInt<1>(0h0)) :
      connect x, n
    else :
      invalidate x
    printf(clock, UInt<1>(0h0), "synthetic=%d", n) : p
    assert(clock, UInt<1>(0h1), UInt<1>(0h0), "synthetic") : a
'''
        self.assertEqual(C['check_bytes'](fixture()+suffix)['status'],'PASS')

    def test_expansion_and_depth_caps(self):
        with self.assertRaises(ValueError):C['leaves'](C['parse_type']('UInt<1>[32769]'))
        with self.assertRaises(ValueError):C['parse_type']('{ x : '*34+'UInt<1>'+' }'*34)
        self.reject(fixture().replace(b'inst cmd of HostBlockCommands',b'inst cmd of HostBlockTop'),'recursive')
        # Tiny fixtures test definition/path boundaries by reducing local cap.
        old=C['MAX_DEFINITIONS']; C['MAX_DEFINITIONS']=2
        try:self.reject(fixture(),'definition cap')
        finally:C['MAX_DEFINITIONS']=old
        old=C['MAX_PATHS'];C['MAX_PATHS']=5
        try:self.reject(fixture(),'path cap')
        finally:C['MAX_PATHS']=old

    def test_flat_collision_and_unresolved_width(self):
        for t in ['{ a_b : UInt<1>, a : { b : UInt<1> } }','{ a : UInt }']:
            with self.assertRaises(ValueError):C['flat_ports']({'ports':{'io':('output',C['parse_type'](t))}})

    def test_invalid_and_symlink_inputs(self):
        for raw in [b'',b'\xff',b'\x00',b'circuit X :\n']:
            self.reject(raw)
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'x.fir';p.write_bytes(fixture());link=Path(td)/'link.fir';link.symlink_to(p)
            with self.assertRaises(OSError):C['check'](link)
            with self.assertRaises(ValueError):C['check'](Path(td))
            sparse=Path(td)/'oversize.fir'
            with sparse.open('wb') as f:f.truncate(C['MAX_BYTES']+1)
            with self.assertRaises(ValueError):C['check'](sparse)


if __name__ == '__main__':
    unittest.main(verbosity=2)
