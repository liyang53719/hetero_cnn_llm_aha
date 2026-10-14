#!/usr/bin/env python3
"""Portable H2048 reduction-order behavior model, pinned to a historical basis.

Default: cold structure/source checks only; no arithmetic and no fixture reads.
--run-actual: independently rerun preserved arithmetic with externally supplied,
exactly pinned frozen fixtures. This is not RTL, full RMS, or current-owner proof.
Python 3.11+ and Git are required. Outputs contain metadata/hashes, never arrays.
"""
import argparse, ast, hashlib, json, struct, subprocess, sys, traceback
from collections import Counter
from fractions import Fraction
from functools import lru_cache
from pathlib import Path

ROOT = None
FIXTURE_ROOT = None
# This literal is only the prefix inside immutable historical receipts. It is
# mapped to --fixture-root; it is never used as a fallback filesystem location.
LEGACY_FIXTURE_PREFIX = Path('/workspace/scratch/f28987e955ed/hetero_recovery_20261013T1036')


HEAD = '027d343c5671ecdcf126b1ec68318728d1c4549a'

RUNNER = 'work/h2048_perf_actual_vector_m1_m16_m128/summary.json'

RUNNER_SHA = 'a5e443e068c236283ff1e1b66c9df119aac28ad38baabaecb699663a093c7f96'

MANIFEST_SHA = {
  1:'fdca7a3011740a44d1a1a26cc7570392b5fdb55993a849758829d4b71a205cc3',
  16:'a0634202bcca950242d6e1c160be6897cd5e14e735b80936f625d0167850d6a0',
  128:'799a8e3bc67c1dd32a77cc4766268a4d5c570639cf1fb7a18f87153fe008fde7'}

PINS = {
 'chisel/continuous_prefill/src/main/scala/heteronpu/continuous/GdnRmsNormFixedBankOwner.scala':'0738e0e0734eecd5981323ea74e87cacbe79b5e1ccf4e4c1bed3185a28c898ef',
 'chisel/continuous_prefill/src/main/scala/heteronpu/continuous/BlockFloat.scala':'9863718ca90089bf812eb07dbd82ce16d982a8c74b04d7543de1bd2dfb1e37b5',
 'candidates/qwen35_35b_rms/owner.py':'14f8f9bb0ee5845dea3a2e3ff203128563e7b1fda11b64c354c26cfdc2cbedc1',
 'candidates/qwen35_35b_rms/formula.py':'504c01f83e053fe573e2496c547bcc35d3ef54fab0fcb095d6eba02574caa1c7',
 'candidates/qwen35_35b_rms/reference.py':'b7a59beb38817ce10d0416de575983762c296a87eef9d57ea87b28158b091230',
 'candidates/qwen35_35b_rms/README.md':'719fb4cb0ac4e194b267c540df5e1453477cd7d0881d0f7fec18d5f4dc72953a',
 'config/upstream/weight_headers/qwen3_5_35b_a3b/modeling_qwen3_5_moe.py':'ea77a3979cb659dd04dc1f6a1cd7d3df53ddc5759e40eb0d5e98846e95b39d30',
 'config/upstream/weight_headers/qwen3_5_35b_a3b/config.json':'5e4d7f74fec2f360eb9cfbfcd6ec0c4c76e684d3a11caaed259d9fd9bfbc7944',
 'reports/execution/QWEN35_35B_H2048_RMS_20261013.json':'0e12d13ecfef245aaece441b462e664cf915e92dd7805fa21cad31b07c15934a',
 'src/heteronpu/rope_bf16_candidate.py':'fa647411e2c9f33c58c0b8c62d14063ebe249b199a8fcbc2c0d2cc645ff10bfd',
 'src/heteronpu/model_geometry.py':'04984111accff6b83bd1ab162d68dd44b0abb7c36de26631f764f774a2d25dee',
 'candidates/qwen2_resident_matrix/ffn_public/test_prefix_owners.py':'daf80d7d6273e9818e63aa030be8ec1ead07324ddcafc82ef8d165ed55065d4e'}

ORIGINAL_SCRIPT = {'bytes': 22844,
 'path': '/tmp/h2048_reduction_order_20261014/run.py',
 'sha256': '5294c45cc767e20665ccd0b05514f24e66f665171ba62f91c6014c04979819d7'}

HISTORICAL_BEHAVIOR_SUMMARY = {'bytes': 30037,
 'path': '/tmp/h2048_reduction_order_20261014/cold_run_2/summary.json',
 'sha256': '064af9cf6e1a7f2f3d6c0ced8cbb7bccd43f5b7de77e29cf02cb316273f120f7'}

CORE_AST_SHA256 = {'ArithmeticFailure': 'a71f15472230b6b0317136dd650f6e8958dd4eb2ed83d37037dddb4482e51c2c',
 'Graph': '04bdf2b81ce8cc95eb6b5c38f639edbd12a49f305f0921fc66de2e32a59036b4',
 'compare_graphs': '5833439621480c511029e8cf26d91a21ecbf29dde54a6701eb0044f6d040f199',
 'directed_checks': '15eef2d8104e29f45cf7ceedf6ec0bf4936c9bfc08d32408733c30dcb612dcdb',
 'grouped_order': '7e7151ed57dc7f85f5c57e9b08ee4dedad00e8cd2968227348bc46f3d5512084',
 'load_arithmetic': 'c87d5297b463ae28f474f48e401b7f077a60947bfdf79fa895be24d2203e477f',
 'rational_flags': 'a80612cdfa9ac328799ab40101a6ed66838691c46517444f4aa1aebc682cfdc6',
 'run_fixture': '7efa02fb3c51465b37690d9167536124afe878dc92d3a550bb864830253be5d7',
 'scalar_order': '83171b2d7a3900e70e999f8fe3b3785628d92a902a9f0d1b0d6344bf956bcc1c',
 'update_hashes': '0d3ba9e341ad53fdb6dafca1cc62770916b2eaad4fb91036e4cd6e801cd3dac0'}

