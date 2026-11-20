#!/usr/bin/env bash
# Reproduce only the original Host *zero-edge* memory-map migration prototype.
# Usage: bash scripts/reproduce_hetero_m128_map_append_20261120.sh WORKSPACE [--execute]
# Needs the pinned 2026-11-20 local evidence and CPU2; no network operation.
# Missing inputs are a hard stop. No weight bytes, runtime data, or RTL are bundled.
set -euo pipefail
[[ $# -ge 1 && $# -le 2 && ( ${2:-} == "" || ${2:-} == --execute ) ]] || exit 2
root=$(cd -P -- "$1" && pwd)
cd -- "$root"
stage=round_20261120T1233/map_repro_$(date -u +%Y%m%dT%H%M%S)_$$
test -d round_20261120T1233/host
sha256sum --check --strict <<'PINS'
81eaaf3cebfb1ae71b43b2eb66226e750f72627d8c5f1f7f34d53f2a0690d0f4  round_20261120T1133/host/BUILD_RESULT.json
ff87895df9fd625db81dde432e273fd9aa12bab5c0d2a983b3cca04c93a256bd  round_20261120T1133/host/host_generation.hpp
2006465f2bb0a70c0c06ae0973a16acebaf401a89256e052617f0d746872dfd2  round_20261120T1133/host/host_restore_driver.cpp
d92c166d6a3efc03683235ce448e9b1b46da91484f0524346ef32cb4ca5677de  round_20261120T1133/host/reader_plan.hpp
bbcb0d7a42851f91315d8976a4f866df9754fef441f68361ba5cdaf7e96c50a7  round_20261120T1133/host/checkpoint_codec.hpp
0af55b0e58402a3cddd336275dc86e948c13393db7169141f22001a92a0fa89a  round_20261120T1133/map/check_append.py
PINS
mkdir -m 700 -- "$stage"
cp -t "$stage" round_20261120T1133/host/{host_generation.hpp,host_restore_driver.cpp,reader_plan.hpp,checkpoint_codec.hpp}
cat > "$stage/append_method.inc" <<'PINNED_SOURCE_EOF'
 // Prepared-boundary component migration only. Do not call on an unverified
 // descriptor or live active evaluator. The Host generation writer separately
 // binds the new map, new run identity, producer ancestry and all native state.
 static void append_after_restore(StrictMemory&m,const Profile&oldp,const Profile&future,
    const std::filesystem::path&workspace,const std::vector<SavedBus>&buses,uint64_t next,
    const std::string&oldhash,const std::string&newhash){
  identity_ok(oldhash);identity_ok(newhash);
  require(oldhash!=newhash&&memory_identity(m)==oldhash,"append old memory identity");
  const auto key=[](const Launch&l){return std::tie(l.version,l.profileId,l.epoch,l.commandBase,l.commandLimit,
      l.commands,l.descriptorBase,l.descriptorLimit,l.descriptors);};
  const auto region=[](const Region&r){return std::tie(r.base,r.limit,r.read,r.write);};
  const auto segment=[](const Segment&s){return std::tie(s.name,s.file,s.address,s.bytes,s.sha256,s.readonly);};
  require(next>0&&oldp.tokens==128&&future.tokens==128&&oldp.profile==future.profile&&oldp.profile<5&&
      oldp.launch.profileId==oldp.profile&&key(oldp.launch)==key(future.launch),"append launch identity");
  for(size_t k=0;k<m.regions.size();++k)
   require(region(m.regions[k])==region(oldp.launch.regions[k])&&
     region(m.regions[k])==region(future.launch.regions[k]),"append region change");
  const auto prefix=m.loaded.size();
  require(prefix==oldp.segments.size()&&future.segments.size()>prefix&&future.segments.size()<=256,"append strict prefix");
  for(size_t k=0;k<prefix;++k)
   require(segment(m.loaded[k].s)==segment(oldp.segments[k])&&
     segment(m.loaded[k].s)==segment(future.segments[k]),"append changes loaded prefix");
  require(!buses.empty()&&buses.size()<=16,"append buses");
  for(size_t k=0;k<buses.size();++k){
   const auto&slot=buses[k]; require(slot.bus&& &slot.bus->memory==&m&&slot.bus->offered&&
     slot.bus->consumed_cycle&&slot.bus->offered_cycle==next&&!slot.name.empty()&&slot.name.size()<=64,
     "append needs prepared boundary for every bus");
   for(size_t j=0;j<k;++j)
    require(buses[j].bus!=slot.bus&&buses[j].name!=slot.name,"append duplicate bus");
   validate(m,m.pages,*slot.bus,next);
  }
  Profile tail=future;tail.segments.erase(tail.segments.begin(),tail.segments.begin()+prefix);
  const auto intersects=[](const Segment&s,uint64_t a,uint64_t n){
    return a<=UINT64_MAX-n&&s.address<a+n&&a<s.address+s.bytes;
  };
  uint64_t total=0;
  for(size_t k=0;k<tail.segments.size();++k){
   const auto&s=tail.segments[k];
   require(s.bytes&&s.bytes<=max_bytes-total&&s.address<=UINT64_MAX-s.bytes&&
      (s.address|s.bytes)%64==0&&!s.name.empty(),"append segment extent");
   total+=s.bytes;
   for(auto&l:m.loaded)require(s.name!=l.s.name&&!intersects(s,l.s.address,l.s.bytes),"append overlaps loaded prefix");
   for(size_t j=0;j<k;++j) require(s.name!=tail.segments[j].name,"append duplicate role");
   for(auto &[pn,p]:m.pages) if(intersects(s,pn*4096,4096))
    for(unsigned i=0;i<4096;++i) require(!p.initialized[i]||!intersects(s,pn*4096+i,1),"append overlaps retired RAM");
   for(auto&slot:buses){
    const auto&b=*slot.bus;
    const auto no_touch=[&](const Address&a){
      AxiBus::validate(a);
      require(!intersects(s,a.addr,64*(a.len+1)),"append intersects existing transaction");
    };
    if(b.rd)no_touch(b.rd->req);
    if(b.stall_ar)no_touch(*b.stall_ar);
    if(b.aw)no_touch(*b.aw);
    if(b.stall_aw)no_touch(*b.stall_aw);
    if(b.pending)no_touch(b.pending->req);
   }
  }
  // Constructor checks readonly permissions, mutual interval disjointness,
  // exact lengths and full file hashes. Cannot insert any output pages.
  StrictMemory staged(tail,workspace);
  Out o;
  for(auto&r:m.regions){o.u(r.base);o.u(r.limit);o.u(r.read);o.u(r.write);}
  o.u(future.segments.size());
  for(auto&s:future.segments){o.str(s.name);o.str(s.file);o.u(s.address);o.u(s.bytes);o.str(s.sha256);o.u(s.readonly);}
  require(digest(o.v)==newhash,"append next memory identity");
  static_assert(std::is_nothrow_move_constructible_v<StrictMemory::Loaded>);
  m.loaded.reserve(future.segments.size());
  for(auto&l:staged.loaded)m.loaded.push_back(std::move(l));
 }
PINNED_SOURCE_EOF
cat > "$stage/test_append.cpp" <<'PINNED_SOURCE_EOF'
#include "checkpoint_codec.hpp"
#include <iostream>
#include <iterator>
using namespace live_transport;
namespace fs=std::filesystem;
struct Fixture {Profile oldp,future;const char* file;uint64_t cut;const char* caller;const char* before;const char* after;};
std::vector<Fixture> fixtures(){
#include "FIXTURE.inc"
}
std::vector<unsigned char> payload(const fs::path&p){
 std::ifstream f(p,std::ios::binary); std::vector<unsigned char>b((std::istreambuf_iterator<char>(f)),{});
 require(b.size()>=200,"missing checkpoint");size_t off=0;
 for(int i=0;i<3;i++){require(off+8<b.size(),"checkpoint header");size_t n=b[off];require(n+off+8<b.size(),"checkpoint field");off+=8+n;}
 return {b.begin()+off,b.end()-32};
}
template<class F>void rejected(F fn,std::string why){
 try{fn();}catch(const std::exception&e){require(std::string(e.what()).find(why)!=std::string::npos,e.what());return;}
 throw std::runtime_error("unexpected acceptance of "+why);
}
std::string config_hash(const Profile&p){
 std::vector<uint8_t>v;
 auto u=[&](uint64_t x){for(int i=0;i<8;i++)v.push_back(uint8_t(x>>(i*8)));};
 auto str=[&](const std::string&s){u(s.size());v.insert(v.end(),s.begin(),s.end());};
 for(auto&r:p.launch.regions){u(r.base);u(r.limit);u(r.read);u(r.write);}
 u(p.segments.size());for(auto&s:p.segments){str(s.name);str(s.file);u(s.address);u(s.bytes);str(s.sha256);u(s.readonly);}
 return digest(v);
}
void tiny_held(const fs::path&dir,const std::string&newcaller){
 std::string oldcaller(64,'c');
 std::vector<uint8_t>v(64,0x22);std::ofstream f(dir/"tiny.new",std::ios::binary);
 f.write(reinterpret_cast<const char*>(v.data()),v.size());f.close();require(f.good(),"tiny write");
 Profile p{0,128,{1,0,1,0,0,0,0,0,0,{{{0x1000,0x2000,true,false},{0x2000,0x3000,true,true},{0,0,false,false},{0,0,false,false}}}},{}};
 Profile q=p;q.segments.push_back({"tiny readonly","tiny.new",0x1080,64,digest(v),true});
 Address addr{0x2000,7,0,6,1};WriteBeat before{};before.strb=UINT64_MAX;before.last=true;before.data.fill(0x11111111);
 WriteBeat after=before;after.data.fill(0x45454545);
 StrictMemory old(p,dir);AxiBus oldbus(old);old.commit_b(addr,{before});
 auto s=oldbus.drive(0);oldbus.advance(s);
 s=oldbus.drive(1);s.ar_valid=s.aw_valid=s.w_valid=true;s.ar=s.aw=addr;s.w=after;oldbus.advance(s);
 s=oldbus.drive(2);require(s.r_valid&&s.b_valid&&s.r.data==before.data,"initial held R/B");
 s.b_ready=true;oldbus.advance(s);
 s=oldbus.drive(3);require(s.r_valid&&s.r.data==before.data&&old.read_beat(addr.addr)==after.data,"held R must differ from overwritten RAM");
 CheckpointCodec::save(dir/"tiny.old.bin",old,oldbus,oldcaller,3);
 StrictMemory m(p,dir);AxiBus b(m);CheckpointCodec::load(dir/"tiny.old.bin",m,b,oldcaller,3);
 CheckpointCodec::append_after_restore(m,p,q,dir,{{"bus0",&b}},3,config_hash(p),config_hash(q));
 CheckpointCodec::save(dir/"tiny.after.bin",m,b,newcaller,3);
 require(payload(dir/"tiny.old.bin")==payload(dir/"tiny.after.bin"),"tiny held transport changed");
 auto sample=b.prepared_offer(3);require(sample.r_valid&&sample.r.data==before.data&&m.read_beat(addr.addr)==after.data,"migration regenerated held R");
 sample.r_ready=true;b.advance(sample);b.retired();
 std::cout<<"PASS synthetic stale R after overlapping B (snapshot preserved), one real bus handshake after component migration\n";

 StrictMemory stalled(p,dir);AxiBus sb(stalled);auto t=sb.drive(0);t.ar_valid=true;t.ar=Address{0x1080,1,0,6,1};sb.advance(t);
 (void)sb.drive(1);
 rejected([&]{CheckpointCodec::append_after_restore(stalled,p,q,dir,{{"bus0",&sb}},1,config_hash(p),config_hash(q));},"intersects existing transaction");
 std::cout<<"PASS negative refuses overlapping stalled AR even in read-only range\n";
}
int main(int argc,char**argv){
 try{
 require(argc==3,"usage: test workspace evidence-dir");
 const fs::path root=argv[1],dir=argv[2]; const std::string newcaller(64,'f');
 tiny_held(dir,newcaller);
 for(const auto &x:fixtures()){
  const auto path=root/x.file;
  StrictMemory m(x.oldp,root);AxiBus b(m);rejected([&]{CheckpointCodec::append_after_restore(m,x.oldp,x.future,root,{{"bus0",&b}},x.cut,x.before,x.after);},"prepared boundary");
  CheckpointCodec::load(path,m,b,x.caller,x.cut);
  auto sid=std::to_string(x.oldp.profile); const auto prefix=b.ledger();
  auto apply=[&](const Profile&p,std::string after){CheckpointCodec::append_after_restore(m,x.oldp,p,root,{{"bus0",&b}},x.cut,x.before,after);};
  auto p=x.future;p.launch.epoch++;rejected([&]{apply(p,x.after);},"launch identity");
  p=x.future;p.segments[0].name+=".changed";rejected([&]{apply(p,x.after);},"loaded prefix");
  p=x.future;p.segments.back().address=x.oldp.segments.back().address;rejected([&]{apply(p,x.after);},"overlaps loaded prefix");
  p=x.future;p.segments.back().address=x.oldp.launch.regions[2].base;
  rejected([&]{apply(p,x.after);},"overlaps retired RAM");
  p=x.future;p.segments.back().sha256=std::string(64,'0');rejected([&]{apply(p,x.after);},"SHA mismatch");
  rejected([&]{apply(x.future,std::string(64,'0'));},"next memory identity");
  CheckpointCodec::save(dir/(sid+".before.bin"),m,b,x.caller,x.cut);
  require(payload(dir/(sid+".before.bin"))==payload(path),"rejected path mutated checkpoint payload");
  apply(x.future,x.after);
  CheckpointCodec::save(dir/(sid+".after.bin"),m,b,newcaller,x.cut);
  require(payload(dir/(sid+".after.bin"))==payload(path),"migration changed bus/debt/counters/offers/original RAM");
  require(b.ledger()==prefix,"ledger changed");
  const auto&newseg=x.future.segments.back();m.require_read(newseg.address,64);
  StrictMemory next(x.future,root);AxiBus nb(next);
  rejected([&]{CheckpointCodec::load(path,next,nb,x.caller,x.cut);},"input/region identity mismatch");
  CheckpointCodec::load(dir/(sid+".after.bin"),next,nb,newcaller,x.cut);
  require(nb.ledger()==prefix&&next.initialized_bytes()==m.initialized_bytes(),"post-append exact restore");
  std::cout<<"PASS component-only profile="<<sid<<" cycle="<<x.cut<<" added="<<(x.future.segments.size()-x.oldp.segments.size())<<" RAM="<<m.initialized_bytes()<<" original_R_prepared="<<b.prepared_offer(x.cut).r_valid<<" new_cfg="<<x.after<<'\n';
 }
 return 0;
 }catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}
}
PINNED_SOURCE_EOF
cat > "$stage/make_fixture.py" <<'PINNED_SOURCE_EOF'
"""Generate local-only test bindings; output no tensor contents."""
import json,sys
from pathlib import Path
top=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(top/'round_20261120T1133/map'))
import check_append as a
idx=a.load('round_20261120T1133/host/GENERATION_INDEX.json','88a82fea691adee3c76fed2576730c8ff29edb79717c441d7366dd929dd84bf0')
old,new=a.load(*a.OLD),a.load(*a.FUT)
def braces(x):return '{'+','.join(x)+'}'
def u(x):return str(x)+'ULL'
def q(x):return json.dumps(x)
def b(x):return str(x).lower()
def expr(p):
 l=p['launch']
 vals=[u(l[k]) for k in ('version','profileId','epoch','commandBase','commandLimit','commands','descriptorBase','descriptorLimit','descriptors')]
 vals.append(braces([braces([braces([u(g['base']),u(g['limit']),b(g['read']),b(g['write'])]) for g in l['regions']])]))
 seg=braces([braces([q(s['name']),q(s['file']),u(s['address']),u(s['bytes']),q(s['sha256']),b(s['readonly'])]) for s in p['segments']])
 return braces([str(p['profile']),str(p['tokens']),braces(vals),seg])
