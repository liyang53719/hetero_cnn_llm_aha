"""Original capability/budgets plus actual loaded-libpython boundary identity."""
import sys
import recipe as R
import issuer as I
BP=R.load_ci('backend_policy.py')
sys.modules['backend_policy']=BP
L=R.load_ci('lifecycle.py')
for key in dir(L):
    if not key.startswith('_'):globals()[key]=getattr(L,key)
_original_snapshot=L.snapshot
_original_payload=L.validate_payload_inventory


def snapshot(recipe,pins):
    result=_original_snapshot(recipe,pins)
    actual=R.observe_platform_before(execute=True)
    R.observe_platform_after(actual)
    result['platform_files']={k:actual[k] for k in ('python','libpython')}
    return result


def validate_payload_inventory(recipe,pins,out,observations):
    # Keep all original exact inventory/bytes/hash/geometry/alias/mask checks.
    _original_payload(recipe,pins,out,observations)
    recipe.fields(observations,dict(contract_id=R.NEW_PLATFORM_REFERENCE_CONTRACT,
        status='NEW_PLATFORM_REFERENCE_OBSERVATIONS_PENDING_REVIEW',numerical_acceptance_claimed=False,
        dut_executed=False,old_pass_inherited=False,full_29_node_acceptance=False),'new observations')
    R.V._platform(observations['platform_before'],observations['platform_after'])
    stable={k:observations['platform_before'][k] for k in ('python','libpython')}
    before=recipe.parse((out/'BOUNDARY_BEFORE.json').read_bytes())
    recipe.need(recipe.same(stable,before['platform_files']),'worker loaded-libpython boundary binding')
    legacy=observations['legacy_contract_diagnostic']
    recipe.exact_keys(legacy,('status','compared_count','equal_count','records'),'legacy comparison')
    rows=legacy['records'];recipe.need(type(rows) is list and len(rows)==18,'actual legacy18 comparisons')
    for i,row in enumerate(rows):
        recipe.exact_keys(row,('node','equal'),'legacy record')
        recipe.need(row['node']=='NODE_%02d'%i and type(row['equal']) is bool,'fixed legacy enum')
    count=sum(row['equal'] for row in rows)
    recipe.need(type(legacy['compared_count']) is int and legacy['compared_count']==18 and
        type(legacy['equal_count']) is int and legacy['equal_count']==count and
        legacy['status']==('LEGACY_CONTRACT_EQUAL' if count==18 else 'LEGACY_CONTRACT_DIFFERENT'),
        'legacy result is diagnostic only, never a new-reference PASS')