HISTORICAL_FIXTURE_INVENTORY = [{'bytes': 8192,
  'path': '/workspace/scratch/f28987e955ed/hetero_recovery_20261013T1036/work/h2048_borrower_replay_m1_from_m16/expected/gamma.fp32le',
  'sha256': 'e2b51431d5c735af4c53d29735cca08461274a89ed2af769e418eee624c48511'},
 {'bytes': 4,
  'path': '/workspace/scratch/f28987e955ed/hetero_recovery_20261013T1036/work/h2048_borrower_replay_m1_from_m16/expected/inverse.fp32le',
  'sha256': '7e52afef2b7f8dff438057878a5566213f5dfc85114a76b563a9cd7b13467200'},
 {'bytes': 4,
  'path': '/workspace/scratch/f28987e955ed/hetero_recovery_20261013T1036/work/h2048_borrower_replay_m1_from_m16/expected/mean.fp32le',
  'sha256': 'c81e9d22a096c10060241c2fad003e06b51f120fab8feba1624d87e47e7ba220'},
 {'bytes': 4,
  'path': '/workspace/scratch/f28987e955ed/hetero_recovery_20261013T1036/work/h2048_borrower_replay_m1_from_m16/expected/mean_eps.fp32le',
  'sha256': 'e0bf5fe326b45787b18469a1cd135cad78512016b275f68dca5bb95420c5adcc'},
 {'bytes': 4096,
  'path': '/workspace/scratch/f28987e955ed/hetero_recovery_20261013T1036/work/h2048_borrower_replay_m1_from_m16/expected/output.bf16le',
  'sha256': 'acfbcab76aa90655d2c8898b1d5107c5a7d5da2f8729cf08d5390dca811756c9'},
 {'bytes': 8192,
  'path': '/workspace/scratch/f28987e955ed/hetero_recovery_20261013T1036/work/h2048_borrower_replay_m1_from_m16/expected/output.fp32le',
  'sha256': '3a77cbaa8d4569faa2681e76e6e9b33e50c78abff741e4bf42030fde61a85238'},
 {'bytes': 4,
  'path': '/workspace/scratch/f28987e955ed/hetero_recovery_20261013T1036/work/h2048_borrower_replay_m1_from_m16/expected/root.fp32le',
  'sha256': '1b5ba51d7ba521bb1d50f357c67b45962b302432d666f9e997059b07fba31d02'},
 {'bytes': 8192,
  'path': '/workspace/scratch/f28987e955ed/hetero_recovery_20261013T1036/work/h2048_borrower_replay_m1_from_m16/expected/scaled.fp32le',
  'sha256': '4df70762e39e893c2d19b5c7ea8f592ae94cfe6a6eadcd3f79d2e5035acef934'},
 {'bytes': 8192,
  'path': '/workspace/scratch/f28987e955ed/hetero_recovery_20261013T1036/work/h2048_borrower_replay_m1_from_m16/expected/squares.fp32le',
  'sha256': '65018e33277c4d0db116bcf744e4ad0c7d4ddb6542eb8068556c925e5c24cd1e'},
 {'bytes': 4,
  'path': '/workspace/scratch/f28987e955ed/hetero_recovery_20261013T1036/work/h2048_borrower_replay_m1_from_m16/expected/sum.fp32le',
  'sha256': '70ee4b9c3344f68ed27c046efbfe9ce1057d62202baf6b3bba23e571fdde133d'},
 {'bytes': 8192,
  'path': '/workspace/scratch/f28987e955ed/hetero_recovery_20261013T1036/work/h2048_borrower_replay_m1_from_m16/expected/weighted.fp32le',
  'sha256': 'fc7e059a684574a5bb350875450fc2d6f0e1b08c070cb1f41be8d6646b9a9383'},
 {'bytes': 4096,
  'path': '/workspace/scratch/f28987e955ed/hetero_recovery_20261013T1036/work/h2048_borrower_replay_m1_from_m16/stimulus/input.bf16le',
  'sha256': '77bda8c4aa7f52bb580cb5e52ccfdd4ff13c6de0ded70f1130dc33e2610dedf4'},
 {'bytes': 4096,
  'path': '/workspace/scratch/f28987e955ed/hetero_recovery_20261013T1036/work/h2048_borrower_replay_m1_from_m16/stimulus/weights.bf16le',
  'sha256': '2f331eb946dccbddc67529a69c0e20d8ec3810ff9658d6c4ecee4462fd3c3f47'},
 {'bytes': 43225,
  'path': '/workspace/scratch/f28987e955ed/hetero_recovery_20261013T1036/work/h2048_borrower_replay_m1_from_m16/manifest.json',
  'sha256': 'fdca7a3011740a44d1a1a26cc7570392b5fdb55993a849758829d4b71a205cc3'},
 {'bytes': 603234,
  'path': '/workspace/scratch/f28987e955ed/hetero_recovery_20261013T1036/work/reuse_owner_actual_m16/summary.json',
  'sha256': '368aa8ec2a5b5ac98a79bb24ca5fe718b4a7ab0cf90e9268c261851e2a98501d'},
 {'bytes': 131072,
  'path': '/workspace/scratch/f28987e955ed/hetero_recovery_20261013T1036/work/h2048_borrower_replay_m16/expected/gamma.fp32le',
  'sha256': '35b6042188671d4b25a47ed0b2221f84d753ea321586d5a40d873a3aa53f267f'},
 {'bytes': 64,
  'path': '/workspace/scratch/f28987e955ed/hetero_recovery_20261013T1036/work/h2048_borrower_replay_m16/expected/inverse.fp32le',
  'sha256': '34b0934624132dfb5c7d77e9ff5ff16ea9d21f1dec5aad401b5959da31c4d027'},
 {'bytes': 64,
  'path': '/workspace/scratch/f28987e955ed/hetero_recovery_20261013T1036/work/h2048_borrower_replay_m16/expected/mean.fp32le',
  'sha256': 'a54f7d84133c42ae1a1ab7e0294f7e5086cae71f3f67f3f55b2f51a2ab5d0a09'},
 {'bytes': 64,
  'path': '/workspace/scratch/f28987e955ed/hetero_recovery_20261013T1036/work/h2048_borrower_replay_m16/expected/mean_eps.fp32le',
  'sha256': 'eb5b978de56e7fb1a3b0c3e7053053fecb8d58576548d1d96441e7271ae8876f'},
 {'bytes': 65536,
  'path': '/workspace/scratch/f28987e955ed/hetero_recovery_20261013T1036/work/h2048_borrower_replay_m16/expected/output.bf16le',
  'sha256': '56503fe5be27c505efb209c0c23c172a2c760f290f9a9327ca922fbd893507ff'},
 {'bytes': 131072,
  'path': '/workspace/scratch/f28987e955ed/hetero_recovery_20261013T1036/work/h2048_borrower_replay_m16/expected/output.fp32le',
  'sha256': 'd8b5a1110af806766118566544aa3f88b8742811a191adf021ab4d73c5a56b53'},
 {'bytes': 64,
  'path': '/workspace/scratch/f28987e955ed/hetero_recovery_20261013T1036/work/h2048_borrower_replay_m16/expected/root.fp32le',
  'sha256': 'd273b3473fe9a71bae3a23816953934b027b44c4d6534f9d075075b4fabdd350'},
 {'bytes': 131072,
  'path': '/workspace/scratch/f28987e955ed/hetero_recovery_20261013T1036/work/h2048_borrower_replay_m16/expected/scaled.fp32le',
  'sha256': 'f19648ae1cecd94efe7aa04dd1556eff9d4e5958775e7dad725be44357259922'},
 {'bytes': 131072,
  'path': '/workspace/scratch/f28987e955ed/hetero_recovery_20261013T1036/work/h2048_borrower_replay_m16/expected/squares.fp32le',
  'sha256': 'd1ba15e8e4f4914d2499dc6baf42a2c0a55c6e2a3270b76e34062226a5ee22f8'},
 {'bytes': 64,
  'path': '/workspace/scratch/f28987e955ed/hetero_recovery_20261013T1036/work/h2048_borrower_replay_m16/expected/sum.fp32le',
  'sha256': '3c888c683e749536587708efb6f9305cf27a6183f8679fba871bbb4799cfb4f3'},
 {'bytes': 131072,
  'path': '/workspace/scratch/f28987e955ed/hetero_recovery_20261013T1036/work/h2048_borrower_replay_m16/expected/weighted.fp32le',
  'sha256': 'dcb421432fb9dbec4c5386dde4bc91569d0e3a76890b26039607492917ffd50e'},
 {'bytes': 65536,
  'path': '/workspace/scratch/f28987e955ed/hetero_recovery_20261013T1036/work/h2048_borrower_replay_m16/stimulus/input.bf16le',
  'sha256': 'be8e9494ce6952a1e848c3f354d545a1eebeb617f96de754c5c76e7a74ea9a0e'},
 {'bytes': 4096,
  'path': '/workspace/scratch/f28987e955ed/hetero_recovery_20261013T1036/work/h2048_borrower_replay_m16/stimulus/weights.bf16le',
  'sha256': '2f331eb946dccbddc67529a69c0e20d8ec3810ff9658d6c4ecee4462fd3c3f47'},
 {'bytes': 43262,
  'path': '/workspace/scratch/f28987e955ed/hetero_recovery_20261013T1036/work/h2048_borrower_replay_m16/manifest.json',
  'sha256': 'a0634202bcca950242d6e1c160be6897cd5e14e735b80936f625d0167850d6a0'},
 {'bytes': 603234,
  'path': '/workspace/scratch/f28987e955ed/hetero_recovery_20261013T1036/work/reuse_owner_actual_m16/summary.json',
  'sha256': '368aa8ec2a5b5ac98a79bb24ca5fe718b4a7ab0cf90e9268c261851e2a98501d'},
 {'bytes': 1048576,
  'path': '/workspace/scratch/f28987e955ed/hetero_recovery_20261013T1036/work/h2048_borrower_replay_m128/expected/gamma.fp32le',
  'sha256': '1aa39da537c0c379387ba72ae3890cf29bc662906e5b489c653fba9001a6ae52'},
 {'bytes': 512,
  'path': '/workspace/scratch/f28987e955ed/hetero_recovery_20261013T1036/work/h2048_borrower_replay_m128/expected/inverse.fp32le',
  'sha256': 'c8efc05c8da4eaf278c61d0e70cb8e6887f06fbf24071da2c8ae4b66d0369aa5'},
 {'bytes': 512,
  'path': '/workspace/scratch/f28987e955ed/hetero_recovery_20261013T1036/work/h2048_borrower_replay_m128/expected/mean.fp32le',
  'sha256': 'ca596df7227f81ba57e3e0bb1ffd8f5d269e795ccd0c3e96745343a1cbbb13fc'},
 {'bytes': 512,
  'path': '/workspace/scratch/f28987e955ed/hetero_recovery_20261013T1036/work/h2048_borrower_replay_m128/expected/mean_eps.fp32le',
  'sha256': '65c10ba96817338be36b91c159dc7da988b787624c0f05dadf43980690f320f4'},
 {'bytes': 524288,
  'path': '/workspace/scratch/f28987e955ed/hetero_recovery_20261013T1036/work/h2048_borrower_replay_m128/expected/output.bf16le',
  'sha256': 'b524371f72e29cd0f98411effd0d1fbe73d29b9bcc0af4010170478b1bb1f174'},
 {'bytes': 1048576,
  'path': '/workspace/scratch/f28987e955ed/hetero_recovery_20261013T1036/work/h2048_borrower_replay_m128/expected/output.fp32le',
  'sha256': 'ed6cde28bc3bf43cab370856843430a904317637d0057ec82aa1dc3db5ea911c'},
 {'bytes': 512,
  'path': '/workspace/scratch/f28987e955ed/hetero_recovery_20261013T1036/work/h2048_borrower_replay_m128/expected/root.fp32le',
  'sha256': '52ffeb057c167151b77c789c39b5bc7504c58d2a381d41643c7fa255da2bd80c'},
 {'bytes': 1048576,
  'path': '/workspace/scratch/f28987e955ed/hetero_recovery_20261013T1036/work/h2048_borrower_replay_m128/expected/scaled.fp32le',
  'sha256': '9e93811df40c5959fad287e10e3884b805176c653336012defc0483cb0fa4d98'},
 {'bytes': 1048576,
  'path': '/workspace/scratch/f28987e955ed/hetero_recovery_20261013T1036/work/h2048_borrower_replay_m128/expected/squares.fp32le',
  'sha256': '2d2cc09a4aa64675c5cc6de0bdda5ca9ea83d40870e3a10d225411d97dcc1279'},
 {'bytes': 512,
  'path': '/workspace/scratch/f28987e955ed/hetero_recovery_20261013T1036/work/h2048_borrower_replay_m128/expected/sum.fp32le',
  'sha256': 'be9ed8b649cc8ae7a08c0cb55ca51c41c07365a42439f1432014f736916bd5db'},
 {'bytes': 1048576,
  'path': '/workspace/scratch/f28987e955ed/hetero_recovery_20261013T1036/work/h2048_borrower_replay_m128/expected/weighted.fp32le',
  'sha256': '3a3f23636129a7fde63bff3871abf7be8f72f9c5522f4a0075235a5c30e65039'},
 {'bytes': 524288,
  'path': '/workspace/scratch/f28987e955ed/hetero_recovery_20261013T1036/work/h2048_borrower_replay_m128/stimulus/input.bf16le',
  'sha256': '70704553d4b42c32a6fa2ad4f0deaf4a0cf44594f832d5cfdb8a654400ca4280'},
 {'bytes': 4096,
  'path': '/workspace/scratch/f28987e955ed/hetero_recovery_20261013T1036/work/h2048_borrower_replay_m128/stimulus/weights.bf16le',
  'sha256': '2f331eb946dccbddc67529a69c0e20d8ec3810ff9658d6c4ecee4462fd3c3f47'},
 {'bytes': 43319,
  'path': '/workspace/scratch/f28987e955ed/hetero_recovery_20261013T1036/work/h2048_borrower_replay_m128/manifest.json',
  'sha256': '799a8e3bc67c1dd32a77cc4766268a4d5c570639cf1fb7a18f87153fe008fde7'},
 {'bytes': 712185,
  'path': '/workspace/scratch/f28987e955ed/hetero_recovery_20261013T1036/work/reuse_owner_actual_m128/summary.json',
  'sha256': 'acd9b3e99654c72a1d868dd9eb079ac255ecb0be76bfebbe21a3e491a4556f07'}]

