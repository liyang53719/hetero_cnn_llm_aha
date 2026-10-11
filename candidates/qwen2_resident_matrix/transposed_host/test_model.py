"""Host public lease + existing physical Down model, with opaque Matrix tokens.

No arithmetic/RTL claim: these tests cover admission, actual-address memory,
ACK publication, command reuse and fault drain through the frozen port model.
"""
import importlib.util
from dataclasses import replace
from pathlib import Path
import sys
import unittest

spec = importlib.util.spec_from_file_location("host_lease_model", Path(__file__).with_name("model.py"))
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)
d = m.down


def launch(**kw):
    values = dict(command_base=0x1000, command_limit=0x1040, commands=1,
                  descriptor_base=0x2000, descriptor_limit=0x2400, descriptors=32, epoch=7,
                  regions=(m.Region(0x1000, 0x10000, True, False),
                           m.Region(0x100000, 0x600000, True, False),
                           m.Region(0x800000, 0xa00000, True, True),
                           m.Region(0x10000000, 0x100c0000, True, True)))
    values.update(kw)
    return m.Launch(**values)


def job(**kw):
    values = dict(m=16, k=32, n=32, activation_bf16=False)
    values.update(kw)
    return d.Job(**values)


class Run:
    def __init__(self, host, j, memory=None):
        self.host = host
        self.owner = host.bind_dense(j)
        assert self.owner is not None
        self.j = self.owner.job
        self.memory = {} if memory is None else memory
        self.read = self.write = self.ack = self.seed_request = self.seed_ack = None
        self.results = []
        self.pending = []
        self.reads = []
        self.raw_a = []
        self.steps = 0

    def cycle(self, *, ack=True, seed=True, **override):
        o = self.owner
        args = {}
        if self.read:
            q = self.read
            if q.kind == "prefix":
                assert q.address in self.memory, "no injected prefix data"
                words = self.memory[q.address]
            elif q.kind == "a":
                # Unwritten initial inputs are explicit finite synthetic words;
                # producer addresses always read actual prior ACK writes.
                words = self.memory.get(q.address, (0x3f800000,) * 16)
                self.raw_a.append((q.address, words))
            else:
                words = (0x3f80,) * 32
            args["read_beat"] = d.ReadBeat(q.tag, words, True)
        if self.results:
            args["result"] = self.results[0]
        if o.group_started and not o.group_done and (o.error or (
                o.group_accepted_steps == (o.chunk_end-o.chunk_start)*o.contexts and
                o.results_received == o.contexts)):
            args["matrix_done"] = d.MatrixDone(self.j.tag, bool(o.error))
        if ack and self.ack:
            args["write_ack"] = self.ack
        if seed and self.seed_ack:
            args["seed_ack"] = self.seed_ack
        args.update(override)
        e = o.tick(**args)
        if e["read_fire"]:
            self.read = None
        if e["read_command_fire"]:
            self.read = e["read_command"]
            self.reads.append(self.read)
        if e["step_fire"]:
            self.steps += 1
            s = e["step"]
            if s.last:
                value = 0x3f800000 + o.chunk_index * 0x10000 + s.context * 0x1000
                self.results.append(d.MatrixResult(s.context, tuple(
                    tuple(value + row*256 + col for col in range(256)) for row in range(16))))
        if e["result_fire"]:
            self.results.pop(0)
        if e["write_command_fire"]:
            self.write = (e["write_command"], 0)
            self.pending = []
        if e["write_data_fire"]:
            q, index = self.write
            self.pending.append((q.address + index*64, e["write_data"].words))
            self.write = (q, index+1)
            if e["write_data"].last:
                self.ack = d.WriteAck(q.tag, nbytes=q.beats*64)
        if e["write_ack_fire"]:
            if not args["write_ack"].error and args["write_ack"].tag == self.write[0].tag:
                self.memory.update(self.pending)
            self.ack = self.write = None
            self.pending = []
        if e["seed_begin_fire"]:
            self.seed_request = e["seed_begin"]
        if e["seed_beat_fire"] and e["seed_beat"].last:
            self.seed_ack = d.SeedAck(self.seed_request)
        if e["seed_ack_fire"]:
            self.seed_request = self.seed_ack = None
        self.host.observe_owner_event(e)
        return e

    def until(self, condition, **kw):
        for _ in range(300000):
            if condition():
                return
            self.cycle(**kw)
        raise AssertionError((self.owner.state, self.owner.error, self.host.state))