print('return {')
for p,x,y,m in zip(idx['profiles'],old['profiles'],new['profiles'],a.NAMES,strict=True):
 a.validate_profile(x,y,a.load(m,old['source_pins'][m]))
 c=p['latest_resume_candidate']
 lines=a.pin(c['path']+'/MANIFEST',c['outer_sha256']).read_text().splitlines()
 rec=[line.split() for line in lines[3:] if line.startswith('bus.bin ')]
 assert len(rec)==1
 path=c['path']+'/bus.bin'
 a.pin(path,rec[0][2],int(rec[0][1]))
 print(braces([expr(x),expr(y),q(path),u(c['cycle']),q(p['generation_identity']),q(a.memid(x)),q(a.memid(y))])+',')
print('};')
PINNED_SOURCE_EOF
cat > "$stage/build_migration.py" <<'PINNED_SOURCE_EOF'
import hashlib,json,os,resource,subprocess
from pathlib import Path
d=Path(__file__).resolve().parent
r=Path(__file__).resolve().parents[2]
old=r/'round_20261120T1133/host'
inputs=json.loads((old/'BUILD_RESULT.json').read_text())
args=inputs['command']
suffix='/round_20261120T1133/host/host_restore_driver.cpp'
historical_driver=next(x for x in args if x.endswith(suffix))
historical_root=historical_driver[:-len(suffix)]
if not historical_root.startswith('/') or historical_root=='/':
 raise RuntimeError('unexpected original build paths')
