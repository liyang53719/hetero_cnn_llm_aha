"""Public Host region-3 lease admission and lifetime, with the real Down model.

This models the changed admission/fence slice, not Command128 DDR decoding or
RTL. ``bind_dense`` receives the typed job after existing policy validation.
Arithmetic and SRAM/seed/drain behavior remain in the frozen Down port model.
Decoded-job rejection is reported as "Rejected", not a bit-exact reproduction
of the upstream decoder's Permission/Dependency/Unsupported/Bounds precedence.
There is no public abort operation. Local reset is not proof that old DMA or
retained-leaf transactions disappeared; only coordinated reset clears poison.
"""
from dataclasses import dataclass, replace
from pathlib import Path
import copy
import hashlib
import importlib.util
import sys

DOWN = Path(__file__).resolve().parent.parent / "transposed_down" / "model.py"
DOWN_SHA256 = "3e6f73fa8fe6ce5e78b4578335e82d7e593d0cce0b35e8f401dc045e1df59412"
if hashlib.sha256(DOWN.read_bytes()).hexdigest() != DOWN_SHA256:
    raise ValueError("frozen Down model identity drift")
spec = importlib.util.spec_from_file_location("host_workspace_down", DOWN)
down = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = down
spec.loader.exec_module(down)
ADDRESS_LIMIT = 1 << 56
LAUNCH_PAYLOAD_BITS = 833


@dataclass(frozen=True)
class Region:
    base: int = 0
    limit: int = 0
    read: bool = False
    write: bool = False

    def validate(self):
        if any(type(x) is not int or not 0 <= x < 1 << 64 for x in (self.base, self.limit)):
            raise ValueError("region uint64")
        if type(self.read) is not bool or type(self.write) is not bool:
            raise ValueError("region permissions")
        if self.base == self.limit and not self.read and not self.write:
            return
        if not self.base < self.limit <= ADDRESS_LIMIT or (self.base | self.limit) & 63:
            raise ValueError("region order/alignment/56-bit range")

    def contains(self, base, end):
        return self.base <= base < end <= self.limit


