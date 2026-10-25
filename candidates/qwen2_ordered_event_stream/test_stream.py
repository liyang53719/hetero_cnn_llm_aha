"""Pure stdlib synthetic lifecycle tests. No DUT modules, ELF or tensors."""
import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import sys
import tempfile
import threading
import types
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('candidate_stream', HERE/'stream.py')
stream = importlib.util.module_from_spec(spec)
spec.loader.exec_module(stream)
OLD = HERE / 'reference_functions.py'
OLD_SHA = '9d16d949cb39a302250c1563c61b97ff94bb3146407574a97968132d4df109cc'


def fixture(rows=1, ticket_start=37):
    """Exact event schema/frequencies; numerical hashes are synthetic strings."""
    edge = 0
    ticket = ticket_start
    tag = 10
    def event(name, values):
        nonlocal edge
        edge += 1
        return name, edge, values
    def group(profile, steps):
        nonlocal ticket, tag
        tag += 1
        yield event('accept_group', (0x23 if profile == 2 else 0x24, steps, tag, 255 if profile == 2 else 1, profile))
        for i in range(steps):
            last = i + 1 == steps
            yield event('accept_step', (i, 0, i == 0, last, last, last if profile == 2 else True, format(edge, '064x')))
            if profile == 0 or last:
                yield event('retire_result', (0, last, False, ticket, 0, format(edge, '064x')))
                if last:
                    yield event('retire_done', (tag, False, ticket, 0))
                if profile == 0:
                    yield event('retire_legacy_reply', (ticket, 0))
        ticket += 1
    yield event('acquire', ('normal', 12))
    for token in range(rows):
        for head in range(12):
            for first in range(0, token + 1, 16):
                yield from group(2, 8)
            for col in range(0, 128, 16):
                yield from group(0, token + 1)
    yield event('retire_owner_response', ())
    yield event('release', ())


def limits(rows=1):
    groups, events = stream.profile_counts(rows)
    return dict(expected_groups=groups, expected_events=events, max_events=events+64, max_bytes=64*1024**2)


def old_function(name):
    raw = OLD.read_bytes()
    if hashlib.sha256(raw).hexdigest() != OLD_SHA:
        raise ValueError('old reference code changed')
    tree = ast.parse(raw)
    nodes = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == name]
    if len(nodes) != 1:
        raise ValueError('old function identity')
    scope = dict(need=stream.need, sys=sys, threading=threading, hashlib=hashlib, struct=struct)
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(OLD), 'exec'), scope)
    return scope[name]


class StreamTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.events = tuple(fixture())
    def tearDown(self):
        self.temp.cleanup()
    def write(self, events=None, name='events.bin', bound=None):
        target = self.root/name
        w = stream.EventWriter(target, **(bound or limits()))
        for event in self.events if events is None else events:
            w.append(event)
        receipt = w.seal()
        return target, receipt
    def rejected(self, edit):
        events = list(self.events)
        edit(events)
        w = stream.EventWriter(self.root/'bad.bin', **limits())
        try:
            with self.assertRaises((ValueError, OSError)):
                for e in events:
                    w.append(e)
                w.seal()
        finally:
            w.close_incomplete()
        self.assertFalse(w.sealed)
    def mutate_payload(self, events, name, index, value, occurrence=0):
        positions = [i for i,e in enumerate(events) if e[0] == name]
        pos = positions[occurrence]
        n, edge, raw = events[pos]
        values = list(raw); values[index] = value
        events[pos] = n, edge, tuple(values)
    def test_exact_raw_roundtrip(self):
        p, receipt = self.write()
        self.assertEqual(tuple(stream.replay(p, **limits())), self.events)
        self.assertEqual(receipt['count'], len(self.events))
        self.assertTrue(stream.artifact_evidence(receipt, p)['complete'])
    def test_old_canonical_exact_equivalence(self):
        for rows in (1, 2, 16):
            events = tuple(fixture(rows))
            p, _ = self.write(events, name='m%d.bin'%rows, bound=limits(rows))
            self.assertEqual(tuple(stream.replay(p, canonical=True, **limits(rows))), old_function('canonical_events')(events))
    def test_ticket_alpha_bijection(self):
        p, _ = self.write(name='a.bin')
        q, _ = self.write(fixture(ticket_start=999), name='b.bin')
        self.assertFalse(stream.equal(p,q,limits=limits()))
        self.assertTrue(stream.equal(p,q,limits=limits(),canonical=True))
    def test_group_ticket_collision(self):
        self.rejected(lambda es:self.mutate_payload(es,'retire_result',3,37,1))
    def test_foreign_result(self):
        # A later response in a multi-step legacy group may not introduce a ticket.
        es=list(fixture(2));positions=[i for i,e in enumerate(es) if e[0]=='retire_result' and not e[2][1]]
        i=positions[0]+3; self.assertEqual(es[i][0],'retire_result')
        n,e,v=es[i];v=list(v);v[3]+=1;es[i]=n,e,tuple(v)
        w=stream.EventWriter(self.root/'foreign.bin',**limits(2))
        try:
            with self.assertRaisesRegex(ValueError,'foreign result'):
                for e in es:w.append(e)
                w.seal()
        finally:w.close_incomplete()
    def test_foreign_done(self):
        self.rejected(lambda es:self.mutate_payload(es,'retire_done',2,999999))
    def test_foreign_legacy_reply(self):
        self.rejected(lambda es:self.mutate_payload(es,'retire_legacy_reply',0,999999))
    def test_duplicate_result(self):
        self.rejected(lambda es:es.insert(10,es[9]))
    def test_duplicate_done(self):
        self.rejected(lambda es:es.insert(11,es[10]))
    def test_step_order(self):
        self.rejected(lambda es:self.mutate_payload(es,'accept_step',0,1))
    def test_edge_order(self):
        self.rejected(lambda es:es.__setitem__(10,(es[10][0],0,es[10][2])))
    def test_early_owner_reply(self):
        self.rejected(lambda es:es.insert(3,('retire_owner_response',3,())))
    def test_abort_is_failure(self):
        self.rejected(lambda es:es.insert(2,('abort',2,())))
    def test_multiple_owner_rejected(self):
        self.rejected(lambda es:es.insert(2,('acquire',2,('normal',12))))
    def test_epoch_change_rejected(self):
        self.rejected(lambda es:self.mutate_payload(es,'retire_result',4,1,1))
    def test_ticket_domain_wrap_rejected(self):
        self.rejected(lambda es:self.mutate_payload(es,'retire_result',3,stream.U64,0))
    def test_profile_and_mask_rejected(self):
        self.rejected(lambda es:self.mutate_payload(es,'accept_group',3,1,0))
    def test_short_or_corrupt_files(self):
        p, _ = self.write();raw=p.read_bytes()
        for name, bad in [('nofooter',raw[:-44]),('shortfooter',raw[:-1]),('shortrecord',raw[:35]),('extra',raw+b'x'),('hash',raw[:-1]+bytes([raw[-1]^1]))]:
            q=self.root/name;q.write_bytes(bad)
            with self.subTest(name=name), self.assertRaises(ValueError):tuple(stream.replay(q,**limits()))
    def test_wrong_count_and_oversize(self):
        p,_=self.write()
        bad=limits();bad['expected_events']-=1
        with self.assertRaises(ValueError):tuple(stream.replay(p,**bad))
        bad=limits();bad['max_bytes']=52
        with self.assertRaises(ValueError):tuple(stream.replay(p,**bad))
    def test_no_materialization(self):
        w=stream.EventWriter(self.root/'no.bin',**limits())
        try:
            with self.assertRaises(TypeError):tuple(w)
        finally:w.close_incomplete()
    def test_short_write_preserves_partial(self):
        w=stream.EventWriter(self.root/'partial.bin',**limits());real=w.file
        class Short:
            def write(self,data):return real.write(data[:7])
            def close(self):real.close()
        w.file=Short()
        with self.assertRaises(OSError):w.append(self.events[0])
        w.close_incomplete();receipt=w.snapshot()
        self.assertFalse(receipt['complete']);self.assertGreater((self.root/'partial.bin').stat().st_size,8)
        self.assertFalse(stream.artifact_evidence(receipt,self.root/'partial.bin')['complete'])
    def test_existing_callback_write_failure_does_not_change_return(self):
        w=stream.EventWriter(self.root/'iofail.bin',**limits());w.append(self.events[0]);real=w.file
        class Broken:
            def write(self,data):raise OSError('injected write failure')
            def close(self):real.close()
        w.file=Broken()
        callback=old_function('_return');key=object()
        tracer=types.SimpleNamespace(events=w,error=None,thread=threading.get_ident(),codes={key:'accept_group'},stopped=False)
        def stop():tracer.stopped=True
        tracer.stop=stop
        class Service:
            def accept_group(self,owner,group):
                callback(tracer,key,0,True)
                return True
        service=Service();tracer.service=service
        owner=types.SimpleNamespace(clock=2);group=types.SimpleNamespace(opcode=0x23,steps=8,tag=11,slice_mask=255,profile=2)
        self.assertTrue(service.accept_group(owner,group));self.assertTrue(tracer.stopped)
        self.assertIn('injected write failure',tracer.error);self.assertFalse(w.sealed)
        w.close_incomplete()
    def test_unsealed_partial_refuses_acceptance(self):
        w=stream.EventWriter(self.root/'partial.bin',**limits());w.append(self.events[0]);w.close_incomplete()
        with self.assertRaises(ValueError):tuple(stream.replay(w.path,**limits()))
    def test_exclusive_new_file(self):
        self.write()
        old=(self.root/'events.bin').read_bytes()
        w=stream.EventWriter(self.root/'events.bin',**limits())
        self.assertFalse(w.created);self.assertIn('FileExistsError',w.error)
        self.assertEqual((self.root/'events.bin').read_bytes(),old)
        self.assertFalse(stream.artifact_evidence(w.snapshot(),w.path)['created'])
    def test_abort_and_foreign_keep_complete_raw_cleanup_tail(self):
        for kind in ('abort', 'foreign'):
            events=list(self.events)
            if kind=='abort':events.insert(2,('abort',2,()))
            else:self.mutate_payload(events,'retire_done',2,999999)
            w=stream.EventWriter(self.root/(kind+'.bin'),**limits())
            for event in events:w.append(event)
            self.assertIsNone(w.error)
            self.assertIsNotNone(w.audit_error)
            with self.assertRaisesRegex(ValueError,'lifecycle rejected'):w.seal()
            receipt=w.snapshot()
            self.assertTrue(receipt['raw_complete']);self.assertFalse(receipt['complete'])
            self.assertEqual(tuple(stream.replay_raw(w.path,max_events=limits()['max_events'],max_bytes=limits()['max_bytes'])),tuple(events))
            self.assertEqual(events[-2][0],'retire_owner_response');self.assertEqual(events[-1][0],'release')
            self.assertFalse(stream.artifact_evidence(receipt,w.path)['complete'])
            with self.assertRaises(ValueError):stream.verify(w.path,**limits())
    def test_raw_capacity_failure_marks_exact_prefix(self):
        bound=limits();bound['max_events']=bound['expected_events']
        w=stream.EventWriter(self.root/'cap.bin',**bound)
        for e in self.events:w.append(e)
        with self.assertRaisesRegex(ValueError,'capacity'):w.append(('abort',99999,()))
        w.close_incomplete();r=w.snapshot()
        self.assertFalse(r['raw_complete']);self.assertEqual(r['event_attempts'],r['count']+1)
        self.assertTrue(r['first_event_sha256']);self.assertTrue(r['last_event_sha256']);self.assertTrue(r['failed_event_sha256'])
    def test_seal_flush_fsync_close_failure_is_incomplete(self):
        from unittest.mock import patch
        for method in ('flush','fsync','close'):
            w=stream.EventWriter(self.root/(method+'.bin'),**limits())
            for event in self.events:w.append(event)
            real=w.file
            class Fault:
                def write(self,data):return real.write(data)
                def fileno(self):return real.fileno()
                def flush(self):
                    if method=='flush':raise OSError('injected flush')
                    return real.flush()
                def close(self):
                    real.close()
                    if method=='close':raise OSError('injected close')
            w.file=Fault()
            with patch.object(stream.os,'fsync',side_effect=OSError('injected fsync')) if method=='fsync' else patch.object(stream.os,'fsync',wraps=stream.os.fsync):
                with self.assertRaises(OSError):w.seal()
            self.assertFalse(w.raw_complete);self.assertFalse(w.sealed);self.assertTrue(w.error)
            w.close_incomplete() # no second close/retry, no propagated capture fault
    def test_header_and_open_failure_are_receipts_not_driver_errors(self):
        from unittest.mock import patch
        w=stream.EventWriter(self.root/'missing'/'events.bin',**limits())
        self.assertFalse(w.created);self.assertTrue(w.error)
        real=stream.EventWriter._write
        def fail_header(writer,data):
            if data==stream.MAGIC:raise OSError('injected header')
            return real(writer,data)
        with patch.object(stream.EventWriter,'_write',new=fail_header):
            w=stream.EventWriter(self.root/'header.bin',**limits())
        self.assertTrue(w.created);self.assertTrue(w.closed);self.assertFalse(w.raw_complete)
        self.assertEqual(w.path.stat().st_size,0)
        self.assertFalse(stream.artifact_evidence(w.snapshot(),w.path)['complete'])
    def test_evidence_relative_path_resolves(self):
        p,r=self.write();evidence=self.root/'capture';evidence.mkdir()
        record=stream.artifact_evidence(r,p,evidence_directory=evidence)
        self.assertEqual((evidence/record['file']).resolve(),p.resolve())

    def test_actual_event_formula_small(self):
        for rows in (1,2,16,17):
            self.assertEqual(sum(1 for _ in fixture(rows)),stream.profile_counts(rows)[1])
    def test_m128_static_counts(self):
        self.assertEqual(stream.profile_counts(128),(19200,2478339))


if __name__ == '__main__':
    unittest.main()
