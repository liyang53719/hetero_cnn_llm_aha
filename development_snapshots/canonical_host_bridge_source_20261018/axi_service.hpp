// SOURCE-ONLY, UNCOMPILED. Five-channel RAM with B-retirement initialization.
#pragma once
#include "host_memory.hpp"
namespace canonical_host::n0_physical {
class N0PhysicalMemory;
template<class Proof> class AxiService {
    Proof& proof_;
    struct Read { Address req; unsigned beat=0; Data512 held{}; };
    struct PendingWrite { Address req; std::vector<WriteBeat> beats; WritePermit permit; };
    HostMemory& memory_;
    std::optional<Read> rd_;
    std::optional<Address> aw_;
    std::optional<WritePermit> aw_permit_;
    std::deque<WriteBeat> writes_;
    std::optional<PendingWrite> staged_;
    bool bvalid_=false;
    unsigned bid_=0;
    std::optional<Address> stalled_ar_,stalled_aw_;
    std::optional<WriteBeat> stalled_w_;
    std::optional<ReadBeat> stalled_r_;
    std::optional<WriteResponse> stalled_b_;
    IndependentLedger audit_;
    uint64_t metadata_requests_=0,metadata_returns_=0;
    static bool metadata(const Address& a) {
        const uint64_t n=64ULL*(a.len+1);
        for(unsigned i=0;i<2;++i)if(a.addr>=inputs[i].base && a.addr-inputs[i].base<=inputs[i].bytes
            && n<=inputs[i].bytes-(a.addr-inputs[i].base))return true;
        return false;
    }
    static void validate(const Address& a,const char* which) {
        require(a.id<256 && a.len<256,std::string(which)+" exact 8-bit ID/len");
        require(a.size==6 && a.burst==1 && a.addr%64==0,std::string(which)+" aligned 64B INCR only");
        require((a.addr&4095ULL)+64ULL*(a.len+1)<=4096,std::string(which)+" 4KiB boundary");
        require(a.addr<(1ULL<<56) && 64ULL*(a.len+1)<=(1ULL<<56)-a.addr,"physical address overflow");
    }
    void stage_complete_write() {
        if(!aw_ || writes_.size()<size_t(aw_->len)+1)return;
        require(!bvalid_ && !staged_,"overwriting held B");
        PendingWrite tx{*aw_,{},*aw_permit_};
        for(unsigned i=0;i<=aw_->len;++i) {
            auto w=writes_.front();writes_.pop_front();
            require(w.last==(i==aw_->len),"WLAST/AWLEN mismatch");
            require(w.strb!=0,"zero-strobe write not an output publication");
            tx.beats.push_back(w);
        }
        bid_=aw_->id;staged_=std::move(tx);bvalid_=true;aw_.reset();aw_permit_.reset();
        // No HostMemory mutation here. Held B does not initialize output bytes.
    }
    friend class N0PhysicalMemory;
    explicit AxiService(HostMemory& m,Proof& p):proof_(p),memory_(m){}
    const Ledger& ledger()const{return audit_.counts();}
    uint64_t metadata_requests()const{return metadata_requests_;}
    template<class Model> void drive(Model& d, uint64_t cycle) const {
        // Exact periodic ready schedules from the pinned Scala spec.
        d.io_axi_ar_ready = !rd_ && cycle % 7 != 0;
        d.io_axi_aw_ready = !aw_ && !bvalid_ && cycle % 5 != 0;
        d.io_axi_w_ready = writes_.size() < 256 && !bvalid_ && cycle % 3 != 0;
        d.io_axi_r_valid = bool(rd_);
        d.io_axi_r_bits_id = rd_ ? rd_->req.id : 0;
        d.io_axi_r_bits_resp = 0;
        d.io_axi_r_bits_last = rd_ && rd_->beat == rd_->req.len;
        for (unsigned i = 0; i < 16; ++i) d.io_axi_r_bits_data[i] = rd_ ? rd_->held[i] : 0;
        d.io_axi_b_valid = bvalid_; d.io_axi_b_bits_id = bid_; d.io_axi_b_bits_resp = 0;
    }
    template<class Model> static Sample sample(const Model& d) {
        Sample s;
        s.ar_valid = d.io_axi_ar_valid; s.ar_ready = d.io_axi_ar_ready;
        s.aw_valid = d.io_axi_aw_valid; s.aw_ready = d.io_axi_aw_ready;
        s.w_valid = d.io_axi_w_valid; s.w_ready = d.io_axi_w_ready;
        s.r_valid = d.io_axi_r_valid; s.r_ready = d.io_axi_r_ready;
        s.b_valid = d.io_axi_b_valid; s.b_ready = d.io_axi_b_ready;
        s.ar = {d.io_axi_ar_bits_addr, d.io_axi_ar_bits_id, d.io_axi_ar_bits_len,
                d.io_axi_ar_bits_size, d.io_axi_ar_bits_burst};
        s.aw = {d.io_axi_aw_bits_addr, d.io_axi_aw_bits_id, d.io_axi_aw_bits_len,
                d.io_axi_aw_bits_size, d.io_axi_aw_bits_burst};
        s.w.strb = d.io_axi_w_bits_strb; s.w.last = d.io_axi_w_bits_last;
        for (unsigned i = 0; i < 16; ++i) s.w.data[i] = d.io_axi_w_bits_data[i];
        s.r.id = d.io_axi_r_bits_id; s.r.resp = d.io_axi_r_bits_resp; s.r.last = d.io_axi_r_bits_last;
        for (unsigned i = 0; i < 16; ++i) s.r.data[i] = d.io_axi_r_bits_data[i];
        s.b.id = d.io_axi_b_bits_id; s.b.resp = d.io_axi_b_bits_resp;
        return s;
    }
    void check_offers(const Sample& s, bool terminal_seen) {
        if (stalled_ar_) require(s.ar_valid && s.ar == *stalled_ar_, "AR changed/dropped while stalled");
        if (stalled_aw_) require(s.aw_valid && s.aw == *stalled_aw_, "AW changed/dropped while stalled");
        if (stalled_w_) require(s.w_valid && s.w == *stalled_w_, "W changed/dropped while stalled");
        if (stalled_r_) require(s.r_valid && s.r == *stalled_r_, "R changed/dropped while stalled");
        if (stalled_b_) require(s.b_valid && s.b == *stalled_b_, "B changed/dropped while stalled");
        stalled_r_ = s.r_valid && !s.r_ready ? std::optional<ReadBeat>(s.r) : std::nullopt;
        stalled_b_ = s.b_valid && !s.b_ready ? std::optional<WriteResponse>(s.b) : std::nullopt;
        stalled_ar_ = s.ar_valid && !s.ar_ready ? std::optional<Address>(s.ar) : std::nullopt;
        stalled_aw_ = s.aw_valid && !s.aw_ready ? std::optional<Address>(s.aw) : std::nullopt;
        stalled_w_ = s.w_valid && !s.w_ready ? std::optional<WriteBeat>(s.w) : std::nullopt;
        if (terminal_seen) {
            require(!s.ar_valid && !s.aw_valid && !s.w_valid, "new AXI offer after first done");
            require(!s.arf() && !s.awf() && !s.wf() && !s.rf() && !s.bf(), "AXI fire after first done");
        }
        audit_.counts().ar_stall += s.ar_valid && !s.ar_ready;
        audit_.counts().aw_stall += s.aw_valid && !s.aw_ready;
        audit_.counts().w_stall += s.w_valid && !s.w_ready;
        audit_.counts().r_stall += s.r_valid && !s.r_ready;
        audit_.counts().b_stall += s.b_valid && !s.b_ready;
    }
    void advance(const Sample& s) {
        // Call after rising edge using the immutable pre-edge sample. Observer
        // methods must still refer to that pre-edge snapshot, not new state.
        audit_.consume(s);
        if(s.rf()) {
            require(bool(rd_),"R without AR debt");
            if(rd_->beat==rd_->req.len) {
                if(metadata(rd_->req))++metadata_returns_;
                rd_.reset();
            } else { ++rd_->beat;rd_->held=memory_.read_beat(rd_->req.addr+64ULL*rd_->beat); }
        }
        if(s.bf()) {
            require(bvalid_ && staged_.has_value() && s.b.resp==0,"B without staged successful write");
            proof_.begin_b(staged_->req,staged_->beats,staged_->permit,s);
            memory_.commit_b(staged_->req,staged_->beats,staged_->permit);
            proof_.end_b();
            staged_.reset();bvalid_=false;
        }
        if(s.arf()) {
            validate(s.ar,"AR");memory_.require_read(s.ar.addr,64ULL*(s.ar.len+1));
            require(!rd_,"AR debt overwrite");
            rd_=Read{s.ar,0,memory_.read_beat(s.ar.addr)};
            if(metadata(s.ar))++metadata_requests_; // Re-scans are intentionally permitted.
        }
        if(s.awf()) {
            validate(s.aw,"AW");require(!aw_ && !staged_,"AW debt overwrite");
            aw_permit_=memory_.require_write(s.aw.addr,64ULL*(s.aw.len+1));aw_=s.aw;
        }
        if(s.wf()) {require(writes_.size()<256,"W FIFO overflow");writes_.push_back(s.w);}
        stage_complete_write(); // AW/W independent; W-before-AW is supported.
    }
    void require_retired()const {
        audit_.require_retired();
        require(!rd_ && !aw_ && !aw_permit_ && writes_.empty() && !staged_ && !bvalid_,"AXI physical debt pending");
        require(metadata_requests_==metadata_returns_,"metadata response debt pending");
        // Never assert metadata_requests == 21 + 215: resident scanners re-read.
    }
};
} // namespace canonical_host
