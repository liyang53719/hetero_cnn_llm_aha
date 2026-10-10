"""No EDA: prove the acceptance-only skip is narrow and fail closed."""
import hashlib
from pathlib import Path
import subprocess
import sys

import pytest

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'.github/scripts'))
import attention_readonly_ci_scope as scope


class Repository:
    def __init__(self,path):
        self.path=path
        self.git('init','-q')
        self.git('config','user.name','Scope tests')
        self.git('config','user.email','scope@example.invalid')
    def git(self,*args):
        return subprocess.check_output(['git','-C',str(self.path),*args],stderr=subprocess.PIPE).decode().strip()
    def write(self,path,text):
        p=self.path/path;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text)
    def commit(self):
        self.git('add','--all');self.git('commit','-qm','scope fixture');return self.git('rev-parse','HEAD')


@pytest.fixture
def repo(tmp_path): return Repository(tmp_path)


ORIGINAL='''name: test
on: [push]
jobs:
  build:
    runs-on: ubuntu-24.04
    timeout-minutes: 120
    steps:
      - run: python real_build.py
  pass:
    needs: build
    steps:
      - run: python numerical_pair.py --mode pass
  fault:
    needs: build
    steps:
      - run: python numerical_pair.py --mode fault
  acceptance:
    needs: [build, pass, fault]
    if: always()
    steps:
      - run: python acceptance.py
'''


def wiring(text):
    return text.replace('\njobs:\n','\njobs:\n'+scope.SCOPE_JOB_BLOCK).replace(
        '  build:\n','  build:\n'+scope.BUILD_GUARD).replace('    if: always()\n',scope.ACCEPTANCE_IF)


@pytest.mark.parametrize('path',sorted(scope.ALLOWED))
def test_exact_readonly_paths(repo,path):
    repo.write(path,'old\n');a=repo.commit();repo.write(path,'new\n');b=repo.commit()
    assert scope.classify(repo.path,a,b)['run_full'] is False


def test_production_wiring_only_preserves_every_other_byte(repo):
    repo.write(scope.WORKFLOW,ORIGINAL);a=repo.commit()
    repo.write(scope.WORKFLOW,wiring(ORIGINAL));b=repo.commit()
    assert scope.normalize_workflow(wiring(ORIGINAL).encode())==ORIGINAL.encode()
    assert scope.classify(repo.path,a,b)['run_full'] is False


@pytest.mark.parametrize('change',[
    lambda s:s.replace('120','121'),
    lambda s:s.replace('--mode fault','--mode pass'),
    lambda s:s.replace('python real_build.py','true'),
    lambda s:s.replace("!= 'false'","== 'true'"),
    lambda s:s.replace('timeout-minutes: 5','timeout-minutes: 50'),
    lambda s:s.replace('runs-on: ubuntu-24.04','runs-on: arbitrary'),
])
def test_any_real_job_or_nonliteral_guard_change_runs_full(repo,change):
    repo.write(scope.WORKFLOW,ORIGINAL);a=repo.commit()
    repo.write(scope.WORKFLOW,change(wiring(ORIGINAL)));b=repo.commit()
    assert scope.classify(repo.path,a,b)['run_full'] is True


@pytest.mark.parametrize('path',[
    'chisel/continuous_prefill/src/main/scala/HostBlockTop.scala',
    'chisel/continuous_prefill/tests/host_bf16_attention_block.cpp',
    'chisel/continuous_prefill/scripts/host_bf16_attention_block_reference.py',
    'chisel/continuous_prefill/scripts/host_bf16_attention_block_fixture.py',
    'rtl/matrix/engine.sv','src/heteronpu/command.py','scripts/verify_attention_native_m1.py',
    'config/upstream/qwen3_5_0p8b/layer3_bf16_contract.json','unknown.txt',
])
def test_unknown_and_numerical_sources_run_full(repo,path):
    repo.write('anchor','unchanged');a=repo.commit();repo.write(path,'changed');b=repo.commit()
    assert scope.classify(repo.path,a,b)['run_full'] is True


def test_unavailable_base_empty_diff_and_deletion_run_full(repo):
    path=next(iter(scope.ALLOWED));repo.write(path,'old');a=repo.commit()
    assert scope.classify(repo.path,'',a)['run_full'] is True
    assert scope.classify(repo.path,'0'*40,a)['run_full'] is True
    assert scope.classify(repo.path,'a'*40,a)['run_full'] is True
    assert scope.classify(repo.path,a,a)['run_full'] is True
    (repo.path/path).unlink();b=repo.commit()
    assert scope.classify(repo.path,a,b)['run_full'] is True


def test_actual_production_body_is_byte_identical_to_published_body():
    # Immutable pre-guard workflow at 5ff4ca; no historical checkout is needed.
    assert hashlib.sha256(scope.normalize_workflow((ROOT/scope.WORKFLOW).read_bytes())).hexdigest() == 'b2afd1c990a9006274bd7bb0e30fb6b88c581ad912c2dd4f56e7940584e8888f'