RUNNER_BYTES = 94045

def require(ok, detail):
    if not ok: raise AssertionError(detail)

def sha(raw): return hashlib.sha256(raw).hexdigest()

def dump(obj): return (json.dumps(obj,sort_keys=True,indent=2)+'\n').encode()

def packed(words): return struct.pack('<'+'I'*len(words), *words)

def record(path):
    path=Path(path)
    with path.open('rb') as f: digest=hashlib.file_digest(f,'sha256').hexdigest()
    return {'path':str(path),'bytes':path.stat().st_size,'sha256':digest}

def git_bytes(*args):
    require(ROOT is not None, '--root must identify an explicit Git checkout')
    return subprocess.check_output(['git', '-C', str(ROOT), *args], stderr=subprocess.PIPE)


def historical_source(path):
    """The only input for helper ASTs: an exact object, never the live worktree."""
    require(path in PINS, 'unlisted historical source: '+path)
    raw=git_bytes('show', HEAD+':'+path)
    require(sha(raw)==PINS[path], 'historical source SHA mismatch: '+path)
    return raw


def within(path):
    require(FIXTURE_ROOT is not None, '--fixture-root is required for fixture access')
    p=Path(path)
    require('..' not in p.parts, 'fixture traversal rejected')
    if p.is_absolute():
        require(p.is_relative_to(FIXTURE_ROOT), 'foreign absolute fixture path rejected')
    else:
        p=FIXTURE_ROOT/p
    resolved=p.resolve(strict=True)
    require(resolved.is_relative_to(FIXTURE_ROOT), 'fixture path or symlink escapes approved root')
    return resolved