args=[x.replace(historical_root+'/',str(r)+'/') for x in args]
def h(p):return hashlib.file_digest(p.open('rb'),'sha256').hexdigest()
pins={'Host.o':(r/inputs['old_host_object']['path'],inputs['old_host_object']['sha256']),
      'callback':(r/'round_20261119T1633/native/verify_callback.cpp',inputs['callback_sha256'])}
for k,(p,expect) in pins.items():
 if h(p)!=expect: raise RuntimeError('build pin mismatch '+k)
out=d/'migration_driver'
if out.exists():raise RuntimeError('existing migration driver')
args=[{str(old/'DRIVER.d'):str(d/'MIGRATION.d'),str(old/'host_restore_driver.cpp'):str(d/'full_migration.cpp'),
       str(old/'host_restore_driver'):str(out)}.get(s,s) for s in args]
args.insert(args.index('-I'+str(old)),'-I'+str(d))
def limit():
 os.sched_setaffinity(0,{2});resource.setrlimit(resource.RLIMIT_AS,(768<<20,768<<20))
 resource.setrlimit(resource.RLIMIT_CPU,(60,60));resource.setrlimit(resource.RLIMIT_CORE,(0,0))
with (d/'BUILD_MIGRATION.log').open('x') as f:
 p=subprocess.run(args,cwd=r,stdout=f,stderr=subprocess.STDOUT,timeout=120,preexec_fn=limit)
