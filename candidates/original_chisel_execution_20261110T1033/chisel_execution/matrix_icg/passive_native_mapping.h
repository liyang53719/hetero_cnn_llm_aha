#ifndef PASSIVE_NATIVE_MAPPING_H
#define PASSIVE_NATIVE_MAPPING_H
// Test-observation only: called once after construction, before any vector row.
// Does not inspect or change DUT state, clocks, inputs, outputs, or native ABI.
#include <cerrno>
#include <cstring>
#include <cstdlib>
#include <string>
#include <stdexcept>
#include <fcntl.h>
#include <unistd.h>
#include <sys/stat.h>
extern char **environ;
namespace passive_native_mapping {
inline void need(bool ok,const char* text){if(!ok)throw std::runtime_error(text);}
inline std::string read_bounded(const char* path,size_t limit){
 const int fd=::open(path,O_RDONLY|O_CLOEXEC);need(fd>=0,"mapping source open");std::string data;char buf[4096];
 try{while(true){ssize_t n=::read(fd,buf,sizeof(buf));if(n<0&&errno==EINTR)continue;need(n>=0,"mapping source read");if(!n)break;need(data.size()+size_t(n)<=limit,"mapping source cap");data.append(buf,size_t(n));}need(::close(fd)==0,"mapping source close");}
 catch(...){::close(fd);throw;}return data;
}
inline void write_exclusive(const char* name,const std::string& data){
 const std::string path=std::string("native_mapping/")+name;const int fd=::open(path.c_str(),O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC,0600);need(fd>=0,"mapping evidence already exists or cannot open");
 try{size_t offset=0;while(offset<data.size()){ssize_t n=::write(fd,data.data()+offset,data.size()-offset);if(n<0&&errno==EINTR)continue;need(n>0,"mapping evidence write");offset+=size_t(n);}need(::fsync(fd)==0,"mapping evidence fsync");need(::close(fd)==0,"mapping evidence close");}
 catch(...){::close(fd);throw;}
}
inline void capture(const char* role){
 need(::mkdir("native_mapping",0700)==0,"fresh native mapping directory required");
 struct stat pre{};const int preload=::lstat("/etc/ld.so.preload",&pre);need(preload==-1&&errno==ENOENT,"system preload must be absent");
 for(char** p=environ;p&&*p;++p)need(std::strncmp(*p,"LD_",3)!=0&&std::strncmp(*p,"GLIBC_TUNABLES=",15)!=0,"unexpected loader environment");
 const std::string before=read_bounded("/proc/self/stat",65536);char target[4097];const ssize_t n=::readlink("/proc/self/exe",target,4096);need(n>0&&n<4096,"bounded self executable identity");
 const std::string maps=read_bounded("/proc/self/maps",1024*1024);const std::string after=read_bounded("/proc/self/stat",65536);
 write_exclusive("stat_before.txt",before);write_exclusive("exe.txt",std::string(target,size_t(n))+"\n");write_exclusive("maps.txt",maps);write_exclusive("stat_after.txt",after);
 write_exclusive("scope.txt",std::string("PASSIVE_SELF_MAPPING_AFTER_CONSTRUCTION_BEFORE_FIRST_VECTOR\nrole=")+role+"\npid="+std::to_string(::getpid())+"\nppid="+std::to_string(::getppid())+"\nLD_variables_absent=1\nsystem_preload_absent=1\nno_added_DUT_call=1\n");
 const int dir=::open("native_mapping",O_RDONLY|O_DIRECTORY|O_CLOEXEC);need(dir>=0,"mapping directory open");const int result=::fsync(dir);const int closed=::close(dir);need(result==0&&closed==0,"mapping directory fsync");
}
}
#endif