def historical_fixture_path(path):
    """Map an immutable receipt name once; resolved local paths are not remapped."""
    p=Path(path)
    require(p.is_absolute() and p.is_relative_to(LEGACY_FIXTURE_PREFIX),
            'historical fixture path outside pinned prefix')
    require('..' not in p.parts, 'historical fixture traversal rejected')
    return within(p.relative_to(LEGACY_FIXTURE_PREFIX))


def checked(path, pin, n=None):
    path=within(path);r=record(path)
    require(r['sha256']==pin,'SHA mismatch: '+str(path))
    require(n is None or r['bytes']==n,'byte count mismatch: '+str(path))
    return r


def extract(path, names, namespace):
    """Execute unchanged selected AST nodes from the pinned historical object."""
    raw=historical_source(path)
    source=ast.parse(raw); selected=[]; found=set()
    for node in source.body:
        ids={node.name} if isinstance(node,(ast.FunctionDef,ast.ClassDef)) else {
            t.id for target in node.targets for t in ast.walk(target) if isinstance(t,ast.Name)} if isinstance(node,ast.Assign) else set()
        if ids & names:
            selected.append(node);found.update(ids & names)
    require(found==names,'helper symbol closure')
    exec(compile(ast.Module(body=selected,type_ignores=[]),HEAD+':'+path,'exec'),namespace)
    return namespace


def load_arithmetic():
    names={'SIGN','EXPONENT','FRACTION','QUIET_NAN','NV','DZ','OF','UF','NX',
        '_validate_word','_is_nan','_is_snan','_is_inf','_decode_finite','_round_finite','mul_rne','add_rne'}
    integer=extract('src/heteronpu/rope_bf16_candidate.py',names,{'require':require})
    rational=extract('candidates/qwen2_resident_matrix/ffn_public/test_prefix_owners.py',
                     {'exact','rn','ref_add','ref_mul'},{'Fraction':Fraction,'lru_cache':lru_cache})
    return integer,rational

def rational_flags(operation,a,b,result,rational):
    """Independent exact-rational flags for finite binary32 add/multiply.

    Compare rounded encoding for NX, and separately round to unrestricted
    exponent/24-bit precision for HardFloat after-rounding tininess.
    """
    exact=rational['exact']
    number=exact(a)+exact(b) if operation=='add' else exact(a)*exact(b)
    if (result&0x7f800000)==0x7f800000: return 5  # finite inputs, OF|NX
    if exact(result)==number: return 0
    magnitude=abs(number)
    require(bool(magnitude),'exact zero cannot be inexact')
    exponent=magnitude.numerator.bit_length()-magnitude.denominator.bit_length()
    power=lambda e: Fraction(1<<max(e,0),1<<max(-e,0))
    if magnitude < power(exponent): exponent-=1
    quantum=power(exponent-23)
    units=magnitude/quantum
    quotient,remainder=divmod(units.numerator,units.denominator)
    quotient+=2*remainder>units.denominator or (2*remainder==units.denominator and quotient&1)
    tiny=quotient*quantum < power(-126)
    return 1 | (2 if tiny else 0)

