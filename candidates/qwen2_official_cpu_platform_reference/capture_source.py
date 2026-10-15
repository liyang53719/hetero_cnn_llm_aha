"""Exact source-derived new-contract entry; importing/building never captures.

The original files stay unchanged. A new reviewed lifecycle/recipe must supply
its own capability and pending-contract interfaces before this can execute.
"""
import ast
import types
from pathlib import Path
from . import policy as P

CAPTURE='candidates/qwen2_fullblock_reference_m128/capture.py'
RECIPE='candidates/qwen2_fullblock_reference_m128/recipe.py'
CAPTURE_SHA='7bbee0a7edc6d36fb4996657ecea75c5181d292c9761bbb18ca4b12fc2486a86'
RECIPE_SHA='2548e4b447ac58580c0e941bdc5287f2fcbc9dea861bb2d0c601884e5dd2ff36'
CONTRACT=P.policy()['contract_id']

# Each replacement is exact and unique. Their inverse must recover every byte
# of the original module; no math/AST extraction or expressions are rewritten.
EDITS=(
    ('    R = recipe\n', "    R = recipe\n    R.need(stage == 'bootstrap' and getattr(R,'NEW_PLATFORM_REFERENCE_CONTRACT',None) == '"+CONTRACT+"', 'new reference contract only; freeze unavailable')\n"),
    ('    before = boundary()\n','    platform_before = R.observe_platform_before(execute=True)\n    before = boundary()\n'),
    ("    L.progress(R,out,'official-holder-construction-and-raw-bindings')\n",
     "    L.progress(R,out,'official-holder-construction-and-raw-bindings')\n    R.need(torch.backends.mkldnn.enabled is False, 'new reference backend must be disabled')\n"),
    ('    records,raw_outputs = {},{}\n','    records,raw_outputs = {},{}\n    legacy_prior18 = {}\n'),
    ("            R.need(R.same(actual,pins['prior18_expectations'][name]), 'fresh prior18 exact reproduction '+name)",
     "            legacy_prior18[name] = R.same(actual,pins['prior18_expectations'][name])"),
    ('    after = boundary()\n','    after = boundary()\n    platform_after = R.observe_platform_after(platform_before)\n    R.need(torch.backends.mkldnn.enabled is False, \'new reference backend changed\')\n'),
    ("    result = {'status':'BOOTSTRAP_UNACCEPTED_NO_NUMERICAL_VERDICT' if bootstrap else 'FRESH_OFFICIAL_AST_FULLBLOCK_CAPTURE_ONLY',",
     "    R.need(set(legacy_prior18) == set(pins['prior18_expectations']) and len(legacy_prior18) == 18, 'legacy comparison complete')\n    result = {'status':'NEW_PLATFORM_REFERENCE_OBSERVATIONS_PENDING_REVIEW',\n        'contract_id':R.NEW_PLATFORM_REFERENCE_CONTRACT,'platform_before':platform_before,'platform_after':platform_after,"),
    ("        'prior18_fresh_hash_matches':True,'frozen29_hash_matches':None if bootstrap else True}",
     "        'legacy_contract_diagnostic':{'status':'LEGACY_CONTRACT_EQUAL' if all(legacy_prior18.values()) else 'LEGACY_CONTRACT_DIFFERENT',\n            'compared_count':18,'equal_count':sum(legacy_prior18.values()),\n            'records':[{'node':'NODE_%02d'%i,'equal':legacy_prior18[n]} for i,n in enumerate(sorted(legacy_prior18))]},\n        'legacy_frozen29_comparison_performed':False}"),
    ('    R.validate_observations(records,pins)\n','    R.validate_new_observations(records,pins)\n'),
    ("                stream.write(data)\n", "                stream.write(data)\n            R.need((out/name).read_bytes() == data, 'new reference payload readback')\n"),
    ("        stream.write(files[manifest_name])\n", "        stream.write(files[manifest_name])\n    R.need((out/manifest_name).read_bytes() == files[manifest_name], 'new reference metadata readback')\n"),
)
LEGACY_VALIDATION="""        if name in pins['prior18_expectations']:
            need(same({k:v for k,v in spec.items() if k != 'file'},pins['prior18_expectations'][name]),
                 name+' fresh prior18 reproduction')
"""


def derive(capture_raw,recipe_raw):
    if (type(capture_raw) is not bytes or type(recipe_raw) is not bytes or
        P.sha(capture_raw)!=CAPTURE_SHA or P.sha(recipe_raw)!=RECIPE_SHA):
        raise ValueError('fixed original source drift')
    original=capture_raw.decode();derived=original
    for old,new in EDITS:
        if derived.count(old)!=1:raise ValueError('unique capture edit required')
        derived=derived.replace(old,new,1)
    reverse=derived
    for old,new in reversed(EDITS):
        if reverse.count(new)!=1:raise ValueError('unique inverse capture edit required')
        reverse=reverse.replace(new,old,1)
    if reverse!=original:raise ValueError('original arithmetic source changed')
    tree=ast.parse(recipe_raw);node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='validate_observations')
    validation=ast.get_source_segment(recipe_raw.decode(),node)+'\n'
    if validation.count(LEGACY_VALIDATION)!=1:raise ValueError('unique legacy validator gate required')
    validation=validation.replace(LEGACY_VALIDATION,'',1).replace('def validate_observations(', 'def validate_new_observations(',1)
    ast.parse(derived);ast.parse(validation)
    return dict(capture_source=derived,validation_source=validation,
        proof=dict(original_capture_sha256=CAPTURE_SHA,original_recipe_sha256=RECIPE_SHA,
            original_capture_byte_reconstruction=True,original_capture_ast_reconstruction=
            ast.dump(ast.parse(reverse),include_attributes=False)==ast.dump(ast.parse(original),include_attributes=False),
            official_math_rewritten=False,legacy_gate_replacements=2,numerical_execution=False))


def load(root):
    """Cold source load only; the returned entry still needs the original capability."""
    root=Path(root);raws=[]
    for relative in (CAPTURE,RECIPE):
        path=root/relative
        if path.resolve()!=path or any(p.is_symlink() for p in (path,*path.parents)):raise ValueError('source alias')
        raws.append(path.read_bytes())
    source=derive(*raws)
    # Load only the exact original recipe's stdlib source namespace, then replace
    # the separate validator function in that private namespace, never globally.
    namespace={'__name__':'_new_platform_geometry','__file__':str(root/RECIPE)}
    exec(compile(raws[1],str(root/RECIPE),'exec'),namespace)
    exec(compile(source['validation_source'],str(Path(__file__).resolve()),'exec'),namespace)
    module=types.ModuleType('_new_platform_capture')
    module.__file__=str(Path(__file__).resolve())
    exec(compile(source['capture_source'],module.__file__,'exec'),module.__dict__)
    return module.capture,namespace['validate_new_observations'],source['proof']