class Admission(unittest.TestCase):
    def test_default_fourth_general_region_and_empty_old_driver(self):
        cfg = launch(regions=launch().regions[:3] + (m.Region(),))
        cfg.validate(False)
        cfg = launch(command_base=0x10000000, command_limit=0x10000040,
                     regions=launch().regions[:3] + (m.Region(0x10000000, 0x100c0000, True, False),))
        cfg.validate(False)
        with self.assertRaises(ValueError):
            cfg.validate(True)
        self.assertEqual(m.LAUNCH_PAYLOAD_BITS, 4*64+16+25+16+4*(64+64+1+1))

    def test_enabled_requires_real_rw_workspace_before_metadata(self):
        for r in (m.Region(), m.Region(1, 1), m.Region(0x10000000, 0x10000040, True, False),
                  m.Region(0x10000000, 0x10000040, False, True)):
            h = m.HostLeaseModel(True)
            h.launch(launch(regions=launch().regions[:3] + (r,)))
            self.assertEqual(h.result(), ("Bounds", 0, 7))
            self.assertEqual(h.owner_issues, 0)

    def test_region_order_alignment_overflow_and_all_pair_collisions(self):
        bad = (m.Region(0x10000001, 0x10000040, True, True),
               m.Region(0x10000000, 0x10000041, True, True),
               m.Region(0x10000040, 0x10000000, True, True),
               m.Region((1<<56)-64, (1<<56)+64, True, True),
               m.Region((1<<64)-64, 64, True, True))
        for r in bad + tuple(m.Region(r.base, r.limit, True, True) for r in launch().regions[:3]):
            with self.assertRaises(ValueError):
                launch(regions=launch().regions[:3] + (r,)).validate(True)
        launch(regions=launch().regions[:3] + (m.Region((1<<56)-64, 1<<56, True, True),)).validate(True)
        for i in range(4):
            for j in range(i+1, 4):
                regions = list(launch().regions)
                regions[j] = replace(regions[j], base=regions[i].base, limit=regions[i].limit)
                with self.assertRaises(ValueError):
                    launch(regions=tuple(regions)).validate(True)

    def test_metadata_cannot_use_reserved_span(self):
        for k, v in (("command_base", 0x10000000), ("descriptor_base", 0x10000000)):
            kwargs = {k: v, k.replace("base", "limit"): v + 0x400}
            with self.assertRaises(ValueError):
                launch(**kwargs).validate(True)

    def test_snapshot_busy_pins_and_nonzero_epoch_identity(self):
        h = m.HostLeaseModel(True)
        cfg = launch(epoch=65535)
        self.assertTrue(h.launch(cfg))
        ws = h.cfg.workspace()
        self.assertEqual(ws.generation, 65536)
        self.assertEqual(ws.split_k, 2560)
        self.assertFalse(h.launch(launch(epoch=3)))
        self.assertEqual(h.cfg.workspace(), ws)
        for flag in ("owner_poison", "hub_poison", "dma_poison"):
            enabled = m.HostLeaseModel(True)
            self.assertFalse(enabled.launch(cfg, **{flag: True}))
            self.assertIsNone(enabled.cfg)
            legacy = m.HostLeaseModel(False)
            self.assertTrue(legacy.launch(cfg, **{flag: True}))

    def test_every_workspace_launch_pin_changes_while_busy_are_ignored(self):
        h = m.HostLeaseModel(True)
        cfg = launch()
        h.launch(cfg)
        original = h.cfg.workspace()
        r = cfg.regions[3]
        for changed in (replace(r, base=r.base+64), replace(r, limit=r.limit-64),
                        replace(r, read=False), replace(r, write=False), m.Region()):
            incoming = replace(cfg, epoch=0, regions=cfg.regions[:3] + (changed,))
            self.assertFalse(h.launch(incoming))
            self.assertEqual(h.cfg.workspace(), original)

    def test_reserved_region_rejects_ordinary_read_and_write(self):
        for field in ("a", "b", "dst"):
            h = m.HostLeaseModel(True)
            h.launch(launch())
            self.assertIsNone(h.bind_dense(job(**{field: 0x10000000})))
            self.assertEqual(h.owner_issues, 0)
            self.assertFalse(h.ordinary_span(0x10000000, 0x10000040))

    def test_ordinary_write_only_arena_remains_legal_but_not_readable(self):
        regions = list(launch().regions)
        regions[2] = replace(regions[2], read=False)
        h = m.HostLeaseModel(True)
        h.launch(launch(regions=tuple(regions)))
        self.assertTrue(h.ordinary_span(0x800000, 0x800800, write=True))
        self.assertFalse(h.ordinary_span(0x800000, 0x800800))
        self.assertIsNotNone(h.bind_dense(job()))

    def test_shape_and_dtype_fail_before_owner_dma(self):
        for change in (dict(m=1), dict(m=64), dict(k=8976), dict(n=16), dict(k=17),
                       dict(activation_bf16=True), dict(output_bf16=True), dict(write_bytes=1)):
            h = m.HostLeaseModel(True)
            h.launch(launch())
            self.assertIsNone(h.bind_dense(job(**change)))
            self.assertEqual(h.owner_issues, 0)

    def test_full_down_capacity_and_single_chunk_reuse(self):
        cfg = launch()
        self.assertEqual(cfg.workspace().extent, 786432)
        full = job(m=128, k=8960, n=1536, a=0x1000000, b=0x2000000, dst=0x8000000)
        cfg.workspace().validate(full)
        with self.assertRaises(ValueError):
            replace(cfg.workspace(), extent=786368).validate(full)
        h = m.HostLeaseModel(True)
        h.launch(launch(regions=cfg.regions[:3] + (m.Region(0x10000000, 0x10000040, True, True),)))
        self.assertIsNotNone(h.bind_dense(job(n=8960)))
        h = m.HostLeaseModel(True)
        h.launch(launch(regions=cfg.regions[:3] + (m.Region(0x10000000, 0x10000040, True, True),)))
        self.assertIsNone(h.bind_dense(job(k=2688)))
        self.assertEqual(h.owner_issues, 0)


