"""Parent-owned full original export/small-gate verification, without a forward.

Cold import is stdlib-only. This command is never run in source-only tests.
"""
import argparse
import importlib.util
import os
from pathlib import Path
import sys
import time


def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec)
    exec(compile(Path(path).read_bytes(),str(path),'exec'),module.__dict__)
    return module


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('root','workspace','context','out'): parser.add_argument('--'+name,type=Path,required=True)
    for name in ('context-sha256','manifest-sha256'): parser.add_argument('--'+name,required=True)
    args=parser.parse_args(argv)
    here=Path(__file__).resolve().parent
    launcher=load('fresh_verifier_launch',here/'launch.py')
    launcher.need(sys.version_info[:3]==(3,12,15) and sys.flags.isolated and not sys.flags.optimize,'isolated verifier runtime')
    contract=launcher.load_contract(args.root)
    context=launcher.strict(launcher.safe(args.context,65536),65536)
    launcher.need(args.out.absolute()==args.workspace.absolute().parent/'VERIFIED_PRODUCER.json','fixed verifier output')
    driver=launcher.load_checked('fresh_owned_verifier_driver',args.root/launcher.PRODUCER/'driver.py',
        contract['sources'][launcher.PRODUCER+'driver.py'])
    driver.launch_context(args.root,args.workspace,context['deadline_ns'],context['attempt_nonce'],context['ci'],args.context,args.context_sha256)
    with driver.bounded(context['deadline_ns']):
        # This replays the unchanged validator over all original exported arrays;
        # it does not generate another official/native forward or reuse an old PASS.
        value=driver.verify_handoff(args.root,args.workspace,args.manifest_sha256,decode_native=True)
        launcher.need(value['attempt_nonce']==context['attempt_nonce'] and
            launcher.encoded(value['ci'])==launcher.encoded(context['ci']),'verifier attempt identity')
        launcher.load_contract(args.root)
        launcher.need(launcher.sha(launcher.safe(args.context))==args.context_sha256,'verifier context drift')
        receipt=dict(schema=1,profile='qwen2-fresh-parent-native-verification-v1',status='PASS_ORIGINAL_M16_NATIVE_GATES',
            attempt_nonce=context['attempt_nonce'],ci=context['ci'],producer_manifest_sha256=args.manifest_sha256,
            parent_context_sha256=args.context_sha256,source_manifest_sha256=value['source_manifest_sha256'],
            runtime_identity_sha256=launcher.sha(launcher.encoded(value['runtime_identity'])),
            host_sha256=launcher.sha(launcher.encoded(value['host'])),native_exports=116,
            original_array_gate_revalidated=True,new_forward_executed=False,claims=launcher.CLAIMS)
        launcher.write_new(args.out,receipt)
        driver.remaining(context['deadline_ns'])
    return 0


if __name__=='__main__': raise SystemExit(main())
