"""TEMP: FP32 numpy RoPE coefficients, not a validated PyTorch platform capture.
Original runtime consumes cos[32],sin[32] BF16 per position. No DUT changes.
"""
from pathlib import Path
import numpy as np,json,hashlib,argparse
p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args()
inv=np.float32(1)/np.power(np.float32(10000000),np.arange(0,64,2,dtype='<f4')/np.float32(64))
angles=np.arange(128,dtype='<f4')[:,None]*inv[None,:]
cs=np.concatenate([np.cos(angles),np.sin(angles)],axis=1).astype('<f4')
u=cs.view('<u4');bf=((u+np.uint32(0x7fff)+((u>>16)&1))>>16).astype('<u2')
a.output.write_bytes(bf.tobytes());print(json.dumps({'status':'TEMP_NUMPY_TRIG_NOT_PLATFORM_VALIDATED','theta':10000000,'rotary_dim':64,'positions':[0,127],'sha256':hashlib.sha256(a.output.read_bytes()).hexdigest(),'numpy':np.__version__}))
