#include "unseeded_matrix_v2.h"
#include <cstring>
#include <iostream>
int main(){
 if(retained_matrix_unseeded_v2_abi_version()!=131072)return 1;
 if(std::strcmp(retained_matrix_unseeded_v2_contract_sha256(),RETAINED_MATRIX_CONTRACT_SHA256))return 2;
 uint32_t w[63]={};
 if(retained_matrix_unseeded_v2_seed_request(nullptr,w,63)!=-7)return 3;
 if(retained_matrix_unseeded_v2_seed_request(nullptr,nullptr,0)!=-7)return 4;
 if(retained_matrix_unseeded_v2_drive(nullptr,w,63)!=-1)return 5;
 if(retained_matrix_unseeded_v2_read(nullptr,w,63)!=-1)return 6;
 std::cout<<"PASS ABI identity and seed/null rejection only; no model instantiated\n";
}
