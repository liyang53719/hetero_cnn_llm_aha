"""Read-only, nonoverlapping stage deltas; no callback or model substitution.

Every interval includes its dispatch/public-retirement edges unless separated
explicitly by the caller. These are software stage intervals, not a per-edge
owner/busy census, not issue capacity, and never hardware utilization.
"""
from collections import Counter
import time
from candidates.qwen2_live_attention_model_m128 import boundary


def require(ok, message):
    if not ok:
        raise ValueError(message)


def identity(x, physical, memory):
    return dict(boundary.identity(x, physical), act_data=id(memory.act.data),
        workspace=id(memory.workspace), workspace_data=id(memory.workspace.data),
        physical_buffers={n:id(r['data']) for n,r in physical.regions.items() if not r['readonly']})


def debts(x, physical, memory):
    result = boundary.debts(x, physical)
    bridge = x.matrix_service._dense
    window = x.window_matrix_bridge
    h = x.coupled
    ws = memory.workspace
    result.update(matrix_group=x.matrix_service.group is not None,
        matrix_result=x.matrix_service.result is not None,
        matrix_done=x.matrix_service._done is not None,
        dense_bridge=bridge is not None, dense_bridge_results=len(bridge.pending) if bridge else 0,
        window_bridge=window is not None, window_bridge_results=len(window.pending) if window else 0,
        ordinary_job=x.down_job is not None, ordinary_terminal=x.down_terminal is not None,
        coordinator_not_idle=h is not None and h.c.state != 'idle',
        coordinator_poison=h is not None and h.c.poison,
        resident_silu_busy=h is not None and h.silu_busy,
        workspace_read=ws.pending_read is not None, workspace_seed=len(ws.seeds),
        workspace_invalidated=ws.invalidated is not None,
        workspace_unfinished=ws.job is not None and not ws.finished)
    return result


def snapshot(x, physical, memory, silu):
    lib = x.matrix_service.lib
    return dict(host=dict(x.counts), matrix=dict(x.matrix_service.counts),
        scalar_calls=dict(x.prefix_owner.scalar.calls), memory=dict(physical.counts),
        workspace=dict(memory.workspace.counts),
        native=dict(dense_fma=int(lib.matrix_dense_fmas()), normal_fma=int(lib.matrix_normal_fmas()),
                    silu_calls=int(silu.sf_calls()), silu_failures=int(silu.sf_failures())),
        observer=dict(silu_vectors=silu.calls))


def delta(after, before):
    answer = {}
    for section in after:
        names = set(after[section]) | set(before[section])
        answer[section] = {n:after[section].get(n,0)-before[section].get(n,0) for n in names}
        require(all(v >= 0 for v in answer[section].values()), 'stage counter reset: '+section)
    return answer


class StageLedger:
    def __init__(self, x, physical, memory, silu):
        self.x, self.physical, self.memory, self.silu = x, physical, memory, silu
        self.start = snapshot(x, physical, memory, silu)
        self.previous = self.start
        self.intervals, self.active = [], None
        self.last_tick = self.start['host'].get('host_model_ticks',0)
        self.closed = False

    def transition(self, name):
        require(not self.closed and isinstance(name,str) and name and
                name not in [r['name'] for r in self.intervals], 'duplicate/closed stage interval')
        now = snapshot(self.x, self.physical, self.memory, self.silu)
        tick = now['host'].get('host_model_ticks',0)
        wall = time.monotonic()
        if self.active is not None:
            diff = delta(now,self.previous)
            require(diff['host'].get('host_model_ticks',0) == tick-self.last_tick, 'stage tick gap')
            self.intervals.append(dict(name=self.active,tick_start=self.last_tick,tick_end=tick,
                host_model_ticks=tick-self.last_tick,wall_seconds=wall-self.wall,accepted_counter_delta=diff,
                matrix_issue_offered=None,matrix_busy_ticks=None,matrix_owned_ticks=None,
                scalar_busy_ticks=None,silu_busy_ticks=None,issue_lease_busy_are_distinct=True))
        else:
            require(tick == self.last_tick, 'unobserved Host edges before first stage')
        self.active, self.previous, self.last_tick, self.wall = name, now, tick, wall

    def finish(self):
        self.transition('closed')
        self.closed = True
        end = snapshot(self.x,self.physical,self.memory,self.silu)
        totals = delta(end,self.start)
        require(sum(r['host_model_ticks'] for r in self.intervals) ==
                totals['host'].get('host_model_ticks',0), 'nonoverlapping stage ticks incomplete')
        dense = totals['matrix'].get('dense_steps',0)
        normal = totals['matrix'].get('normal_steps',0)
        return dict(intervals=self.intervals,total=totals,
            host_model_ticks=totals['host'].get('host_model_ticks',0),
            stage_partition='nonoverlapping driver stages including dispatch/retirement; no per-edge state census',
            full_fixed_array_cells=4096,matrix_context_storage_slots=5,resident_tile_storage_slots=3,
            accepted_dense_steps=dense,accepted_normal_steps=normal,
            full_fixed_array_issued_cell_opportunities=4096*(dense+normal),
            actual_c_fma=totals['native'].get('dense_fma',0)+totals['native'].get('normal_fma',0),
            matrix_issue_offered=None,matrix_busy_ticks=None,matrix_owned_ticks=None,
            hardware_cycles=None,hardware_busy_fraction=None,hardware_utilization=None,
            software_model_issue_fraction=None,software_model_ownership_fraction=None,
            per_edge_owner_busy_census_available=False,model_ticks_are_hardware_cycles=False,
            denominator_note='4096 cells per accepted issue event is arithmetic packing, never elapsed utilization',
            scalar_sfu_unified_physical_arbiter_proven=False)
