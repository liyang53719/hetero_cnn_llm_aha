from dataclasses import dataclass
@dataclass(frozen=True)
class Qwen2Budget:
    sequence:int=1024;layers:int=28;q_heads:int=12;head_dim:int=128;linear_mac_per_token_layer:int=46792704;hidden:int=1536;vocab:int=151936;macs_per_cycle:int=512;clock:int=1_000_000_000;tps:float=300
    @property
    def useful_macs(self):return self.linear_mac_per_token_layer*self.sequence*self.layers+self.layers*self.q_heads*(self.sequence*(self.sequence+1)//2)*self.head_dim*2+self.hidden*self.vocab
    @property
    def hard_cycles(self):return int(self.sequence*self.clock/self.tps)
    @property
    def wall_util(self):return self.useful_macs/(self.macs_per_cycle*self.hard_cycles)
