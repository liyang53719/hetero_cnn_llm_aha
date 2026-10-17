"""Explicit M128 packed Public profile; linked numerical entry remains closed."""
from dataclasses import dataclass
import hashlib,inspect,json
from pathlib import Path
from ..attention_packed_owner.schedule import PackedSchedule
from ..attention_packed_owner import hooks
from ..attention_packed_public.mux import ScratchMux

@dataclass(frozen=True)
class PackedM128PublicProfile:
    compile_receipt: str
    receipt_sha256: str
    manifest: str
    manifest_sha256: str
    version: int = 2

    def install(self, owner, parent, job, owner_id):
        from ..official_bf16.owners import OfficialAttentionOwner
        from ..ffn_attention.matrix_service import MatrixService
        from ..dense_block_reduce.matrix_binding import ProfiledMatrixService
        from ..official_bf16.dense_silu import OfficialMatrixService
        from ..ffn_public import model as public
        from ..raw_kv_parent.model import ParentLoan
        if (type(self) is not PackedM128PublicProfile or type(self.version) is not int or self.version != 2 or
            type(owner) is not OfficialAttentionOwner or type(owner.matrix) is not ProfiledMatrixService or
            type(parent) is not ParentLoan or type(job) is not public.group.PrefixJob or
            type(job.m) is not int or job.m != 128 or job.kind != 'Attention' or
            not owner.ports()['job_ready'] or getattr(owner,'packed_schedule',None) is not None or
            parent.raw.blocked or not parent.raw.drained or any(parent.debts().values())):
            raise ValueError('exact idle original M128 Public packed profile required')
        from ..ffn_attention.attention_owner import AttentionOwner
        expected=((OfficialAttentionOwner,'0c87797587281b4e7f23663242e947ffe4157db9a644e788d67eb5c9045c50c1'),
                  (AttentionOwner,'ae5fcc65b0d238e8b3697d563ad5fc309ee17e72a078f39cfd841838c96bf929'),
                  (MatrixService,'d3cc6f8ddbe08617c1c476d3b15e2033031e3e42b121233baa9c1b5835250698'),
                  (OfficialMatrixService,'dfd44e15f274090ba7d1eca4fa6c59248e11029dad3c5fcfc0b45693c6267699'),
                  (ProfiledMatrixService,'33ea0786d537aa7de59b19ff55cb515f2afeaee780f4a9f1faeb42402da19593'))
        if any(hashlib.sha256(Path(inspect.getfile(cls)).read_bytes()).hexdigest()!=value for cls,value in expected):
            raise ValueError('exact reviewed owner/native profile sources required')
        from . import contract
        from . import admission
        contract.snapshot()
        manifest=admission.read_manifest(self.manifest,self.manifest_sha256,rows=128)
        if (type(self.compile_receipt) is not str or type(self.receipt_sha256) is not str or
            len(self.receipt_sha256)!=64 or any(c not in '0123456789abcdef' for c in self.receipt_sha256)):
            raise ValueError('strict combined compile receipt required')
        receipt=Path(self.compile_receipt)
        if receipt.is_symlink() or not receipt.is_file() or receipt.stat().st_size>262144:
            raise ValueError('combined compile receipt path/size')
        raw=receipt.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=self.receipt_sha256:
            raise ValueError('combined compile receipt identity')
        data=json.loads(raw)
        if type(data) is not dict or type(data.get('schema')) is not int or type(data.get('returncode')) is not int:
            raise ValueError('combined compile receipt canonical fields')
        data=admission.verify_library(self.compile_receipt,manifest=manifest)
        name=getattr(owner.matrix.lib,'_name',None)
        if type(name) is not str or Path(name).resolve()!=Path(data['library']).resolve():
            raise ValueError('one verified combined Matrix/SiLU ELF required')
        schedule=PackedSchedule()
        mux=ScratchMux(parent,owner_id=owner_id)
        hooks.install(owner,schedule)
        return schedule,mux

def authorize_full_numeric(*args,**kwargs):
    raise ValueError('full Public numeric admission is not implemented in this bounded profile')