rec={'args':args,'returncode':p.returncode,'exe_sha256':h(out) if p.returncode==0 else None,'recompiled_dut':False}
with (d/'BUILD_MIGRATION.json').open('x') as f:json.dump(rec,f,sort_keys=True,indent=2)
raise SystemExit(p.returncode)
PINNED_SOURCE_EOF
cat > "$stage/full_migration.cpp" <<'PINNED_SOURCE_EOF'
#define main frozen_main_for_link_only
#include "host_restore_driver.cpp"
#undef main
namespace fs=std::filesystem;
struct Fixture {Profile oldp,future;const char* file;uint64_t cut;const char* caller;const char* before;const char* after;};
std::vector<Fixture> fixtures(){
#include "FIXTURE.inc"
}
static constexpr char future_map[]="round_20261120T0733/launch_after/FIVE_LAUNCH_MAP_FUTURE.json";
static constexpr char future_map_sha[]="f10012b8a38907ed1fce2da1768568a62930f5d43fefdd530022ee3d4cb333bc";
int main(int argc,char**argv){
 try{
  require(argc==9,"full_migration mode current_exe_sha migration_run_sha PROFILE OLD_PLAN OLD_PLAN_SHA OUTPUT_DIR EXPECTED_MANIFEST_OR_DASH");
  const std::string mode=argv[1],exe=argv[2],runid=argv[3],profarg=argv[4];
  require((mode=="migrate"||mode=="verify")&&host_ck::rs::hex_sha(exe)&&host_ck::rs::hex_sha(runid),"invalid migration mode or identity");
  require(profarg.size()==1&&profarg[0]>='0'&&profarg[0]<='4',"profile");
  const auto num=static_cast<unsigned>(profarg[0]-'0');
  auto x=fixtures().at(num);
  const auto plan=reader_plan::load(argv[5],argv[6]);const auto&parent=plan.rows.at(num);
  const fs::path old=reader_plan::private_relative(parent.path),out=argv[7];
  require(runid!=plan.producer_run&&exe!=plan.producer_exe&&parent.cut==x.cut&&parent.identity==x.caller&&
    old.lexically_normal()==fs::absolute(fs::path(x.file).parent_path()).lexically_normal(),"foreign parent optional plan");
  const auto version=host_ck::identity(runid,num,exe);
  const auto identity=host_ck::hash_text(std::string("HETERO_HOST_MAP_APPEND_PROTOTYPE_1\n")+version+"\n"+future_map_sha+"\n"+
    parent.outer+"\n"+parent.ancestry+"\n"+x.before+"\n"+x.after+"\n");
  pinned(fs::canonical("/proc/self/exe"),exe.c_str(),32<<20);
  pinned(input_pins::Host_o_path,input_pins::Host_o_sha,16<<20);
  pinned(input_pins::map_path,input_pins::map_sha,16<<20);
  pinned(future_map,future_map_sha,16<<20);
  pinned(input_pins::layout_path,input_pins::layout_sha,16<<20);
  pinned(input_pins::arc_path,input_pins::arc_sha,64<<20);
  pinned(input_pins::matrix_path,input_pins::matrix_sha,16<<20);
  pinned(input_pins::icg_path,input_pins::icg_sha,16<<20);
  pinned(input_pins::idma_path,input_pins::idma_sha,16<<20);
  pinned(old/"ANCESTRY",parent.ancestry.c_str(),4096);
  actual_binding::Libs libs({input_pins::matrix_path,input_pins::icg_path,input_pins::idma_path});actual_binding::libs=&libs;
  const auto* matrix_pin=matrix_checkpoint_pin();
  require(matrix_pin&&std::strcmp(matrix_pin,"4bc589e976704f2874898a6ca9040f52c106efa4c9440979ba4c62d35e8fd540")==0,"original inner Matrix pin");
  const auto ancestry=std::string("HETERO_HOST_MAP_APPEND_PROTOTYPE_1\n")+plan.producer_run+" "+plan.producer_exe+" "+parent.outer+" "+parent.ancestry+"\n"+
    std::to_string(num)+" "+std::to_string(x.cut)+" "+std::to_string(x.cut*2)+" post-fall zero_edges\n"+runid+" "+exe+" "+identity+"\n"+input_pins::map_sha+
    " "+future_map_sha+" "+x.before+" "+x.after+"\n";
  const auto check_unchanged=[&](HostGeneration::Instance&a){
   auto &h=a.host;auto &n=*a.dispatch;
   const auto view=a.bus.prepared_offer(parent.cut);
   host_ck::Bytes sites;for(auto c:hetero_verify_site_calls)host_ck::put(sites,c);
   uint64_t local=0;for(unsigned i=0;i<8;i++)local+=n.edges(i)[0];
   require(a.stats.cycle==parent.cut&&a.bus.ledger().bs==parent.b&&a.memory.initialized_bytes()==parent.bytes&&
       a.account.completions==parent.completions&&h.get(actual_host::io_pc)==parent.pc&&
       !h.get(actual_host::reset)&&!h.get(actual_host::io_launch_valid)&&n.clock_level()==0&&!matrix_obs()[2]&&
       h.eval_calls==a.stats.evals&&hetero_verify_calls==a.stats.verifies&&
       digest(HostArcCheckpoint::encode(h))==parent.arc&&pin_digest(h,n,sample_bus(h,view))==parent.pins&&
       digest(sites)==parent.sites&&local==parent.local&&ram_digest(a.memory)==parent.ram,
       "actual old hardware/pin/PC/output state changed during append");
  };
  if(mode=="migrate"){
   require(std::string(argv[8])=="-","expected dash on migration");
   auto a=HostGeneration::restore(x.oldp,old,parent.outer,parent.identity,parent.cut);
   check_unchanged(*a);
   CheckpointCodec::append_after_restore(a->memory,x.oldp,x.future,fs::current_path(),{{"bus0",&a->bus}},parent.cut,x.before,x.after);
   check_unchanged(*a);
   const auto sha=HostGeneration::save(*a,out,identity,ancestry);
   check_unchanged(*a);
   printf("FULL_MIGRATION_ZERO_EDGE profile=%u cycle=%llu owners=17 manifest=%s identity=%s\n",num,(unsigned long long)parent.cut,sha.c_str(),identity.c_str());
  }else{
   pinned(out/"ANCESTRY",host_ck::hash_text(ancestry).c_str(),4096);
   auto a=HostGeneration::restore(x.future,out,argv[8],identity,parent.cut);
   check_unchanged(*a);
   printf("FULL_MIGRATION_FRESH_RESTORE profile=%u cycle=%llu owners=17 manifest=%s identity=%s\n",num,(unsigned long long)parent.cut,argv[8],identity.c_str());
  }
  return 0;
 }catch(const std::exception&e){fprintf(stderr,"FAIL %s\n",e.what());return 1;}
}
PINNED_SOURCE_EOF
cat > "$stage/run_migration.py" <<'PINNED_SOURCE_EOF'
"""Reopen each exact producer generation; separately reopen the new map state.
No model edge/launch. No workspace payload is copied to or from a remote.
"""
import hashlib,json,os,re,resource,struct,subprocess
from pathlib import Path
d=Path(__file__).resolve().parent
root=d.parents[1]
index=root/'round_20261120T1133/host/GENERATION_INDEX.json'
expect_index='88a82fea691adee3c76fed2576730c8ff29edb79717c441d7366dd929dd84bf0'
plan=d.parent/'host/RESTORE_PLAN'
expect_plan='c9d83d257c14e9c3047ab48f9596740f2f3ce466073bf933142574ef12dec81f'
def h(x):return hashlib.sha256(x).hexdigest()
def file(p):return h(p.read_bytes())
def require(x,m):
 if not x:raise RuntimeError(m)
