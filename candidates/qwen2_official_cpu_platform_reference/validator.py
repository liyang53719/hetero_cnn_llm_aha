"""Fail-closed local evidence validation. No API here grants execution or freeze."""
import copy
import json
from pathlib import Path
from . import policy as P
from candidates.qwen2_fullblock_ci_reference import repeat_observation as B
from candidates.qwen2_fullblock_ci_reference import comparison_diagnostic as C
from candidates.qwen2_fullblock_ci_reference import all_comparisons as A
from candidates.qwen2_fullblock_ci_dut import platform_freeze as F
from candidates.qwen2_fullblock_ci_execution import closure as BASE
from candidates.qwen2_fullblock_ci_execution import runtime_profile as PROFILE

ROOT=Path(__file__).resolve().parents[2]


def need(ok,message='invalid new-reference evidence'):
    if not ok:raise ValueError(message)


def exact(value,keys):
    need(type(value) is dict and all(type(k) is str for k in value) and set(value)==set(keys))


def digest(value):
    need(type(value) is str and len(value)==64 and all(c in '0123456789abcdef' for c in value))
    return value


def parse(raw):
    need(type(raw) is bytes and 0<len(raw)<=262144)
    def unique(pairs):
        result={}
        for key,value in pairs:
            need(key not in result);result[key]=value
        return result
    return json.loads(raw,object_pairs_hook=unique)


def source_digest(root=ROOT):
    """Actual source-only closure; external certificate/observations are excluded."""
    root=Path(root);need(root==ROOT and root.resolve()==root)
    paths=[P.PACKAGE+'/'+name for name in P.FILES]+[P.PLATFORM_SOURCE,P.ORIGINAL_PINS,P.DUT_PINS,P.PAIR_WORKFLOW]
    files={}
    for relative in paths:
        path=root/relative;need(path.resolve()==path and not any(p.is_symlink() for p in (path,*path.parents)))
        raw=path.read_bytes();files[relative]=dict(bytes=len(raw),sha256=P.sha(raw))
    need(files[P.ORIGINAL_PINS]['sha256']==P.ORIGINAL_PINS_SHA256)
    need(files[P.DUT_PINS]['sha256']==P.DUT_PINS_SHA256)
    return P.sha(P.encoded(dict(base_source_closure=BASE.digest(root),files=files)))


def platform_read_paths(python_identity):
    """Exact local read set for a future audit hook; never a directory grant.

    Supply the already-verified resolved setup-python identity from initialize.
    The existing observer still checks real canonical paths and mapped libpython.
    """
    exact(python_identity,('path','bytes','sha256'))
    need(type(python_identity['path']) is str and type(python_identity['bytes']) is int and
        {k:python_identity[k] for k in ('bytes','sha256')}==F.PYTHON_IDENTITY)
    path=Path(python_identity['path'])
    need(str(path)==python_identity['path'] and path.is_relative_to(F.PYTHON_HOME) and '..' not in path.parts)
    return (python_identity['path'],str(F.LIBPYTHON),'/proc/self/maps')


def observe_platform_before(*,execute=False):
    """Reuse exact CI-only observer. Local large-ELF platforms remain refused."""
    return F.observe(execute=execute)


def observe_platform_after(before):
    return F.verify_same(before)


def _platform(before,after):
    keys=('schema','status','scope','python_version','process_id','python','libpython',
          'independently_reviewed','historical_equivalence_claimed','full_system_closure','numeric_execution_allowed')
    for value in (before,after):
        exact(value,keys)
        need(type(value['schema']) is int and value['schema']==1 and
            value['status']=='CURRENT_PROCESS_PLATFORM_OBSERVED_ONLY' and
            value['scope']=='PYTHON_ELF_AND_LOADED_LIBPYTHON_ONLY' and
            type(value['python_version']) is list and all(type(n) is int for n in value['python_version']) and
            value['python_version']==[3,12,14] and type(value['process_id']) is int and value['process_id']>0)
        for flag in ('independently_reviewed','historical_equivalence_claimed','full_system_closure','numeric_execution_allowed'):
            need(value[flag] is False)
        for name in ('python','libpython'):
            spec=value[name];exact(spec,('path','bytes','sha256','device','inode'))
            need(type(spec['path']) is str and type(spec['bytes']) is int and spec['bytes']>0)
            digest(spec['sha256'])
            need(type(spec['device']) is int and spec['device']>=0 and type(spec['inode']) is int and spec['inode']>0)
        python=value['python'];need(str(Path(python['path']))==python['path'] and '..' not in Path(python['path']).parts and
            Path(python['path']).is_relative_to(F.PYTHON_HOME) and
            {k:python[k] for k in ('bytes','sha256')}==F.PYTHON_IDENTITY)
        need(value['libpython']['path']==str(F.LIBPYTHON))
    need(F.same(before,after),'same-process platform boundary drift')