class Lifetime(unittest.TestCase):
    def test_successful_relaunch_changes_lease_and_epoch_zero_same_owner(self):
        h = m.HostLeaseModel(True)
        h.launch(launch())
        first = Run(h, job())
        first.until(lambda: h.state == "complete")
        h.completion()
        self.assertEqual(h.result(), (None, 1, 7))
        regions = launch().regions[:3] + (m.Region(0x11000000, 0x110c0000, True, True),)
        self.assertTrue(h.launch(launch(epoch=0, regions=regions)))
        second = Run(h, job(k=2688), first.memory)
        self.assertIs(second.owner, first.owner)
        self.assertEqual(second.owner.workspace.generation, 1)
        second.until(lambda: h.state == "complete")
        self.assertTrue(any(r.kind == "prefix" for r in second.reads))
        self.assertTrue(all(0x11000000 <= r.address < 0x110c0000
                            for r in second.reads if r.kind == "prefix"))
        h.completion()
        self.assertEqual(h.result(), (None, 1, 0))

    def test_terminal_wrong_tag_precedes_owner_error(self):
        # Deliberate invalid owner response checks Host precedence, not an
        # arithmetic completion or successful owner/DMA execution.
        h = m.HostLeaseModel(True)
        h.launch(launch())
        h.bind_dense(job())
        h.observe_owner_event(dict(response_fire=True, response=(0xffffffff, "Memory", 0)))
        self.assertEqual(h.status, "Protocol")
        self.assertFalse(h.published)

    def test_same_owner_two_commands_read_actual_ack_producer(self):
        h = m.HostLeaseModel(True)
        h.launch(launch(commands=2))
        first = Run(h, job())
        identity = id(first.owner)
        first.until(lambda: h.state == "complete")
        self.assertFalse(h.published)
        self.assertFalse(h.completion(False))
        h.completion()
        self.assertEqual(h.published, [(0x800000, 0x800800)])
        second = Run(h, job(a=0x800000, dst=0x810000), first.memory)
        self.assertEqual(id(second.owner), identity)
        second.until(lambda: h.state == "complete")
        self.assertTrue(second.raw_a)
        self.assertTrue(all(words == first.memory[addr] for addr, words in second.raw_a))
        h.completion()
        self.assertEqual(h.result(), (None, 2, 7))
        self.assertTrue(h.launch_ready())

    def test_final_ack_and_completion_backpressure_keep_lease(self):
        h = m.HostLeaseModel(True)
        cfg = launch()
        h.launch(cfg)
        run = Run(h, job())
        run.until(lambda: run.ack is not None)
        for _ in range(11):
            run.cycle(ack=False)
            self.assertEqual(h.state, "wait_done")
            self.assertFalse(h.launch(launch(epoch=123)))
        run.until(lambda: h.state == "complete")
        for _ in range(5):
            self.assertFalse(h.completion(False))
            self.assertEqual(h.cfg.workspace(), cfg.workspace())
        h.completion()
        self.assertIsNone(h.result(False))
        self.assertFalse(h.launch_ready())
        self.assertEqual(h.result(), (None, 1, 7))

    def test_actual_prefix_read_error_waits_seed_ack_then_poison(self):
        h = m.HostLeaseModel(True)
        h.launch(launch())
        run = Run(h, job(k=2688))
        run.until(lambda: run.read is not None and run.read.kind == "prefix")
        req = run.seed_request
        self.assertIsNotNone(req)
        run.cycle(read_beat=d.ReadBeat(run.read.tag, (0,)*16, True, error=True), seed=False)
        for _ in range(11):
            run.cycle(seed=False)
            self.assertEqual(h.state, "wait_done")
        self.assertTrue(run.owner.group_done)
        self.assertTrue(run.owner.seed_outstanding)
        self.assertTrue(run.owner.ports()["seed_ack_ready"])
        run.cycle(seed_ack=d.SeedAck(req, error=True))
        run.until(lambda: h.state == "complete")
        self.assertFalse(h.published)
        h.completion()
        self.assertIsNotNone(h.result()[0])
        self.assertFalse(h.launch_ready())
        h.reset()
        self.assertFalse(h.launch_ready())
        h.reset(coordinated=True)
        self.assertTrue(h.launch_ready())
        self.assertTrue(h.launch(launch()))
        retry = Run(h, job())
        retry.until(lambda: h.state == "complete")
        h.completion()
        self.assertEqual(h.result(), (None, 1, 7))

    def test_final_write_error_does_not_publish(self):
        h = m.HostLeaseModel(True)
        h.launch(launch())
        run = Run(h, job())
        run.until(lambda: run.ack is not None)
        run.cycle(write_ack=d.WriteAck(run.ack.tag, error=True))
        run.until(lambda: h.state == "complete")
        self.assertFalse(h.published)
        h.completion()
        self.assertIsNotNone(h.result()[0])
        self.assertEqual(h.state, "locked")

    def test_late_seed_ack_after_success_blocks_new_public_launch(self):
        h = m.HostLeaseModel(True)
        h.launch(launch())
        run = Run(h, job(k=2688))
        run.until(lambda: run.seed_ack is not None)
        late = run.seed_ack
        run.until(lambda: h.state == "complete")
        h.completion()
        self.assertEqual(h.result(), (None, 1, 7))
        self.assertTrue(h.launch_ready())
        run.owner.tick(seed_ack=late)
        self.assertTrue(run.owner.ports()["reset_required"])
        self.assertFalse(h.launch(launch(epoch=8)))
        h.reset(coordinated=True)
        self.assertTrue(h.launch(launch(epoch=8)))


if __name__ == "__main__":
    unittest.main()
