"""One explicit source candidate; never mutate or relabel the frozen baseline."""
from pathlib import Path
import hashlib
import json
import re
import sys

TARGET = 'chisel/continuous_prefill/src/main/scala/heteronpu/continuous/Bf16CausalGqaOwner.scala'
BASE_SHA256 = '47670efdb97d98e6faa1b8c24bbd0c059a510e5e2968346910053c380526511d'
MODULE = 'Bf16CausalGqaOwner'
OLD = '''  val incomingRows = VecInit(io.matrix.result.bits.value.map(_.asUInt))
  val incomingBeat = incomingRows(row).asTypeOf(Vec(8, UInt(1024.W)))(Mux(state === resultQk, 0.U, beat))
  val incomingFloats = incomingBeat.asTypeOf(Vec(32, UInt(32.W)))
'''
NEW = '''  val incomingFloats = GqaMatrixResultSelect(io.matrix.result.bits.value,
    row, Mux(state === resultQk, 0.U(3.W), beat))

'''
HELPER = '''/** Select exactly 32 FP32 bit patterns without first packing the whole tile.
  * Every row/beat encoding is valid (four/three bits). This is purely a wire
  * selection; it is independent of valid/ready and performs no arithmetic.
  */
object GqaMatrixResultSelect {
  def apply(value: Vec[Vec[UInt]], row: UInt, beat: UInt): Vec[UInt] = {
    require(value.length == 16 && value.forall(_.length == 256))
    require(value.forall(_.forall(_.getWidth == 32)))
    require(row.getWidth == 4 && beat.getWidth == 3)
    VecInit((0 until 32).map { lane =>
      MuxLookup(row, 0.U(32.W))((0 until 16).map { r =>
        r.U -> MuxLookup(beat, 0.U(32.W))((0 until 8).map { b =>
          b.U -> value(r)(b * 32 + lane)
        })
      })
    })
  }
}

'''
ANCHOR = '/** Bounded 16-query x32-key QK tiles and 16-query x256-column PV tiles.'


def require(ok, message):
    if not ok:
        raise ValueError(message)


def transform(raw):
    require(hashlib.sha256(raw).hexdigest() == BASE_SHA256,
            'candidate requires the exact frozen GQA source')
    text = raw.decode('utf-8')
    require(text.count(OLD) == text.count(ANCHOR) == 1, 'selector source anchor changed')
    # Keep every pre-existing source line at the same line number, including
    # inferred memories' source-location metadata. The strict raw module gate
    # still decides whether only the intended owner changed; no normalization.
    require(len(OLD.splitlines()) == len(NEW.splitlines()), 'replacement moved original source lines')
    return (text.replace(OLD, NEW, 1) + HELPER).encode('utf-8')


def module_hashes(path):
    """Hash every complete module and all outside bytes without normalizing RTL."""
    modules = {}
    outside = hashlib.sha256()
    gap = hashlib.sha256()
    gaps = []
    order = []
    current = None
    digest = None
    size = 0
    with Path(path).open('rb') as stream:
        for line in stream:
            start = re.match(rb'^module\s+([A-Za-z_][A-Za-z_0-9$]*)\b', line)
            end = re.match(rb'^endmodule\b', line)
            if start:
                require(current is None, 'nested or unterminated module')
                current = start[1].decode('ascii')
                require(current not in modules, 'duplicate generated module')
                order.append(current)
                gaps.append(gap.hexdigest())
                gap = hashlib.sha256()
                digest = hashlib.sha256()
                size = 0
            if current is None:
                require(not end, 'endmodule outside a module')
                outside.update(line)
                gap.update(line)
            else:
                digest.update(line)
                size += len(line)
                if end:
                    modules[current] = dict(sha256=digest.hexdigest(), bytes=size)
                    current = None
    require(current is None and modules, 'incomplete or empty generated module inventory')
    gaps.append(gap.hexdigest())
    return dict(modules=modules, module_order=order, outside_gap_sha256=gaps,
                outside_sha256=outside.hexdigest())