class ArithmeticFailure(Exception):
    def __init__(self,key,reason): self.key=key;self.reason=reason;super().__init__(reason)

class Graph:
    def __init__(self,integer,rational):
        self.integer=integer;self.rational=rational;self.nodes={};self.counts=Counter();self.oracle_checks=0
    def op(self,key,operation,a,b):
        require(key not in self.nodes,'duplicate semantic node')
        require((a&0x7f800000)!=0x7f800000 and (b&0x7f800000)!=0x7f800000,'nonfinite operand')
        word,flags=self.integer[operation+'_rne'](a,b)
        reference=self.rational['ref_'+operation](a,b)
        require(word==reference,'independent rational result mismatch at '+str(key))
        require(flags==rational_flags(operation,a,b,reference,self.rational),'independent rational flags mismatch at '+str(key))
        self.oracle_checks+=1
        rejected=bool(flags&0x1c or operation=='add' and flags&2 or (word&0x7f800000)==0x7f800000)
        self.nodes[key]=(operation,a,b,word,flags,rejected)
        self.counts[operation]+=1
        if rejected: raise ArithmeticFailure(key,'overflow/invalid/nonfinite' if flags&0x1c or (word&0x7f800000)==0x7f800000 else 'legacy_add_underflow')
        return word
    def square(self,block,lane,residue,term,x):
        return self.op(('square',block,lane,residue,term),'mul',x,x)
    def term(self,block,lane,residue,term,a,b):
        return self.op(('term_add',block,lane,residue,term),'add',a,b)
    def residue(self,block,lane,residue,a,b):
        return self.op(('residue_add',block,lane,residue),'add',a,b)
    def finish(self,partials):
        total=0
        for lane in range(8):
            subtotal=0
            for residue in range(4):
                subtotal=self.op(('fold_residue',lane,residue),'add',subtotal,partials[4*lane+residue])
            total=self.op(('fold_lane',lane),'add',total,subtotal)
        return total

def scalar_order(x,integer,rational):
    """Literal existing owner sequence: chunk,lane,residue,localblock,term."""
    require(len(x)==2048,'H2048 row');g=Graph(integer,rational);partials=[None]*32
    for chunk in range(2):
        for lane in range(8):
            for residue in range(4):
                for localblock in range(2):
                    block=chunk*2+localblock;partial=0
                    for term in range(16):
                        index=chunk*1024+localblock*512+term*32+residue*8+lane
                        square=g.square(block,lane,residue,term,x[index])
                        partial=g.term(block,lane,residue,term,partial,square)
                    p=4*lane+residue
                    previous=0 if block==0 else partials[p]
                    partials[p]=g.residue(block,lane,residue,previous,partial)
    return g,g.finish(partials)

def grouped_order(x,integer,rational):
    """Two 16-lane batches, exact original p=4*lane+residue output layout.

    Within one input beat j=8*residue+lane; hardware slot i maps lane=4*g+i//4,
    residue=i%4. One MUL batch completes before its separate ADD batch. No FMA.
    Python lists here are diagnostic graph state, not a resource claim.
    """
    require(len(x)==2048,'H2048 row');g=Graph(integer,rational);partials=[None]*32
    for chunk in range(2):
        for localblock in range(2):
            block=2*chunk+localblock;block_acc=[0]*32
            for term in range(16):
                for group in range(2):
                    sq=[]
                    for i in range(16):
                        lane=4*group+i//4;residue=i%4
                        index=1024*chunk+512*localblock+32*term+8*residue+lane
                        sq.append(g.square(block,lane,residue,term,x[index]))
                    for i in range(16):
                        lane=4*group+i//4;residue=i%4;p=4*lane+residue
                        block_acc[p]=g.term(block,lane,residue,term,block_acc[p],sq[i])
            for group in range(2):
                for i in range(16):
                    lane=4*group+i//4;residue=i%4;p=4*lane+residue
                    previous=0 if block==0 else partials[p]
                    partials[p]=g.residue(block,lane,residue,previous,block_acc[p])
    return g,g.finish(partials)

def compare_graphs(old,new):
    require(set(old.nodes)==set(new.nodes),'semantic node set changed')
    for key in old.nodes:
        require(old.nodes[key]==new.nodes[key],'operands/result/flags/status mismatch at '+str(key))
    require(old.counts==new.counts=={'mul':2048,'add':2216},'reduction primitive counts')
    require(len(old.nodes)==4264,'reduction node count')
    return len(old.nodes)

def update_hashes(hashes,graph):
    for key,node in sorted(graph.nodes.items()):
        # A canonical, length-delimited semantic identity including operands and flags.
        raw=json.dumps([list(key),list(node)],separators=(',',':')).encode()+b'\n'
        hashes.setdefault(key[0],hashlib.sha256()).update(raw)
        hashes.setdefault('all',hashlib.sha256()).update(raw)

def core_ast_inventory(raw):
    tree=ast.parse(raw); result={}
    for node in tree.body:
        if getattr(node, 'name', None) in CORE_AST_SHA256:
            require(node.name not in result, 'duplicate core symbol: '+node.name)
            result[node.name]=sha(ast.dump(node, include_attributes=False).encode())
    require(result==CORE_AST_SHA256, 'preserved arithmetic AST mismatch')
    return result


def validate_sources():
    """Historical validation only. Current HEAD need not equal the old basis."""
    require(git_bytes('rev-parse', HEAD+'^{commit}').decode().strip()==HEAD,
            'historical commit object unavailable or not exact')
    records=[]
    for path,pin in PINS.items():
        raw=historical_source(path)
        records.append({'git_object':HEAD+':'+path, 'bytes':len(raw), 'sha256':sha(raw)})
    return records