@dataclass(frozen=True)
class Launch:
    command_base: int
    command_limit: int
    commands: int
    descriptor_base: int
    descriptor_limit: int
    descriptors: int
    epoch: int
    regions: tuple

    def ordinary_regions(self, enabled):
        return self.regions[:3] if enabled else self.regions

    def validate(self, enabled):
        if len(self.regions) != 4 or not all(isinstance(r, Region) for r in self.regions):
            raise ValueError("exact public Vec4 regions")
        if not (type(self.epoch) is int and 0 <= self.epoch < 65536):
            raise ValueError("public epoch16")
        if not (type(self.commands) is int and 0 < self.commands <= 64 and
                type(self.descriptors) is int and 0 < self.descriptors <= 0xffffff):
            raise ValueError("command/descriptor count")
        for r in self.regions:
            r.validate()
        for i, a in enumerate(self.regions):
            for b in self.regions[i + 1:]:
                if a.base < a.limit and b.base < b.limit and overlap(a.base, a.limit, b.base, b.limit):
                    raise ValueError("regions overlap")
        tables = ((self.command_base, self.command_limit, self.commands),
                  (self.descriptor_base, self.descriptor_limit, self.descriptors))
        for base, limit, count in tables:
            if any(type(x) is not int or not 0 <= x < 1 << 64 for x in (base, limit)):
                raise ValueError("table uint64")
            end = base + ((count * 16 + 63) // 64) * 64
            if not base < limit or (base | limit) & 63 or end > limit:
                raise ValueError("table span/alignment")
            if not any(r.read and not r.write and r.contains(base, limit)
                       for r in self.ordinary_regions(enabled)):
                raise ValueError("table outside ordinary readonly regions")
        if overlap(*tables[0][:2], *tables[1][:2]):
            raise ValueError("command and descriptor tables overlap")
        if enabled:
            r = self.regions[3]
            if not (r.read and r.write and r.limit - r.base >= 64):
                raise ValueError("enabled profile requires nonempty RW workspace")

    def workspace(self):
        r = self.regions[3]
        # Identity only: epoch may repeat after successful completion/reset.
        # It is not a cross-reset stale-response or checkpoint certificate.
        return down.PrefixWorkspace(r.base, r.limit - r.base, self.epoch + 1, 2560)


def overlap(base, end, other_base, other_end):
    return base < other_end and other_base < end


class HostLeaseModel:
    """Changed Host admission/publication slice; no implicit backend completion."""
    def __init__(self, enabled=False):
        self.enabled = enabled
        self.state = "idle"
        self.poison = False
        self.cfg = None
        self.owner = None
        self.bound = None
        self.published = []
        self.completed = 0
        self.status = None
        self.owner_issues = 0

    def launch_ready(self, *, owner_poison=False, hub_poison=False, dma_poison=False):
        selected_poison = self.owner is not None and self.owner.ports()["reset_required"]
        return (self.state == "idle" and not self.poison and
                not (self.enabled and (selected_poison or owner_poison or hub_poison or dma_poison)))

    def launch(self, cfg, **poison):
        if not self.launch_ready(**poison):
            return False
        self.cfg = copy.deepcopy(cfg)
        self.completed = 0
        self.published = []
        self.status = None
        try:
            self.cfg.validate(self.enabled)
        except ValueError:
            # Existing Host launch bounds errors finish before any metadata DMA.
            self.status = "Bounds"
            self.state = "finish"
            return True
        self.state = "decode"
        return True

    def ordinary_span(self, base, end, *, write=False):
        return any((r.write if write else r.read) and r.contains(base, end)
                   for r in self.cfg.ordinary_regions(self.enabled))

    def live_span(self, base, end):
        readonly = any(r.read and not r.write and r.contains(base, end)
                       for r in self.cfg.ordinary_regions(self.enabled))
        return readonly or any(a <= base < end <= b for a, b in self.published)

    def bind_dense(self, job):
        if self.state != "decode" or not self.enabled:
            raise ValueError("selected Host profile must be ready for decoded Dense")
        job = replace(job, tag=(self.cfg.epoch << 16) | self.completed)
        try:
            job.validate()
            if job.activation_bf16 or job.output_bf16 or job.n > 8960:
                raise ValueError("unchanged plain Host FP32 A/D and maxRow contract")
            a_end = job.a + job.m * job.k * 4
            b_end = job.b + job.k * job.n * (2 if job.weight_bf16 else 4)
            d_end = job.dst + job.m * job.n * 4
            for base, end in ((job.a, a_end), (job.b, b_end)):
                if not self.ordinary_span(base, end) or not self.live_span(base, end):
                    raise ValueError("unpublished or reserved input")
            if not self.ordinary_span(job.dst, d_end, write=True):
                raise ValueError("destination outside ordinary writable region")
            if any(overlap(job.dst, d_end, a, b) for a, b in self.published):
                raise ValueError("destination overwrites published producer")
            workspace = self.cfg.workspace()
            workspace.validate(job)
        except ValueError:
            self.status = "Rejected"
            self.poison = True
            self.state = "complete"
            return None
        self.bound = copy.deepcopy(job)
        if self.owner is None:
            self.owner = down.DenseOwnerModel(workspace)
        else:
            self.owner.workspace = workspace
        event = self.owner.tick(job=self.bound)
        if not event["job_ready"]:
            raise AssertionError("owner must accept checked job")
        self.owner_issues += 1
        self.state = "wait_done"
        return self.owner

    def observe_owner_event(self, event):
        if not event.get("response_fire"):
            return
        if self.state != "wait_done":
            raise ValueError("unsolicited owner response")
        tag, error, nbytes = event["response"]
        expected = self.bound.m * self.bound.n * 4
        self.status = ("Protocol" if tag != self.bound.tag else
                       error or ("Protocol" if nbytes != expected else None))
        self.poison |= self.status is not None
        self.state = "complete"

    def completion(self, ready=True):
        if self.state != "complete" or not ready:
            return False
        if self.status is not None:
            self.state = "finish"
        else:
            self.published.append((self.bound.dst, self.bound.dst + self.bound.m * self.bound.n * 4))
            self.completed += 1
            self.state = "finish" if self.completed == self.cfg.commands else "decode"
        return True

    def result(self, ready=True):
        if self.state != "finish" or not ready:
            return None
        result = (self.status, self.completed, self.cfg.epoch)
        self.state = "locked" if self.poison else "idle"
        return result

    def reset(self, *, coordinated=False):
        if not coordinated:
            # A controller-only reset is explicitly outside the Host top reset
            # contract. Fail closed instead of fabricating backend retirement.
            self.poison = True
            return
        enabled = self.enabled
        owner = self.owner
        if owner is not None:
            owner.tick(coordinated_reset=True)
        self.__init__(enabled)
        self.owner = owner