pins=json.loads((d/'BUILD_MIGRATION.json').read_text())
exe=d/'migration_driver'; exe_sha=file(exe)
require(file(index)==expect_index and pins['returncode']==0 and exe_sha==pins['exe_sha256'],'untrusted plan/index/exe')
require(file(plan)==expect_plan,'canonical active plan pin')
indexdata=json.loads(index.read_text())
run=h(f'MAP_APPEND_ORIGINAL_FIVE_TEST_V1\n{exe_sha}\n{expect_plan}\n'.encode())
out=d/'full'
out.mkdir(mode=0o700)
def limit():
 resource.setrlimit(resource.RLIMIT_AS,(768<<20,768<<20))
 resource.setrlimit(resource.RLIMIT_CPU,(12,12))
 resource.setrlimit(resource.RLIMIT_CORE,(0,0))
def step(mode,num,q,sha):
 args=['taskset','-c','2',str(exe),mode,exe_sha,run,str(num),str(plan),expect_plan,str(q),sha]
 result=subprocess.run(args,cwd=root,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=40,preexec_fn=limit)
 with (out/f'{num}.{mode}.log').open('x') as f:f.write(result.stdout)
 require(result.returncode==0,f'{mode} profile {num}: {result.stdout[-600:]}')
 m=re.findall(r'owners=17 manifest=([0-9a-f]{64}) identity=([0-9a-f]{64})',result.stdout)
 require(len(m)==1,'missing mode attestation')
 return m[0]
