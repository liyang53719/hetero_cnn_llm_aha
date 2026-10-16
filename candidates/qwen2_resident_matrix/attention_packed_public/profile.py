"""Explicit M1/M2 Public transport profile; full numeric launch remains closed."""
from dataclasses import dataclass
import hashlib,inspect
from pathlib import Path
from ..attention_packed_owner.schedule import PackedSchedule
from ..attention_packed_owner import hooks
from .mux import ScratchMux

@dataclass(frozen=True)
class PackedPublicProfile:
    version: int = 1

    def install(self, owner, parent, job, owner_id):
        from ..official_bf16.owners import OfficialAttentionOwner
        from ..ffn_attention.matrix_service import MatrixService
        from ..dense_block_reduce.matrix_binding import ProfiledMatrixService
        from ..official_bf16.dense_silu import OfficialMatrixService
        from ..ffn_public.prefix_owners import Job
        from ..raw_kv_parent.model import ParentLoan
        if (type(self) is not PackedPublicProfile or type(self.version) is not int or self.version != 1 or
            type(owner) is not OfficialAttentionOwner or type(owner.matrix) is not ProfiledMatrixService or
            type(parent) is not ParentLoan or type(job) is not Job or
            type(job.m) is not int or job.m not in (1,2) or job.kind != 'Attention' or
            not owner.ports()['job_ready'] or getattr(owner,'packed_schedule',None) is not None or
            parent.raw.blocked or not parent.raw.drained or any(parent.debts().values())):
            raise ValueError('exact idle original M1/M2 Public packed profile required')
        from ..ffn_attention.attention_owner import AttentionOwner
        expected=((OfficialAttentionOwner,'0c87797587281b4e7f23663242e947ffe4157db9a644e788d67eb5c9045c50c1'),
                  (AttentionOwner,'ae5fcc65b0d238e8b3697d563ad5fc309ee17e72a078f39cfd841838c96bf929'),
                  (MatrixService,'d3cc6f8ddbe08617c1c476d3b15e2033031e3e42b121233baa9c1b5835250698'),
                  (OfficialMatrixService,'dfd44e15f274090ba7d1eca4fa6c59248e11029dad3c5fcfc0b45693c6267699'),
                  (ProfiledMatrixService,'33ea0786d537aa7de59b19ff55cb515f2afeaee780f4a9f1faeb42402da19593'))
        if any(hashlib.sha256(Path(inspect.getfile(cls)).read_bytes()).hexdigest()!=value for cls,value in expected):
            raise ValueError('exact reviewed owner/native profile sources required')
        name=getattr(owner.matrix.lib,'_name',None)
        if type(name) is not str:raise ValueError('qualified packed native library path required')
        library=Path(name)
        if not library.is_file() or hashlib.sha256(library.read_bytes()).hexdigest()!='1ba0b6aa738dd4a409b91adf93cafbcec63fc3c0df1590f9b91cf8f223f54811':
            raise ValueError('qualified packed native library required')
        schedule=PackedSchedule()
        mux=ScratchMux(parent,owner_id=owner_id)
        hooks.install(owner,schedule)
        return schedule,mux

def authorize_full_numeric(*args,**kwargs):
    raise ValueError('full Public numeric admission is not implemented in this bounded profile')
