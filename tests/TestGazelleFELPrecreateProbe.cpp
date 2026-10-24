// SPDX-License-Identifier: GPL-2.0-or-later
// Host-only test of the *production* read-only probe header. We replace
// libdovi with a fake ABI: this DOES NOT validate real Dolby RPU semantics.
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <iostream>
#include <vector>
#define HAVE_LIBDOVI 1
#include "../xbmc/utils/GazelleFELPrecreateProbe.h"

static int parses=0, rpuFrees=0, headerFrees=0;
struct DoviRpuOpaque { uint8_t marker; };
extern "C" {
DoviRpuOpaque* dovi_parse_unspec62_nalu(const uint8_t* b,size_t n) {
  ++parses;
  if (!b || n<3 || b[2]==0) return nullptr;
  return new DoviRpuOpaque{b[2]};
}
const DoviRpuDataHeader* dovi_rpu_get_header(const DoviRpuOpaque* p) {
  if (!p || p->marker==4) return nullptr;
  auto* out=new DoviRpuDataHeader{};
  out->guessed_profile=p->marker==3?8:7;
  out->el_type=p->marker==1?"FEL":p->marker==2?"MEL":"?";
  return out;
}
void dovi_rpu_free_header(const DoviRpuDataHeader* h) {
  ++headerFrees;
  delete h;
}
void dovi_rpu_free(DoviRpuOpaque* p) {
  if (p) {++rpuFrees;delete p;}
}
}
static std::vector<uint8_t> sample(uint8_t marker=1) {
  std::vector<uint8_t> v;
  const auto push=[&v](uint8_t type,uint8_t markerValue) {
    v.insert(v.end(),{0,0,0,3,static_cast<uint8_t>(type<<1u),1u,markerValue});
  };
  push(19,31);push(62,marker);push(63,32);
  return v;
}
static std::vector<uint8_t> hvcc() {
  auto v=std::vector<uint8_t>(23,0);
  v[0]=1;v[21]=3;
  return v;
}
int main() {
  using namespace GazelleFEL;
  const auto h=hvcc();
  for(uint8_t m=0;m<6;++m) {
    const auto v=sample(m);
    const int before=parses;
    const auto r=InspectFirstAU(v.data(),v.size(),h.data(),h.size(),false);
    assert(r.framingValid && r.bl && r.el && r.rpu);
    assert(parses==before+1);
    assert(r.type==(m==1?PrecreateRpuType::FEL:m==2?PrecreateRpuType::MEL:PrecreateRpuType::Unknown));
  }
  // Invalid profile and missing header still release parser allocations.
  assert(parses==6 && rpuFrees==5 && headerFrees==4);
  for(int n=0;n<10;++n) {
    auto v=sample();
    auto hv=h;
    bool protectedInput=false;
    switch(n) {
      case 0:v[3]=255;break;                       // overclaimed BL length
      case 1:v.pop_back();break;                    // truncated last NAL
      case 2:v[4]|=0x80u;break;                     // forbidden bit
      case 3:v[5]=0;break;                          // temporal id zero
      case 4:v.erase(v.begin()+7,v.begin()+14);break; // missing RPU
      case 5:v.resize(14);break;                    // no EL
      case 6:{auto rpu=std::vector<uint8_t>(v.begin()+7,v.begin()+14);v.insert(v.end(),rpu.begin(),rpu.end());break;}// duplicate RPU
      case 7:hv[21]=2;break;                        // reserved width
      case 8:protectedInput=true;break;
      case 9:hv[0]=0;break;
    }
    const int before=parses;
    const auto r=InspectFirstAU(v.data(),v.size(),hv.data(),hv.size(),protectedInput);
    assert(r.type==PrecreateRpuType::Unknown);
    assert(parses==before);
  }
  {
    auto v=sample();
    auto r=InspectFirstAU(v.data(),kMaxPrecreateAU+1,h.data(),h.size(),false);
    assert(r.type==PrecreateRpuType::Unknown);
  }

  // Annex B transport (3/4-byte mixed start codes) must also be recognized
  // WITHOUT hvcC. Parser allocation accounting remains real in this fake FFI.
  const auto asAnnexB=[](uint8_t marker) {
    const auto source=sample(marker);
    std::vector<uint8_t> output;
    std::size_t p=0;
    unsigned n=0;
    while(p<source.size()) {
      const std::size_t len=source[p+3];
      output.insert(output.end(),(n++%2)?std::initializer_list<uint8_t>{0,0,1}:
                                          std::initializer_list<uint8_t>{0,0,0,1});
      output.insert(output.end(),source.begin()+p+4,source.begin()+p+4+len);
      p+=4+len;
    }
    return output;
  };
  for(const uint8_t marker:{uint8_t{1},uint8_t{2}}) {
    const auto v=asAnnexB(marker);
    const int before=parses;
    const auto r=InspectFirstAU(v.data(),v.size(),nullptr,0,false);
    assert(r.framingValid && r.bl && r.el && r.rpu && parses==before+1);
    assert(r.type==(marker==1?PrecreateRpuType::FEL:PrecreateRpuType::MEL));
  }
  {
    auto v=asAnnexB(1);
    const int before=parses;
    assert(InspectFirstAU(v.data(),v.size(),nullptr,0,true).type==PrecreateRpuType::Unknown);
    assert(parses==before);
    // Leading-zero padding is ambiguous and must fail closed, not resync.
    v.insert(v.begin(),0);
    assert(InspectFirstAU(v.data(),v.size(),nullptr,0,false).type==PrecreateRpuType::Unknown);
    assert(parses==before);
  }
  {
    auto v=asAnnexB(1);
    const int before=parses;
    v.insert(v.end(),{0,0,1,0x7c,1,1}); // second, ambiguous RPU
    assert(InspectFirstAU(v.data(),v.size(),nullptr,0,false).type==PrecreateRpuType::Unknown);
    assert(parses==before);
  }
  {
    auto v=asAnnexB(1);
    const int before=parses;
    v.insert(v.end(),{0,0,0,1}); // empty trailing NAL
    assert(InspectFirstAU(v.data(),v.size(),nullptr,0,false).type==PrecreateRpuType::Unknown);
    assert(parses==before);
  }
  {
    auto v=asAnnexB(1);
    // Boundary on start-code immediately after a VCL NAL.
    v.resize(v.size()-7); // remove final EL including its start code
    const int before=parses;
    assert(InspectFirstAU(v.data(),v.size(),nullptr,0,false).type==PrecreateRpuType::Unknown);
    assert(parses==before);
  }
  {
    auto v=asAnnexB(1);
    const int before=parses;
    v[5]=0; // invalid BL temporal_id_plus1
    assert(InspectFirstAU(v.data(),v.size(),nullptr,0,false).type==PrecreateRpuType::Unknown);
    assert(parses==before);
  }
  std::cout<<"GAZELLE_FEL_PRECREATE_PROBE_HOST_PASS malformed=10 annexb_negative=5 "
             "fel_mel_unknown_separate=true rpu_free_once=true "
             "protected_stock=true libdovi=FAKE_ABI_NO_REAL_PARSE "
             "live_fel=false no_device=true\n";
}
