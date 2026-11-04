import resource,sys,runpy
resource.setrlimit(resource.RLIMIT_AS,(96<<20,96<<20));resource.setrlimit(resource.RLIMIT_CPU,(20,20));sys.dont_write_bytecode=True
from pathlib import Path
runpy.run_path(str(Path(__file__).resolve().parent/'tests/test_integration.py'),run_name='__main__')
