"""Small cycle/control reference for ResidentCSeedReader, not a Chisel simulator.

The fixture supplies exactly one-cycle 256-bit bank data. The existing seed
controller model supplies the independent endpoint/control reference. No FMA
or alternate accumulator arithmetic is implemented here.
"""
from dataclasses import dataclass
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "candidates/qwen2_resident_matrix"))
from seed_protocol_model import Ack, Beat, Request, ResidentPrefixOwner, finite


@dataclass(frozen=True)
class Descriptor:
    seed: Request = Request()
    slot: int = 0
    tile_row: int = 0
    n_base: int = 0
    prefix_k: int = 256


class ResidentReaderModel:
    def __init__(self, owner):
        self.owner = owner
        self.state = "idle"
        self.desc = None
        self.shape = None
        self.payload = (0,) * 16
        self.index = self.slice = self.cluster = 0
        self.pinned = self.began = self.ack_seen = self.poison = False
        self.lease = None
        self.reads = self.completions = 0

    def geometry(self):
        m, n, k = self.shape
        d = self.desc
        rows, cols = min(16, m - d.tile_row * 16), min(256, n - d.n_base)
        base, slots = (k // 2, 1) if k <= 1536 else (128, 3)
        legal = (0 < m <= 128 and 0 < n < 65536 and 0 < k < 65536 and
                 n % 16 == k % 16 == 0 and 0 <= d.tile_row < 8 and rows > 0 and
                 0 <= d.n_base < n and d.n_base % 256 == 0 and
                 0 < d.prefix_k < k and d.prefix_k % 256 == 0 and
                 0 <= d.slot < slots and base + slots * 256 <= 1024 and
                 0 <= d.seed.context < 5 and 0 < d.seed.source_generation <= 0xFFFFFFFF and
                 d.seed.slice_mask == (1 << ((cols + 31) // 32)) - 1)
        return legal, rows, cols, base

    def metadata_ok(self):
        d = self.desc
        if not (0 <= d.slot < 3 and 0 <= d.tile_row < 8):
            return False
        o = self.owner
        return (o.prefix[d.slot][d.tile_row] == d.prefix_k and
                o.owner_n[d.slot][d.tile_row] == d.n_base and
                o.generation[d.slot][d.tile_row] == d.seed.source_generation)

    def held(self):
        return self.lease is not None and self.owner.leases.get((self.desc.slot, self.desc.tile_row)) == self.lease

    def fault(self):
        self.poison = True
        self.state = "locked"
        if self.pinned:
            self.owner.quarantined.add((self.desc.slot, self.desc.tile_row))

    def tick(self, *, start=None, acquire_ready=True, ports_granted=None,
             legacy_drained=True, owner_ready=True, abort=False,
             controller_reset=False, begin_ready=False, beat_ready=False,
             ack=None, committed=None, terminal_ready=True, read_data=None):
        """Evaluate old-cycle wires then update registers at its ending edge."""
        old_state = self.state
        if ports_granted is None:
            ports_granted = self.pinned
        active = old_state not in ("idle", "locked")
        source_fault = active and (abort or not owner_ready or
            self.shape != (self.owner.m, self.owner.n, self.owner.k) or
            (self.pinned and (not self.metadata_ok() or not self.held() or
                             not ports_granted or not legacy_drained)))
        unexpected_ack = ack is not None and (not self.began or self.ack_seen)
        usable = not (self.poison or source_fault or unexpected_ack or controller_reset)
        out = dict(start=False, acquired=False, begin=None, read=None, beat=None,
                   ack_fire=False, completed=False,
                   abort_controller=self.poison or source_fault or unexpected_ack,
                   stop_legacy=start is not None or old_state != "idle" or self.poison or controller_reset)
        if old_state == "idle" and start is not None and not (self.poison or controller_reset or abort or not owner_ready or ack):
            self.desc, self.shape = start, (self.owner.m, self.owner.n, self.owner.k)
            self.index = self.slice = self.cluster = 0
            self.pinned = self.began = self.ack_seen = False
            self.state = "acquiring"
            out["start"] = True
        if old_state == "acquiring" and usable:
            legal, rows, cols, _ = self.geometry()
            if not legal or not self.metadata_ok() or (self.desc.slot, self.desc.tile_row) in self.owner.leases:
                self.fault()
            elif legacy_drained and acquire_ready:
                d = self.desc
                self.lease = self.owner.open_restore(d.seed, d.slot, d.tile_row,
                    d.n_base, d.prefix_k, rows, cols)
                self.pinned = True
                self.state = "begin"
                out["acquired"] = True
        if old_state == "begin" and usable:
            out["begin"] = self.desc.seed
            if begin_ready:
                self.began = True
                self.state = "read_low"
        if old_state in ("read_low", "capture_low", "capture_high") and usable:
            _, rows, cols, base = self.geometry()
            row, half = divmod(self.cluster, 2)
            first_col = self.slice * 32 + half * 16
            live = row < rows and first_col < cols
            if old_state == "capture_low" or (old_state == "read_low" and live):
                word = base + self.desc.slot * 256 + self.desc.tile_row * 32 + first_col // 8
                word += int(old_state == "capture_low")
                assert base <= word < 1024
                out["read"] = (row, word)
                self.reads += 1
            if old_state == "read_low":
                if live:
                    self.state = "capture_low"
                else:
                    self.payload = (0,) * 16
                    self.state = "offer"
            else:
                assert read_data is not None and len(read_data) == 8, "missing synchronous t+1 response"
                col = first_col + (8 if old_state == "capture_high" else 0)
                word = tuple(read_data[i] if row < rows and col + i < cols else 0 for i in range(8))
                if old_state == "capture_low":
                    self.payload = word + (0,) * 8
                    self.state = "capture_high"
                else:
                    self.payload = self.payload[:8] + word
                    self.state = "offer"
                if not all(finite(v) for v in word):
                    self.fault()
        if old_state == "offer" and usable:
            last = self.cluster == 31 and not self.desc.seed.slice_mask >> (self.slice + 1)
            out["beat"] = Beat.make(self.desc.seed, self.index, self.payload, last)
            if beat_ready:
                if last:
                    self.state = "wait_ack"
                else:
                    self.index += 1
                    if self.cluster == 31:
                        self.slice += 1  # legal source masks are contiguous
                        self.cluster = 0
                    else:
                        self.cluster += 1
                    self.state = "read_low"
        # The old began/ackSeen values correspond to registers before this
        # cycle. begin and ACK cannot coexist with the registered controller.
        ack_fire = ack is not None and old_state not in ("idle", "acquiring", "begin") and self.began and not self.ack_seen and terminal_ready
        success = ack_fire and old_state == "wait_ack" and usable and ack == Ack.make(self.desc.seed) and committed == self.desc.seed
        out["ack_fire"] = ack_fire
        if ack_fire:
            self.ack_seen = True
            if success:
                self.owner.release(self.lease, True)
                self.pinned = self.began = False
                self.state = "idle"
                self.completions += 1
                out["completed"] = True
            else:
                self.fault()
        if committed is not None and not success:
            self.fault()
        if source_fault or unexpected_ack or controller_reset:
            self.fault()
        return out


class SyncBankFixture:
    """An observer of actual owner bytes with fixed one-cycle return timing."""
    def __init__(self, owner):
        self.owner = owner
        self.pending = None
        self.requests = []

    def tick(self, reader, **kwargs):
        out = reader.tick(read_data=self.pending, **kwargs)
        self.pending = None
        if out["read"] is not None:
            bank, word = out["read"]
            offset = (bank * 1024 + word) * 32
            self.pending = tuple(int.from_bytes(self.owner.scratch[offset + i * 4:offset + i * 4 + 4], "little") for i in range(8))
            self.requests.append((bank, word))
        return out


def dense_port_cycle(*, pause, legacy_request=False, legacy_pending=False,
                     operand_valid=False, a_high_pending=False, a_write=False,
                     state="execute", status=0, seed_enable=False):
    """The actual default-off StreamingDense patch's port arbitration only."""
    grant = (pause and not legacy_pending and not operand_valid and
             not a_high_pending and not a_write and state != "aWait" and status == 0)
    if seed_enable and not grant:
        raise ValueError("source read before actual Dense read/write/DMA drain")
    return dict(grant=grant, legacy_fire=legacy_request and not pause,
                seed_fire=seed_enable and grant,
                a_request=state == "aReq" and not a_high_pending and not pause and status == 0,
                job_ready=state == "idle" and not pause)