def current_execution():
    """Audit live context separately; no live source is accepted as model input."""
    head=git_bytes('rev-parse', 'HEAD').decode().strip()
    records=[]
    for path in PINS:
        p=(ROOT/path).resolve()
        if not p.is_relative_to(ROOT):
            records.append({'relative_path':path,'state':'SYMLINK_OUTSIDE_ROOT_NOT_READ'})
        elif not p.is_file():
            records.append({'relative_path':path,'state':'ABSENT_NOT_MODEL_INPUT'})
        else:
            r=record(p);r['relative_path']=path;r['equals_historical_pin']=r['sha256']==PINS[path]
            records.append(r)
    return {'checkout':str(ROOT),'head':head,'pinned_path_worktree_records':records,
            'current_owner_proven':False,'live_sources_used_for_arithmetic':False}


def frozen_inventory():
    """Validate embedded historical metadata; never opens fixture payloads."""
    by_path={}
    for receipt in HISTORICAL_FIXTURE_INVENTORY:
        p=Path(receipt['path'])
        require(p.is_absolute() and p.is_relative_to(LEGACY_FIXTURE_PREFIX), 'inventory prefix')
        relative=p.relative_to(LEGACY_FIXTURE_PREFIX)
        require('..' not in relative.parts, 'inventory traversal')
        require(isinstance(receipt['bytes'],int) and receipt['bytes']>0, 'inventory byte count')
        require(len(receipt['sha256'])==64 and all(c in '0123456789abcdef' for c in receipt['sha256']), 'inventory digest')
        require(str(relative) not in by_path or by_path[str(relative)]==receipt, 'conflicting inventory record')
        by_path[str(relative)]=receipt
    fixtures=[]
    for tokens,pin in MANIFEST_SHA.items():
        matches=[r for p,r in by_path.items() if p.endswith('/manifest.json') and r['sha256']==pin]
        require(len(matches)==1, 'historical manifest inventory mismatch')
        fixtures.append({'tokens':tokens,'historical_manifest_receipt':matches[0]})
    require(set(MANIFEST_SHA)=={1,16,128}, 'frozen token inventory')
    return {'status':'PINNED_METADATA_ONLY','fixture_payloads_opened':False,
            'historical_receipt_entries':len(HISTORICAL_FIXTURE_INVENTORY),
            'unique_file_records':len(by_path),'fixtures':fixtures,
            'historical_fixture_runner':{'relative_path':RUNNER,'sha256':RUNNER_SHA,'bytes':RUNNER_BYTES}}


def verified_runner():
    p=within(RUNNER);checked(p,RUNNER_SHA,RUNNER_BYTES)
    raw=p.read_bytes();require(sha(raw)==RUNNER_SHA,'runner changed before parse')
    runner=json.loads(raw)
    require(runner['sources_unchanged'] and runner['fixtures_unchanged'],'historical fixture gate identity')
    require(runner['fixtures']==HISTORICAL_FIXTURE_INVENTORY,'historical fixture inventory changed')
    return runner


def fixture_from_runner(tokens):
    runner=verified_runner()
    matches=[r for r in runner['fixtures'] if r['sha256']==MANIFEST_SHA[tokens] and r['path'].endswith('/manifest.json')]
    require(len(matches)==1,'exact fixture pin in existing runner')
    receipt=matches[0];manifest=historical_fixture_path(receipt['path']);manifest_record=checked(manifest,receipt['sha256'],receipt['bytes'])
    raw=manifest.read_bytes();require(sha(raw)==receipt['sha256'],'manifest changed before parse')
    data=json.loads(raw);directory=manifest.parent
    require(data['tokens']==tokens and data['width']==2048,'fixture geometry')
    require(data['allowed_dut_input_files']==['stimulus/input.bf16le','stimulus/weights.bf16le'],'stimulus allowlist')
    require(set(data['assertion_only_files'])==set(data['files'])-set(data['allowed_dut_input_files']),'expected separation')
    require(data['source_tokens'] in (16,128) and data['source_row_start']==0,'frozen provenance')
    require(data['producer']['original_reduction_policy']=='torch_2_10_cpu_default_f32_8lane_4ilp_128','reduction recipe')
    file_records={}
    for name,r in data['files'].items():
        require(not Path(name).is_absolute() and '..' not in Path(name).parts, 'fixture filename traversal')
        path=within(directory/name);require(path.is_relative_to(directory),'fixture escape')
        require(r['role']==('DUT_MEMORY_INPUT' if name.startswith('stimulus/') else 'HOST_ASSERTION_ONLY'),'fixture role')
        file_records[name]=checked(path,r['sha256'],r['bytes'])
    parent=data['summary'];parent_record=checked(historical_fixture_path(parent['path']),parent['sha256'],parent['bytes'])
    require(any(r=={k:parent[k] for k in ('path','sha256','bytes')} for r in runner['fixtures']),
            'producer receipt absent from pinned historical runner')
    # Every real weight is verified but reduction does not depend on gamma/weight.
    weights=(directory/'stimulus/weights.bf16le').read_bytes()
    require(len(weights)==4096 and all((v[0]&0x7f80)!=0x7f80 for v in struct.iter_unpack('<H',weights)),'real weight domain')
    return directory,{'tokens':tokens,'manifest':receipt,'resolved_manifest':manifest_record,
                      'producer_summary':parent,'resolved_producer_summary':parent_record,'files':file_records,
                      'weight_arithmetic_use':'none: reduction-only stage; identity/domain verified'}


