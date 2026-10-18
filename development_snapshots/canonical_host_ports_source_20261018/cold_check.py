"""Static checks of the real header source; never compiles or models a Host DUT."""
from pathlib import Path
import hashlib
import json
import re

HERE = Path(__file__).resolve().parent
RESULT = {
    'status': 'io_result_bits_status',
    'completed': 'io_result_bits_completed',
    'failedPc': 'io_result_bits_failedPc',
    'epoch': 'io_result_bits_epoch',
}
HUB = {
    'accepted[0]': 'io_memoryAccepted_0',
    'accepted[1]': 'io_memoryAccepted_1',
    'returned[0]': 'io_memoryReturned_0',
    'returned[1]': 'io_memoryReturned_1',
}


def require(ok, why):
    if not ok:
        raise ValueError(why)


def uncomment(text):
    return re.sub(r'//[^\n]*|/\*.*?\*/', '', text, flags=re.S)


def function_body(text, signature):
    require(text.count(signature) == 1, 'unique exact signature: ' + signature)
    after = text.split(signature, 1)[1]
    require(after.lstrip().startswith('{'), 'function opening brace')
    start = after.index('{') + 1
    depth = 1
    for i in range(start, len(after)):
        depth += (after[i] == '{') - (after[i] == '}')
        if depth == 0:
            return after[start:i]
    raise ValueError('unterminated function')


def zero_targets(body):
    lines = [line.strip() for line in body.splitlines() if line.strip()]
    pattern = re.compile(r'd\.([A-Za-z0-9_]+(?:\[\d+\])?)\s*=\s*0;')
    require(all(pattern.fullmatch(line) for line in lines), 'zero-only direct assignments')
    targets = tuple(pattern.fullmatch(line).group(1) for line in lines)
    require(len(targets) == len(set(targets)) == 54, '54 distinct input slots')
    return targets


def bindings(body, type_name):
    lines = [line.strip() for line in body.splitlines() if line.strip()]
    require(lines[0] == type_name + ' value{};' and lines[-1] == 'return value;', 'getter structure')
    pattern = re.compile(r'value\.([A-Za-z0-9_]+(?:\[\d+\])?)\s*=\s*d\.([A-Za-z0-9_]+);')
    require(all(pattern.fullmatch(line) for line in lines[1:-1]), 'direct unchanged getter assignments')
    pairs = [pattern.fullmatch(line).groups() for line in lines[1:-1]]
    require(len(pairs) == len(dict(pairs)), 'unique getter destinations')
    return dict(pairs)


def sources(repo):
    pin = json.loads((HERE / 'SOURCE_PIN.json').read_text())
    root = Path(repo).resolve(strict=True)
    loaded = {}
    for name, expected in pin['upstream'].items():
        raw = (root / name).read_bytes()
        require(len(raw) == expected['bytes'] and hashlib.sha256(raw).hexdigest() == expected['sha256'], 'upstream source drift: ' + name)
        loaded[Path(name).name] = raw.decode()
    return loaded


def check(text=None, *, repo):
    original = sources(repo)
    text = uncomment((HERE / 'host_ports.hpp').read_text() if text is None else text)
    startup = uncomment(original['startup_inputs.hpp'])
    expected = zero_targets(function_body(startup, 'inline void zero_inputs(VHostBlockTop& d)'))
    actual = zero_targets(function_body(text, 'static void initialize_inputs(Model& d)'))
    require(actual == expected, 'exact original input ordering/targets')
    snapshot = function_body(uncomment(original['host_fields.hpp']), 'static InputSnapshot input_snapshot(const VHostBlockTop& d)')
    pin_targets = tuple(re.findall(r'd\.([A-Za-z0-9_]+(?:\[\d+\])?)', snapshot))
    require(actual == pin_targets, 'independent published snapshot coverage')
    require(bindings(function_body(text, 'static HostResult result(const Model& d)'), 'HostResult') == RESULT, 'result pin binding')
    require(bindings(function_body(text, 'static HubCounts hub(const Model& d)'), 'HubCounts') == HUB, 'hub pin binding')
    require('std::uint8_t status = 0;' in text and 'std::uint16_t completed = 0, failedPc = 0, epoch = 0;' in text, 'result storage widths')
    require('std::array<std::uint64_t, 2> accepted{}, returned{};' in text, 'two uint64 counters per direction')
    require('return accepted == other.accepted && returned == other.returned;' in text, 'complete hub equality')
    scala = original['HostResidualCommands.scala']
    for name, bits in [('status', 8), ('completed', 16), ('failedPc', 16), ('epoch', 16)]:
        require(re.search(r'val\s+' + name + r'\s*=\s*UInt\(' + str(bits) + r'\.W\)', scala) is not None, 'Scala result width: ' + name)
    for name in ('memoryAccepted', 'memoryReturned'):
        require('val ' + name + '=Output(Vec(2,UInt(64.W)))' in original['HostBlockTop.scala'], 'Scala hub shape: ' + name)
    for forbidden in ('launch_payload', '.eval(', 'VHostBlockTop', 'HostMemory', 'CanonicalSinkStreamBridge', '#include "'):
        require(forbidden not in text, 'partial-source boundary: ' + forbidden)
    return dict(input_slots=54, result_fields=4, hub_counters=4, compiled=False, model_executed=False)


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(check(repo=args.repo), sort_keys=True))
