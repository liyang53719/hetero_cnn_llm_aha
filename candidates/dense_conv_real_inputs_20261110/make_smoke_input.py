"""Explicit deterministic synthetic user-boundary hidden states, never Dense results."""
from pathlib import Path
import argparse,numpy as np
p=argparse.ArgumentParser();p.add_argument('output',type=Path);a=p.parse_args()
if a.output.exists():raise ValueError('preserve existing input')
x=((np.arange(128*1024,dtype=np.int32)%31)-15).astype('<f4')/np.float32(32)
a.output.write_bytes((x.view('<u4')>>16).astype('<u2').tobytes())
