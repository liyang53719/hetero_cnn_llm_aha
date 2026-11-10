#pragma once
#include <cstdint>
#include <fstream>
#include <iostream>
#include <iomanip>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>
inline void require_argc(int actual,int expected){if(actual!=expected)throw std::runtime_error("vector file argument required");}
inline std::vector<std::vector<uint32_t>> read_rows(const char* path,size_t count,size_t max_rows){
 std::ifstream f(path);if(!f)throw std::runtime_error("missing vectors");std::string line;
 std::vector<std::vector<uint32_t>> rows;
 while(std::getline(f,line)){
  if(line.size()>32768||rows.size()>=max_rows)throw std::runtime_error("bounded vectors");
  std::istringstream in(line);std::string token;std::vector<uint32_t> row;
  while(in>>token){if(token.size()>8||token.empty()||token.find_first_not_of("0123456789abcdefABCDEF")!=std::string::npos)throw std::runtime_error("hex word");row.push_back(uint32_t(std::stoul(token,nullptr,16)));}
  if(row.size()!=count)throw std::runtime_error("complete vector width");rows.push_back(row);
 }
 if(rows.empty())throw std::runtime_error("nonempty vectors");return rows;
}
inline void print_row(size_t row,uint32_t clock,const std::vector<uint32_t>& result,uint64_t rises,uint64_t falls){
 std::cout<<std::dec<<row<<" "<<clock;for(auto x:result)std::cout<<" "<<std::hex<<std::setfill('0')<<std::setw(8)<<x;
 std::cout<<" "<<std::dec<<rises<<" "<<falls<<"\n";
}
