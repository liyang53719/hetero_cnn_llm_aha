"""Compose the distinct observer over the frozen tiled preparation, source-only."""
import hashlib
import json
from pathlib import Path
from ..attention_packed_m128 import prepare as prior
from .capture import VERSION, require

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PREFIX = 'candidates/qwen2_resident_matrix/attention_packed_tiled_observation/'
OWN = tuple(PREFIX+n for n in ('capture.py','monitor.py','prepare.py','test_capture.py','test_admission.py','README.md'))
EXTRA = ('candidates/qwen2_resident_matrix/official_bf16/observation.py',
         'scripts/observe_qwen2_attention_model.py')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check():
    base = prior.check()
    pins = json.loads((HERE/'pins.json').read_text())
    require(set(pins) == {'schema','runtime','own'} and pins['schema'] == VERSION,
            'packed observation pin schema')
    expected = {**base['sources'],**prior.prior.check()['generated'],**base['own'],**base['generated'],
                prior.PREFIX+'pins.json':digest(prior.HERE/'pins.json'),
                **{n:digest(ROOT/n) for n in EXTRA}}
    require(pins['runtime'] == expected and set(pins['own']) == set(OWN), 'packed observation source inventory')
    require({n:digest(ROOT/n) for n in OWN} == pins['own'], 'packed observation source drift')
    return pins


def compose(destination):
    pins = check()
    out = prior.compose(destination)
    for name in (*EXTRA,*OWN,PREFIX+'pins.json',prior.PREFIX+'pins.json'):
        target = out/name; target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes((ROOT/name).read_bytes())
    expected = {**pins['runtime'],**pins['own'],PREFIX+'pins.json':digest(HERE/'pins.json')}
    require({n:digest(out/n) for n in expected} == expected, 'packed observation composition drift')
    return out


def authorize_full_numeric(*args, **kwargs):
    raise ValueError('observer preparation confers no full Public numeric admission')


def schedule_source():
    import tempfile
    with tempfile.TemporaryDirectory() as directory:
        out = prior.compose(Path(directory)/'tree')
        return (out/prior.TARGET).read_text()