def manifest(q,expected):
 p=q/'MANIFEST';require(file(p)==expected,'manifest trust')
 rows=p.read_text().splitlines()[3:];out={}
 for line in rows:
  n,b,s=line.split(); raw=(q/n).read_bytes();require(len(raw)==int(b) and h(raw)==s,f'bad member {n}')
  out[n]=raw
 require(len(out)==286,'exact expected component count')
 return out
def normalize(n,b):
 if n=='launch.bin':return b[:16]+b[80:-32]
 if n=='dispatch.bin':return b[:8]+b[72:-32]
 if n=='bus.bin':
  pos=0
  for _ in range(3):
   length=struct.unpack_from('<Q',b,pos)[0];pos+=8+length
  return b[pos:-32]
 return b
records=[]
for p in indexdata['profiles']:
 num=p['profile']; orig=p['latest_resume_candidate'];q=out/f'profile_{num}'
 sha,binding=step('migrate',num,q,'-')
 old=manifest(root/orig['path'],orig['outer_sha256'])
 new=manifest(q,sha)
 require(old.keys()==new.keys(),'changed schema')
 changed=[n for n in old if old[n]!=new[n]]
 require(set(changed)=={'bus.bin','launch.bin','dispatch.bin'},f'unexpected different owner file(s) {changed}')
 require(all(normalize(n,old[n])==normalize(n,new[n]) for n in changed),'nonidentity field differs')
 require(step('verify',num,q,sha)==(sha,binding),'fresh restore disagrees')
 records.append({'profile':num,'cycle':orig['cycle'],'old_manifest_sha256':orig['outer_sha256'],'new_manifest_sha256':sha,
 'new_identity':binding,'ancestry_sha256':file(q/'ANCESTRY'),'member_count':len(old),'raw_identical':len(old)-len(changed),
 'identity_and_seal_only_diff':changed,'fresh_process_verify':True,'edge_exec_count':0,
 'hardware_pc0_numeric_pass':False,'portable_primary_reader_acceptance':False})