def directed_checks(integer,rational):
    # Constants are synthetic regression witnesses, never actual/model stimuli.
    cases=[
      ('add_positive_zero','add',0,0,0,0),
      ('add_negative_zero','add',0x80000000,0x80000000,0x80000000,0),
      ('mixed_zero','add',0x80000000,0,0,0),
      ('square_negative_zero','mul',0x80000000,0x80000000,0,0),
      ('cancel_exact','add',0x3f800001,0xbf800001,0,0),
      ('cancel_to_subnormal','add',0x00800000,0x807fffff,1,0),
      ('add_min_subnormals','add',1,1,2,0),
      ('tie_even_down','add',0x3f800000,0x33800000,0x3f800000,1),
      ('tie_even_up','add',0x3f800001,0x33800000,0x3f800002,1),
      ('negative_tie','add',0xbf800001,0xb3800000,0xbf800002,1),
      ('mul_exact_subnormal','mul',0x00800000,0x3f000000,0x00400000,0),
      ('mul_tie_zero','mul',1,0x3f000000,0,3),
      ('mul_tie_even_subnormal','mul',3,0x3f000000,2,3),
      ('mul_negative_tiny','mul',0x80000001,0x3f000000,0x80000000,3),
      ('hardfloat_tiny_rounds_normal','mul',0x00800000,0x3f7fffff,0x00800000,3),
      ('mul_overflow','mul',0x7f7fffff,0x40000000,0x7f800000,5),
      ('add_overflow','add',0x7f7fffff,0x7f7fffff,0x7f800000,5)]
    details=[]
    for name,op,a,b,expected,flags in cases:
        actual=integer[op+'_rne'](a,b);reference=rational['ref_'+op](a,b)
        require(actual==(expected,flags) and reference==expected,'directed primitive '+name)
        require(flags==rational_flags(op,a,b,reference,rational),'directed independent flags '+name)
        details.append({'name':name,'passed':True,'result_sha256':sha(packed([*actual]))})
    rows={
      'all_positive_zero':[0]*2048,
      'alternating_signed_zero':[0,0x80000000]*1024,
      'bf16_subnormal_and_square_underflow':[x<<16 for x in [1,0x8001,0x0080,0x8080,0x1a00,0x9a00,0x1a40,0x1a80]*256],
      'mixed_magnitude_rounding':[x<<16 for x in [0x3f80,0xbf80,0x3980,0xb980,0x3f81,0xbf81,0x3a00,0xba00]*256]}
    row_reports=[]
    for name,x in rows.items():
        old,a=scalar_order(x,integer,rational);new,b=grouped_order(x,integer,rational)
        count=compare_graphs(old,new);require(a==b,'directed sum');h={};update_hashes(h,old)
        row_reports.append({'name':name,'nodes':count,'graph_sha256':h['all'].hexdigest(),'sum_sha256':sha(packed([a])),'passed':True})
    for name,x in [('square_overflow',[0x60000000]+[0]*2047),('accumulate_overflow',[0x5f000000]*2048)]:
        failures=[]
        for fn in (scalar_order,grouped_order):
            try:fn(x,integer,rational)
            except ArithmeticFailure as e:failures.append({'node':list(e.key),'reason':e.reason})
            else:raise AssertionError('overflow accepted: '+name)
        require(failures[0]['reason']==failures[1]['reason'],'failure class changed')
        row_reports.append({'name':name,'expected_rejection':True,'schedules':failures,'output_published':False,'passed':True})
    # A one-round fused multiplication is explicitly a different graph.
    a,b,c=0x3f800001,0x3f7ffffe,0xbf800000
    product=integer['mul_rne'](a,b)[0];unfused=integer['add_rne'](product,c)[0]
    fused=rational['rn'](rational['exact'](a)*rational['exact'](b)+rational['exact'](c))
    require(unfused!=fused,'FMA negative control must discriminate')
    return {'primitive_cases':details,'row_cases':row_reports,'fma_negative_control_discriminates':True,
            'cancellation_scope':'primitive add only: valid RMS squares are nonnegative'}

def run_fixture(tokens,integer,rational):
    directory,report=fixture_from_runner(tokens)
    oldhash,newhash={},{};sumhash=hashlib.sha256();sqhash=hashlib.sha256();nodes=0;oracle_checks=0
    ascending_differences=0;actual_counts=Counter()
    # Expected readers are outside model functions; no expected value is an operand.
    with (directory/'stimulus/input.bf16le').open('rb') as source, (directory/'expected/squares.fp32le').open('rb') as squares_expected, (directory/'expected/sum.fp32le').open('rb') as sum_expected:
        for token in range(tokens):
            raw=source.read(4096);require(len(raw)==4096,'short stimulus');x=[w[0]<<16 for w in struct.iter_unpack('<H',raw)]
            require(all((w&0x7f800000)!=0x7f800000 for w in x),'finite BF16 stimulus')
            old,a=scalar_order(x,integer,rational);new,b=grouped_order(x,integer,rational)
            nodes+=compare_graphs(old,new);require(a==b,'sum mismatch');oracle_checks+=old.oracle_checks+new.oracle_checks
            update_hashes(oldhash,old);update_hashes(newhash,new);actual_counts.update(old.counts)
            squares=[None]*2048
            for key,node in old.nodes.items():
                if key[0]=='square':
                    _,block,lane,residue,term=key;squares[512*block+32*term+8*residue+lane]=node[3]
            actual_squares=packed(squares);actual_sum=packed([a])
            require(actual_squares==squares_expected.read(8192),'frozen squares mismatch at token '+str(token))
            require(actual_sum==sum_expected.read(4),'frozen sum mismatch at token '+str(token))
            sqhash.update(actual_squares);sumhash.update(actual_sum)
            wrong=0
            for square in squares:wrong=integer['add_rne'](wrong,square)[0]
            ascending_differences+=wrong!=a
        require(not source.read(1) and not squares_expected.read(1) and not sum_expected.read(1),'trailing fixture data')
    old_digest={k:v.hexdigest() for k,v in oldhash.items()};new_digest={k:v.hexdigest() for k,v in newhash.items()}
    require(old_digest==new_digest,'canonical hash mismatch')
    report.update(status='BITEXACT_REDUCTION_MODEL_ONLY',semantic_nodes_compared=nodes,
      independent_integer_vs_rational_operation_checks=oracle_checks,primitive_counts=dict(actual_counts),
      scalar_schedule_node_sha256=old_digest,grouped_schedule_node_sha256=new_digest,
      squares_sha256=sqhash.hexdigest(),sum_sha256=sumhash.hexdigest(),
      frozen_squares_bit_mismatches=0,frozen_sum_bit_mismatches=0,per_node_operands_result_flags_mismatches=0,
      wrong_ascending_sum_differing_rows=ascending_differences,expected_numeric_reads=['squares','sum'],
      inverse_loaded_as_operand=False,full_rms_tested=False)
    return report

