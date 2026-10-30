"""Read-only CPython profile observer; no forward/topk replacement or arithmetic.

Only retain existing local/return object references at the original return event.
Serialization and dtype/shape checks happen after profiling is removed.
"""
import hashlib
import inspect
from pathlib import Path
import sys

OFFICIAL_SOURCE_SHA256='ea77a3979cb659dd04dc1f6a1cd7d3df53ddc5759e40eb0d5e98846e95b39d30'
OFFICIAL_CLASS='transformers.models.qwen3_5_moe.modeling_qwen3_5_moe.Qwen3_5MoeTopKRouter'

def require(ok, message):
    if not ok: raise ValueError(message)

class LocalReturnObserver:
    def __init__(self, instance, function):
        self.instance=instance;self.function=function;self.code=function.__code__
        self.events=[];self.callback=self._observe;self.active=False
    def _observe(self, frame, event, value):
        if event=='return' and frame.f_code is self.code and frame.f_locals.get('self') is self.instance:
            # No tensor calls, writes to f_locals, arithmetic or return substitution.
            self.events.append((frame.f_locals.get('router_probs'),value))
    def __enter__(self):
        require(sys.implementation.name=='cpython','CPython profile semantics required')
        require(not self.active and sys.getprofile() is None and sys.gettrace() is None,'existing instrumentation forbidden')
        require(not self.events,'observer must be fresh')
        self.active=True;sys.setprofile(self.callback);return self
    def __exit__(self, kind, value, traceback):
        intact=sys.getprofile() is self.callback
        sys.setprofile(None);self.active=False
        if not intact:
            if value is not None:
                value.add_note('profile observer changed during failed forward')
            else:
                require(False,'profile observer changed during forward')
        # Never suppress or rewrite the original forward exception.
        return False

class OfficialRouterObserver(LocalReturnObserver):
    def __init__(self, router):
        cls=type(router)
        require(cls.__module__+'.'+cls.__name__==OFFICIAL_CLASS,'exact original router class required')
        function=cls.forward
        self.source=Path(inspect.getsourcefile(function)).resolve()
        self.verify_source()
        require(router.forward.__func__ is function,'bound forward replaced')
        super().__init__(router,function)
    def verify_source(self):
        require(hashlib.sha256(self.source.read_bytes()).hexdigest()==OFFICIAL_SOURCE_SHA256,'official router source drift')
    def take(self, torch):
        require(not self.active,'serialize only after profiler removal')
        self.verify_source()
        require(type(self.instance).forward is self.function and self.instance.forward.__func__ is self.function and self.function.__code__ is self.code,'forward changed')
        require(len(self.events)==1,'one original full M128 router invocation required')
        probs,returned=self.events[0]
        require(isinstance(probs,torch.Tensor) and tuple(probs.shape)==(128,256) and probs.dtype is torch.float32 and probs.device.type=='cpu','exact original FP32 probabilities')
        require(isinstance(returned,tuple) and len(returned)==3,'normal original router return required')
        require(tuple(returned[0].shape)==(128,256) and returned[0].dtype is torch.bfloat16,'original BF16 logits')
        require(tuple(returned[1].shape)==(128,8) and returned[1].dtype is torch.bfloat16,'original BF16 weights')
        require(tuple(returned[2].shape)==(128,8) and returned[2].dtype is torch.int64,'original Torch expert IDs')
        require(bool(torch.isfinite(probs).all()) and bool(((probs>=0)&(probs<=1)).all()),'finite actual router probability range')
        return probs
