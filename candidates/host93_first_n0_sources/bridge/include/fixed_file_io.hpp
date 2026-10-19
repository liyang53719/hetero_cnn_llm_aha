#pragma once
#include <array>
#include <cerrno>
#include <cstdint>
#include <fcntl.h>
#include <istream>
#include <stdexcept>
#include <streambuf>
#include <string>
#include <sys/stat.h>
#include <unistd.h>
namespace canonical_runtime_v1::first_n0 {
struct ResourceIncomplete:std::runtime_error {using std::runtime_error::runtime_error;};
inline void io_failure(const char* why) {
    if(errno==ENOMEM||errno==EMFILE||errno==ENFILE||errno==ENOSPC||errno==EDQUOT||errno==EFBIG)
        throw ResourceIncomplete(why);
    throw std::runtime_error(why);
}
class Fd final {
    int fd_;
public:
    explicit Fd(int fd):fd_(fd){if(fd<0)io_failure("fixed file open");}
    ~Fd(){::close(fd_);}
    Fd(const Fd&)=delete;Fd& operator=(const Fd&)=delete;
    int get()const noexcept{return fd_;}
};
inline int open_dir(const char* path) {return ::open(path,O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);}
class FixedInputBuffer final:public std::streambuf {
    Fd fd_;std::array<char,65536> chunk_{};
protected:
    int_type underflow()override {
        if(gptr()<egptr())return traits_type::to_int_type(*gptr());
        ssize_t n;do {n=::read(fd_.get(),chunk_.data(),chunk_.size());}while(n<0&&errno==EINTR);
        if(n<0)io_failure("fixed file read");
        if(n==0)return traits_type::eof();
        setg(chunk_.data(),chunk_.data(),chunk_.data()+n);return traits_type::to_int_type(*gptr());
    }
public:
    FixedInputBuffer(int dir,const char* name,std::uint64_t bytes)
      :fd_(::openat(dir,name,O_RDONLY|O_NOFOLLOW|O_NONBLOCK|O_CLOEXEC)) {
        struct stat st{};
        if(::fstat(fd_.get(),&st)!=0||!S_ISREG(st.st_mode)||st.st_size<0||std::uint64_t(st.st_size)!=bytes)
            throw std::runtime_error("fixed regular input size");
        setg(chunk_.data(),chunk_.data(),chunk_.data());
    }
};
inline bool exclusive_write(int dir,const char* name,const void* bytes,std::size_t size)noexcept {
    const int fd=::openat(dir,name,O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC,0600);
    if(fd<0)return false;
    std::size_t offset=0;const auto* data=static_cast<const char*>(bytes);
    while(offset<size) {
        const auto n=::write(fd,data+offset,size-offset);
        if(n<0&&errno==EINTR)continue;
        if(n<=0){::close(fd);return false;}offset+=static_cast<std::size_t>(n);
    }
    return ::close(fd)==0;
}
}