o={'scope':'PASS FULL 17-OWNER SAME-EDGE MIGRATION PROTOTYPE NOT CAMPAIGN ACCEPTANCE','run_sha':run,'exe_sha':exe_sha,
 'source_baseline_index_sha':expect_index,'runtime_controller_source':file(d/'full_migration.cpp'),'records':records}
with (out/'RESULT.json').open('x') as f:json.dump(o,f,indent=2,sort_keys=True);f.write('\n')
print(file(out/'RESULT.json'))
PINNED_SOURCE_EOF
python - "$stage" <<'APPLY'
from pathlib import Path
import sys
d=Path(sys.argv[1]); p=d/'checkpoint_codec.hpp'; text=p.read_text()
anchor=' struct SavedBus {std::string name;const AxiBus* bus;};\n'
if text.count(anchor)!=1: raise RuntimeError('exact codec insertion anchor')
p.write_text(text.replace(anchor,anchor+(d/'append_method.inc').read_text()))
APPLY
PYTHONDONTWRITEBYTECODE=1 python "$stage/make_fixture.py" > "$stage/FIXTURE.inc"
printf 'Staged tested sources in %s (no Host evaluation)\n' "$stage"
if [[ ${2:-} == --execute ]]; then
 command -v taskset >/dev/null
 mkdir -m 700 "$stage/evidence"
 taskset -c 2 g++ -std=c++20 -O2 -DNDEBUG -I round_20261120T1133/host -I round_20261120T0433/bus_save "$stage/test_append.cpp" -o "$stage/test_append"
 taskset -c 2 "$stage/test_append" "$root" "$stage/evidence" | tee "$stage/TEST.log"
 python -B "$stage/build_migration.py"
 taskset -c 2 python -B "$stage/run_migration.py"
fi