def module_diff(baseline, candidate):
    left, right = module_hashes(baseline), module_hashes(candidate)
    require(left['modules'].keys() == right['modules'].keys(), 'RTL module set changed')
    require(left['module_order'] == right['module_order'], 'RTL module order changed')
    require(left['outside_sha256'] == right['outside_sha256'], 'RTL outside modules changed')
    require(left['outside_gap_sha256'] == right['outside_gap_sha256'], 'RTL outside module gaps changed')
    changed = sorted(k for k in left['modules'] if left['modules'][k] != right['modules'][k])
    require(changed == [MODULE], 'unexpected generated module changes: ' + repr(changed))
    def sha(path):
        with Path(path).open('rb') as f:
            return hashlib.file_digest(f, 'sha256').hexdigest()
    old_sha, new_sha = sha(baseline), sha(candidate)
    require(old_sha != new_sha, 'candidate did not change generated RTL')
    return dict(schema='GQA_SELECTOR_RTL_STRUCTURE_CANDIDATE_V1',
                baseline_sha256=old_sha, candidate_sha256=new_sha,
                changed_modules=changed, unchanged_modules=len(left['modules']) - 1,
                outside_bytes_equal=True, normalization_applied=False,
                baseline=left, candidate=right, numerical_acceptance=False,
                behavioral_equivalence='requires separate selector and active owner tests',
                physical_qor_acceptance=False)


def preserve_failure(baseline, candidate, receipt, message):
    """Keep exact failing module bytes, without admitting any changed module."""
    from concat_inventory import MAX_SOURCE_BYTES
    baseline, candidate, receipt = map(Path, (baseline, candidate, receipt))
    destination = receipt.parent.parent/'selected-source/failure-module-diff'
    require(not destination.parent.exists(), 'fresh failure source destination required')
    destination.mkdir(parents=True)
    left, right = module_hashes(baseline), module_hashes(candidate)
    names = sorted(set(left['modules']) | set(right['modules']))
    changed = [name for name in names if left['modules'].get(name) != right['modules'].get(name)]
    result = dict(schema='GQA_SELECTOR_STRICT_MODULE_FAILURE_V1', status='REJECTED',
        numerical_acceptance=False, normalization_applied=False, error=message,
        changed_modules=changed, baseline=left, candidate=right,
        source_limit_bytes=MAX_SOURCE_BYTES, selected_source_bytes=0, saved_modules=[], preserved_sources=[])
    for variant, path, inventory in (('baseline', baseline, left), ('candidate', candidate, right)):
        with path.open('rb') as stream:
            active = None
            captured = None
            for line in stream:
                start = re.match(rb'^module\s+([A-Za-z_][A-Za-z_0-9$]*)\b', line)
                if start and start[1].decode('ascii') in changed:
                    active = start[1].decode('ascii')
                    identity = inventory['modules'][active]
                    entry = dict(variant=variant, module=active, **identity, preserved=False)
                    result['saved_modules'].append(entry)
                    if result['selected_source_bytes'] + identity['bytes'] <= MAX_SOURCE_BYTES:
                        captured = bytearray()
                    else:
                        entry['reason'] = 'source_byte_budget'
                if active is not None:
                    if captured is not None:
                        captured.extend(line)
                        require(len(captured) <= identity['bytes'], 'failure module byte overflow')
                    if re.match(rb'^endmodule\b', line):
                        if captured is not None:
                            require(len(captured) == identity['bytes'] and
                                hashlib.sha256(captured).hexdigest() == identity['sha256'],
                                'failure module identity mismatch')
                            output = destination/variant/(active+'.sv')
                            output.parent.mkdir(parents=True, exist_ok=True)
                            output.write_bytes(captured)
                            result['selected_source_bytes'] += len(captured)
                            entry.update(preserved=True, saved_as=str(output.relative_to(destination.parent)))
                            result['preserved_sources'].append(dict(path=entry['saved_as'],
                                bytes=identity['bytes'], sha256=identity['sha256']))
                        active, captured = None, None
        with path.open('rb') as stream:
            result[variant+'_rtl_sha256'] = hashlib.file_digest(stream, 'sha256').hexdigest()
    failure = receipt.with_suffix('.failure.json')
    failure.write_text(json.dumps(result, indent=2)+'\n')
    return result


if __name__ == '__main__':
    baseline, candidate, receipt = map(Path, sys.argv[1:])
    try:
        result = module_diff(baseline, candidate)
    except ValueError as error:
        preserve_failure(baseline, candidate, receipt, str(error))
        raise
    receipt.write_text(json.dumps(result, indent=2) + '\n')