def validate(observation,certificate_raw,*,expected_certificate_sha256,expected_source_sha256,root=ROOT):
    """Validate private evidence, return PENDING; this cannot authorize a run.

    Expected digests must come from separately reviewed launcher inputs. Actual
    source closure and original source bytes are recomputed here, not trusted as
    a second caller-supplied string. No observation bytes are written or uploaded.
    """
    digest(expected_certificate_sha256);digest(expected_source_sha256)
    need(P.sha(certificate_raw)==expected_certificate_sha256,'external certificate bytes drift')
    need(source_digest(root)==expected_source_sha256,'actual source closure drift')
    # This helper checks a byte commitment only. The sole admission authority is
    # issuer.validate_certificate(), reusing the existing external review schema.
    # Do not invent a second certificate format or infer authority from fields.
    need(type(parse(certificate_raw)) is dict,'certificate JSON object required')
    exact(observation,('schema','run_id','source_closure_sha256','boundary_before','boundary_after',
                      'platform_before','platform_after','runtime','backend_before','backend_after',
                      'typed_inputs','outputs','legacy_comparison'))
    need(type(observation['schema']) is int and observation['schema']==1 and observation['run_id'] in ('new01','new02') and
        observation['source_closure_sha256']==expected_source_sha256)
    raw=(Path(root)/P.ORIGINAL_PINS).read_bytes();pins=P.original(raw)
    requirements=PROFILE.apply(pins,{PROFILE.PROFILE_ENV:P.PROFILE,'ATEN_CPU_CAPABILITY':'avx2'})['runtime_requirements']
    need(F.same(observation['runtime'],requirements),'fixed arithmetic runtime drift')
    backend=dict(profile=P.PROFILE,mkldnn_enabled=False,threads=4,interop_threads=1,deterministic_algorithms=True)
    need(F.same(observation['backend_before'],backend) and F.same(observation['backend_after'],backend),'backend setting drift')
    before=observation['boundary_before'];after=observation['boundary_after']
    for boundary in (before,after):
        need(type(boundary) is dict and 'platform_files' in boundary,'loaded platform boundary required')
        B._boundary({k:v for k,v in boundary.items() if k!='platform_files'},True)
        need(F.same(boundary['platform_files'],{k:observation['platform_before'][k] for k in ('python','libpython')}),
             'loaded platform boundary identity drift')
    need(F.same(before,after) and before['external_certificate_sha256']==expected_certificate_sha256 and
        before['source_closure_sha256']==expected_source_sha256,'capture boundary drift')
    _platform(observation['platform_before'],observation['platform_after'])
    platform=observation['platform_before']
    expected_native=copy.deepcopy(pins['runtime_native_files'])
    expected_native['python']={k:platform['python'][k] for k in ('path','bytes','sha256')}
    need(F.same(before['native_files'],expected_native),'six native identities drift')
    raw_expected={P.RAW_ROOTS[s['manifest_role']]+'/'+s['local_name']+'.bin':
        {k:s[k] for k in ('bytes','sha256')} for s in pins['raw_tensors']}
    need(F.same(before['raw13'],raw_expected),'fixed raw path/content drift')
    typed=observation['typed_inputs'];exact(typed,pins['producer_roles'])
    for name,spec in typed.items():
        exact(spec,('bytes','sha256'))
        need(F.same(spec,{k:pins['producer_roles'][name][k] for k in ('bytes','sha256')}),'typed input content drift')
    outputs=observation['outputs'];geometry=P.geometry(raw);exact(outputs,geometry)
    for name,spec in outputs.items():
        exact(spec,set(C.FIELDS)|{'file'})
        need(type(spec['file']) is str and spec['file']==name+'.f32le' and C._record({k:spec[k] for k in C.FIELDS}))
        need(F.same({k:spec[k] for k in geometry[name]},geometry[name]),'new29 geometry/dtype drift')
    A.checked(observation['legacy_comparison'])  # Differences are retained, never a rejection criterion.
    return dict(schema=1,status='VALIDATED_LOCAL_PENDING_REVIEW',contract_id=P.policy()['contract_id'],
        complete_outputs=29,source_certificate_bytes_checked=True,source_authority_verified=False,
        same_fixed_environment_only=True,reference_freeze_available=False,dut_authorized=False,
        numerical_acceptance_claimed=False,legacy_failures_preserved=True)
