#!/usr/bin/env bash
# Rebuild a NEW isolated runtime from official, SHA256-pinned wheels.
# Usage: bash rebuild_runtime.sh REPO_ROOT NEW_RUNTIME_NAME [PYTHON_3_12]
# Output: REPO_ROOT/work/NEW_RUNTIME_NAME. Never reuse a historical receipt.
set -euo pipefail
ROOT="$(cd "${1:?repository root required}" && pwd)"
NAME="${2:?fresh runtime directory name required}"
PYTHON="${3:-python3}"
[[ "$NAME" =~ ^[A-Za-z0-9_.-]+$ && "$NAME" != . && "$NAME" != .. ]] || exit 2
[[ -d "$ROOT/src/heteronpu" ]] || { echo 'Missing repository src/heteronpu' >&2; exit 2; }
RUNTIME="$ROOT/work/$NAME"
[[ ! -e "$RUNTIME" ]] || { echo 'Output must be a fresh directory' >&2; exit 2; }
PYTHON="$("$PYTHON" -c 'import sys; assert sys.version_info[:2]==(3,12); print(sys.executable)')"
mkdir -p "$RUNTIME/wheels"
cat > "$RUNTIME/requirements_actual.txt" <<'REQUIREMENTS'
Jinja2==3.1.6
MarkupSafe==3.0.3
PyYAML==6.0.3
Pygments==2.21.0
filelock==3.20.0
fsspec==2025.12.0
iniconfig==2.3.1
mpmath==1.3.0
networkx==3.6.1
numpy==2.3.5
packaging==26.3
pluggy==1.6.0
pytest==8.4.2
sympy==1.14.0
torch==2.10.0+cpu
typing_extensions==4.15.0
REQUIREMENTS
cat > "$RUNTIME/wheel_sha256.txt" <<'WHEEL_HASHES'
339b4732ffda5cd79b13f4e2711a31b0365ce445d95d243bb996273d072546a2  filelock-3.20.0-py3-none-any.whl
8bf1fe301b7d8acfa6e8571e3b1c3d158f909666642431cc78a1b7b4dbc5ec5b  fsspec-2025.12.0-py3-none-any.whl
9121e2c1fdb355232495be3194c8dfe87ccc2d5dee45947b78e68f499790d7a7  iniconfig-2.3.1-py3-none-any.whl
85ece4451f492d0c13c5dd7c13a64681a86afae63a5f347908daf103ce6d2f67  jinja2-3.1.6-py3-none-any.whl
d6dd0be5b5b189d31db7cda48b91d7e0a9795f31430b7f271219ab30f1d3ac9d  markupsafe-3.0.3-cp312-cp312-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl
a0b2b9fe80bbcd81a6647ff13108738cfb482d481d826cc0e02f5b35e5c88d2c  mpmath-1.3.0-py3-none-any.whl
d47fbf302e7d9cbbb9e2555a0d267983d2aa476bac30e90dfbe5669bd57f3762  networkx-3.6.1-py3-none-any.whl
0d8163f43acde9a73c2a33605353a4f1bc4798745a8b1d73183b28e5b435ae28  numpy-2.3.5-cp312-cp312-manylinux_2_27_x86_64.manylinux_2_28_x86_64.whl
d7193f7c8e4e93f444fde0262bf90af30e16fa0ad0ad44cb553c87339b23cd1c  packaging-26.3-py3-none-any.whl
e920276dd6813095e9377c0bc5566d94c932c33b27a3e3945d8389c374dd4746  pluggy-1.6.0-py3-none-any.whl
2363c69b61c4a97c838da3b130dcd6468f4848992b21a82f2a63ec34377137d9  pygments-2.21.0-py3-none-any.whl
872f880de3fc3a5bdc88a11b39c9710c3497a547cfa9320bc3c5e62fbf272e79  pytest-8.4.2-py3-none-any.whl
ba1cc08a7ccde2d2ec775841541641e4548226580ab850948cbfda66a1befcdc  pyyaml-6.0.3-cp312-cp312-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl
e091cc3e99d2141a0ba2847328f5479b05d94a6635cb96148ccb3f34671bd8f5  sympy-1.14.0-py3-none-any.whl
ee40b8a4b4b2cf0670c6fd4f35a7ef23871af956fecb238fbf5da15a72650b1d  torch-2.10.0+cpu-cp312-cp312-manylinux_2_28_x86_64.whl
f0fa19c6845758ab08074a0cfa8b7aecb71c999ca73d62883bc25cc018c4e548  typing_extensions-4.15.0-py3-none-any.whl
WHEEL_HASHES
"$PYTHON" -m pip download --no-deps --index-url https://download.pytorch.org/whl/cpu --dest "$RUNTIME/wheels" 'torch==2.10.0+cpu'
grep -vi '^torch==' "$RUNTIME/requirements_actual.txt" > "$RUNTIME/requirements_pypi.txt"
"$PYTHON" -m pip download --no-deps --index-url https://pypi.org/simple --dest "$RUNTIME/wheels" -r "$RUNTIME/requirements_pypi.txt"
(cd "$RUNTIME/wheels" && sha256sum -c ../wheel_sha256.txt)
"$PYTHON" -m pip install --no-index --no-deps --target "$RUNTIME/site-packages" "$RUNTIME"/wheels/*.whl
"$PYTHON" - "$RUNTIME" <<'WRAPPER_BUILDER'
import sys
from pathlib import Path
r=Path(sys.argv[1])
wrapper='#!/usr/bin/env bash\nset -euo pipefail\nRUNTIME="$(cd "$(dirname "$0")" && pwd)"\nROOT="$(cd "$RUNTIME/../.." && pwd)"\nexport PYTHONPATH="$RUNTIME/site-packages:$ROOT/src:$ROOT"\nexport PYTHONNOUSERSITE=1\nexport ATEN_CPU_CAPABILITY=default\nexport OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1\nCPU="$("/opt/codex/runtimes/codex-primary-runtime/dependencies/python/bin/python" -S -c \'import os; print(min(os.sched_getaffinity(0)))\')"\nexec taskset -c "$CPU" "/opt/codex/runtimes/codex-primary-runtime/dependencies/python/bin/python" -S "$@"\n'
# The wrapper stores the actual selected Python interpreter, never an old path.
old='/opt/codex/runtimes/codex-primary-runtime/dependencies/python/bin/python'
wrapper=wrapper.replace(old,sys.executable)
(r/'python.sh').write_text(wrapper)
(r/'python.sh').chmod(0o755)
WRAPPER_BUILDER
cat > "$RUNTIME/verify_runtime.py" <<'VERIFY_RUNTIME'
import os,sys,json,hashlib,datetime,importlib.metadata
from pathlib import Path
import torch,numpy as np,yaml,pytest,heteronpu
R=Path(__file__).resolve().parent
def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
torch.set_num_threads(1);torch.set_num_interop_threads(1)
checks={'heteronpu_import':any(Path(p).resolve()==R.parent.parent/'src/heteronpu' for p in heteronpu.__path__),'torch_version':torch.__version__=='2.10.0+cpu','torch_commit':torch.version.git_version=='449b1768410104d3ed79d3bcfe4ba1d65c7f22c0','numpy_version':np.__version__=='2.3.5','yaml_version':yaml.__version__=='6.0.3','pytest_version':pytest.__version__=='8.4.2','default_dispatch':torch.backends.cpu.get_cpu_capability()=='DEFAULT' and os.getenv('ATEN_CPU_CAPABILITY')=='default','one_cpu':len(os.sched_getaffinity(0))==1,'torch_threads_one':torch.get_num_threads()==torch.get_num_interop_threads()==1,'isolated_modules':all(Path(m.__file__).resolve().is_relative_to(R/'site-packages') for m in [torch,np,yaml,pytest]),'bf16_import_smoke':torch.tensor([1.,2.],dtype=torch.bfloat16).float().tolist()==[1.,2.]}
paths=['python.sh','site-packages/torch/lib/libtorch_cpu.so','site-packages/torch/_C.cpython-312-x86_64-linux-gnu.so','site-packages/numpy/_core/_multiarray_umath.cpython-312-x86_64-linux-gnu.so']
receipt={'status':'PASS_ISOLATED_PINNED_RUNTIME_READY' if all(checks.values()) else 'FAIL_RUNTIME','checks':checks,'created_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'runtime_root':str(R),'python':sys.version,'python_executable':sys.executable,'torch':torch.__version__,'torch_commit':torch.version.git_version,'numpy':np.__version__,'cpu_capability':torch.backends.cpu.get_cpu_capability(),'affinity':sorted(os.sched_getaffinity(0)),'sha256':{p:sha(R/p) for p in paths},'wheels':{p.name:sha(p) for p in sorted((R/'wheels').glob('*.whl'))},'installed_packages':{d.metadata['Name']:d.version for d in importlib.metadata.distributions(path=[str(R/'site-packages')])},'official_sources':['https://download.pytorch.org/whl/cpu','https://pypi.org/simple'],'scope':'Fresh runtime import/version/binary/one-CPU/BF16 smoke verification only; no model pass inherited or claimed. Old wrapper/receipt bytes unavailable.','complete_dependency_source_closure':False}
(R/'runtime_receipt.json').write_text(json.dumps(receipt,indent=2,sort_keys=True)+'\n')
print(json.dumps({'status':receipt['status'],'checks':checks,'sha256':dict(receipt['sha256'],**{'runtime_receipt.json':sha(R/'runtime_receipt.json')})},indent=2))
if not all(checks.values()):raise SystemExit(1)
VERIFY_RUNTIME
"$RUNTIME/python.sh" "$RUNTIME/verify_runtime.py" | tee "$RUNTIME/verify.log"
echo 'Fresh receipt generated. Review and explicitly pin its new SHA; no model PASS is implied.'