def main(argv=None):
    global ROOT,FIXTURE_ROOT
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,required=True,help='Explicit checkout containing historical Git objects')
    parser.add_argument('--fixture-root',type=Path,help='Relocated fixture tree root; preserve work/ relative paths')
    parser.add_argument('--run-actual',action='store_true',help='Run directed arithmetic and ALL frozen M1/M16/M128 fixtures')
    parser.add_argument('--out',type=Path,required=True,help='New metadata-only output directory')
    args=parser.parse_args(argv)
    ROOT=args.root.resolve(strict=True)
    require(ROOT.is_dir(), '--root must be a directory')
    out=args.out.resolve();out.mkdir(parents=True,exist_ok=False)
    summary={'status':'RUNNING','scope':'PYTHON_BEHAVIOR_REDUCTION_EQUIVALENCE_ONLY',
      'historical_basis_commit':HEAD,'original_success_inherited':False,
      'historical_behavior_evidence':{'summary_receipt':HISTORICAL_BEHAVIOR_SUMMARY,
         'original_script_receipt':ORIGINAL_SCRIPT,'status':'HISTORICAL_ONLY_NOT_REEXECUTED_BY_PACKAGING'},
      'rtl_executed':False,'eda_executed':False,'official_model_rerun':False,'weights_downloaded':False,
      'behavior_model_executed':False,
      'physical_performance_measured':False,'physical_resource_realization_proven':False,
      'sqrt_div_or_inverse_computed':False,'numpy_used':False,'host_floating_point_used':False,
      'current_owner_proven':False,'full_rms_tested':False,
      'script':record(Path(__file__)),'failures':[],
      'groups':{'cold_structure':{'status':'NOT_EXECUTED'},
                'directed_arithmetic':{'status':'NOT_EXECUTED'},
                'external_actual_fixtures':{'status':'NOT_EXECUTED','tokens':[1,16,128],
                   'reason':'Requires --run-actual and external exact-pinned fixture bytes'}},
      'behavior_model_rerun_required':True}
    success=False
    try:
        before=validate_sources();execution_before=current_execution()
        summary['historical_source_validation']={'commit':HEAD,'records':before,'status':'VERIFIED'}
        summary['current_execution_before']=execution_before
        inventory=frozen_inventory()
        core=core_ast_inventory(Path(__file__).read_bytes())
        summary['groups']['cold_structure']={'status':'PASS_COLD_STRUCTURE_ONLY',
          'core_ast_sha256':core,'fixture_inventory':inventory,'fixture_payloads_opened':False}
        if args.run_actual:
            require(args.fixture_root is not None,'--run-actual requires explicit --fixture-root')
            FIXTURE_ROOT=args.fixture_root.resolve(strict=True)
            require(FIXTURE_ROOT.is_dir(),'--fixture-root must be a directory')
            # Preflight EVERY external identity before any numerical execution.
            preflight=[fixture_from_runner(m)[1] for m in (1,16,128)]
            summary['fixture_root']=str(FIXTURE_ROOT)
            summary['groups']['external_actual_fixtures']['status']='RUNNING'
            summary['groups']['external_actual_fixtures']['identity_preflight']='VERIFIED_ALL_PINS_AND_BYTES'
            summary['groups']['directed_arithmetic']['status']='RUNNING'
            integer,rational=load_arithmetic()
            summary['directed']=directed_checks(integer,rational)
            summary['groups']['directed_arithmetic']['status']='PASS_DIRECTED_ARITHMETIC'
            summary['cases']=[]
            for m in (1,16,128):
                summary['cases'].append(run_fixture(m,integer,rational))
                print(json.dumps({'tokens':m,'status':summary['cases'][-1]['status'],
                                  'nodes':summary['cases'][-1]['semantic_nodes_compared']}),flush=True)
            for initial,case in zip(preflight,summary['cases']):
                _,current=fixture_from_runner(case['tokens'])
                require(current==initial,'fixture identities changed during run')
                require(current['files']==case['files'],'fixture identities changed before arithmetic')
            summary['groups']['external_actual_fixtures'].update(status='PASS_BITEXACT_REDUCTION_MODEL_ONLY',
                reason='Fresh execution completed for all three exact-pinned historical fixtures')
            summary.update(status='PASS_BITEXACT_REDUCTION_MODEL_ONLY',fixtures_unchanged=True,
              counts_per_token={'square_mul':2048,'term_add':2048,'residue_add':128,'fold_residue':32,'fold_lane':8,'total':4264},
              arithmetic='Pinned repository integer dyadic FP32 RNE with flags, independently checked bits and flags against pinned exact rational helper plus rational tininess oracle per operation',
              grouping='g=0,1; i=0..15; lane=4*g+i//4; residue=i%4; input[chunk*1024+block_local*512+term*32+8*residue+lane]; p=4*lane+residue',
              final_tree='Every block starts +0 and adds term0..15; every residue starts +0 and adds global block0..3; every lane starts +0 and adds residue0..3; total starts +0 and adds lane0..7',
              deferred_scalar='mean=MulIeeeRne(sum,0x3a000000); mean_eps=Add(mean,0x358637bd); root=Sqrt(mean_eps); inverse=Div(0x3f800000,root). Not executed in this stage.',
              official_limit='Pinned official class uses torch.rsqrt. Frozen default-CPU recipe/observations support this finite test set; no universal rsqrt versus sqrt/div proof or new official model execution is claimed.',
              behavior_limit='Node bits/flags and intended reject policy checked. This model does not prove transaction timing, cancellation, vector exception aggregation, memory ports or resource realization.')
        else:
            summary['status']='PASS_COLD_STRUCTURE_ONLY'
        after=validate_sources();require(before==after,'historical source changed during run')
        summary['historical_sources_unchanged']=True
        summary['current_execution_after']=current_execution()
        summary['current_execution_unchanged']=execution_before==summary['current_execution_after']
        require(record(Path(__file__))==summary['script'],'script changed during run')
        if args.run_actual:
            summary['behavior_model_executed']=True
            summary['behavior_model_rerun_required']=False
        success=True
    except Exception as e:
        summary['status']='FAILED'
        summary['failures'].append({'type':type(e).__name__,'message':str(e),'traceback':traceback.format_exc()})
        for group in summary['groups'].values():
            if group['status']=='RUNNING':group['status']='FAILED'
    (out/'summary.json').write_bytes(dump(summary))
    (out/'failures.json').write_bytes(dump(summary['failures']))
    (out/'receipt.json').write_bytes(dump({'summary':record(out/'summary.json'),
        'failures':record(out/'failures.json'),'script':record(Path(__file__))}))
    print(json.dumps({'status':summary['status'],'summary':record(out/'summary.json')}),flush=True)
    return 0 if success else 1


if __name__=='__main__':raise SystemExit(main())
