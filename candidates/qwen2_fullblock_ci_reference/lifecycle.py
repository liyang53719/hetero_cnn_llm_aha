"""Original one-use lifecycle, with a distinct CI namespace and extra binding review."""
from pathlib import Path
import sys
import recipe as R
import issuer as I
import backend_policy as BP
B = R.legacy('lifecycle.py')
WORK = R.WORK
B.WORK = WORK
WALL_SECONDS,RSS_BYTES = B.WALL_SECONDS,B.RSS_BYTES
LOG_RETAIN_BYTES,LOG_EMITTED_LIMIT,POLL_SECONDS = B.LOG_RETAIN_BYTES,B.LOG_EMITTED_LIMIT,B.POLL_SECONDS
identity,write_new,last_stage = B.identity,B.write_new,B.last_stage

def progress(recipe,out,stage):
    BP.before_stage(recipe,stage)
    return B.progress(recipe,out,stage)
directory_inventory,bytes_under = B.directory_inventory,B.bytes_under
validate_payload_inventory,verify_parent_entry = B.validate_payload_inventory,B.verify_parent_entry

def run_path(recipe,run_id,mode):
    recipe.need(mode == 'bootstrap','CI frozen mode awaits independent new bootstrap review and source change')
    return B.run_path(recipe,run_id,mode)

def validate_go(recipe,pins,path,run_id,mode):
    """Original single-GO checks plus explicit source-policy bootstrap review.

    Unlike the historical review, this review authorizes fixed derivation of new
    identities; it must explicitly deny independent review of future observations.
    It does not assert that the review tool is the later CI Python executable.
    """
    run_path(recipe,run_id,mode)
    target = recipe.safe_path(recipe.ROOT,path)
    recipe.need(target.is_relative_to(recipe.ROOT/WORK) and target.stat().st_size <= 16384,'bounded CI go')
    go = recipe.parse(target.read_bytes())
    recipe.exact_keys(go,('schema','action','run_id','source_manifest','source_review','issued_by',
                          'maximum_invocations','no_retry','exclusive_numeric_slot'),'single go')
    recipe.fields(go,dict(schema=1,action='single-'+mode,run_id=run_id,
        source_manifest=recipe.source_manifest(),maximum_invocations=1,no_retry=True,
        exclusive_numeric_slot=True),'single go')
    recipe.need(type(go['issued_by']) is str and go['issued_by'].strip(),'explicit go issuer')
    review_spec = go['source_review']
    recipe.exact_keys(review_spec,('path','bytes','sha256'),'review identity')
    recipe.need(type(review_spec['bytes']) is int and 0 < review_spec['bytes'] <= 262144,'bounded source review')
    review_path = recipe.safe_path(recipe.ROOT,review_spec['path'])
    recipe.need(review_path.is_relative_to(recipe.ROOT/WORK),'fresh CI review namespace')
    review = recipe.parse(recipe.checked(recipe.ROOT,review_spec['path'],review_spec))
    I.validate_expansion(review,pins)
    recipe.fields(review,dict(status='APPROVED_SOURCE_FOR_SINGLE_BOOTSTRAP',
        source_manifest=go['source_manifest'],mode=mode,numeric_executed=False,
        ci_binding_policy=recipe.bootstrap_policy(),historical_receipts_revalidated=False,
        observed_bindings_independently_reviewed=False),'independent CI source-policy review')
    recipe.need(go['issued_by'] == I.ISSUER and type(review.get('reviewer')) is str and review['reviewer'].strip() and
                review['reviewer'] != go['issued_by'],'distinct independent reviewer and disclosed issuer')
    recipe.need(run_id == I.RUN_ID,'certificate permits only ci01 bootstrap')
    recipe.fields(review.get('tool_identity'),dict(implementation='cpython',python_major_minor=[3,12],
        source_manifest=go['source_manifest']),'review tool/source identity')
    # Independently derive and validate the new binding; never label it reviewed.
    recipe.need(recipe.same(pins,recipe.load_pins()),'observed CI bindings drift at admission')
    return dict(receipt=dict(path=str(target.relative_to(recipe.ROOT)),**identity(target)),content=go)


def claim_capability(recipe,pins,out,mode,fd):
    run_path(recipe,out.parent.name,mode)
    return B.claim_capability(recipe,pins,out,mode,fd)

def snapshot(recipe,pins):
    recipe.need(recipe.same(pins,recipe.load_pins()),'effective execution binding drift')
    metadata = recipe.source_check(recipe.ROOT,pins)
    certificate_sha,closure_sha = I.external_pins()
    recipe.need(I.source_closure_digest() == closure_sha,'aggregate source closure drift at capture boundary')
    result = dict(external_certificate_sha256=certificate_sha,source_closure_sha256=closure_sha,
        source_manifest=recipe.source_manifest(),
        pins=identity(recipe.ROOT/recipe.BINDING),effective_pins_sha256=recipe.sha(recipe.encoded(pins)),
        sources={},raw13={},native_files={},input_proofs={},raw_support={},
        historical_receipts_revalidated=False)
    for path,pin in pins['sources'].items():
        actual = identity(recipe.safe_path(recipe.ROOT,path))
        recipe.fields(actual,{k:pin[k] for k in ('bytes','sha256')},'source '+path)
        result['sources'][path] = actual
    for pin in pins['raw_tensors']:
        actual = identity(recipe.safe_path(recipe.ROOT,pin['path']))
        recipe.fields(actual,{k:pin[k] for k in ('bytes','sha256')},'raw '+pin['path'])
        result['raw13'][pin['path']] = actual
    for path,pin in metadata['proof_files'].items():
        actual = identity(recipe.safe_path(recipe.ROOT,path))
        recipe.need(recipe.same(actual,pin),'input receipt drift')
        result['input_proofs'][path] = actual
    for name,pin in pins['runtime_native_files'].items():
        path = Path(pin['path']) if Path(pin['path']).is_absolute() else recipe.safe_path(recipe.ROOT,pin['path'])
        actual = dict(path=pin['path'],**identity(path))
        recipe.need(recipe.same(actual,pin),'native runtime hash drift')
        result['native_files'][name] = actual
    recipe.need(Path(sys.executable).resolve() == Path(pins['runtime_native_files']['python']['path']).resolve(),'Python identity')
    return result
