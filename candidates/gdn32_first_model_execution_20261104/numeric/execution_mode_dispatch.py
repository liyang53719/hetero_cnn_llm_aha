"""Explicit new same-job admission, unchanged old execution modes."""
import importlib.util,pathlib
P=pathlib.Path
p=P(__file__).resolve().parent/'samejob_gdn32_full.py'
s=importlib.util.spec_from_file_location('gdn32_full_dispatch',p);g=importlib.util.module_from_spec(s);s.loader.exec_module(g)
def admit(b):return g.admit(b)
def __getattr__(name):return getattr(g,name)
