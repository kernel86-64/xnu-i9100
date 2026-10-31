#!/usr/bin/env python3
"""Compile actual stderr/write/writev and SIGABRT helpers with ASan/UBSan."""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parent.parent


def function(path, marker):
    source = (root/path).read_text()
    start = source.index(marker)
    brace = source.index('{', start)
    depth = 1
    pos = brace+1
    while depth:
        if source[pos] == '{':
            depth += 1
        elif source[pos] == '}':
            depth -= 1
        pos += 1
    return source[start:pos]


header = (root/'pexpert/arm/i9100_abort_observation.h').read_text()
helpers = '\n'.join([
    function('bsd/kern/sys_generic.c', 'static unsigned i9100_ui_stderr_note('),
    function('bsd/kern/sys_generic.c', 'int\nwrite_nocancel('),
    function('bsd/kern/sys_generic.c', 'int\nwr_uio('),
    function('bsd/kern/kern_sig.c', 'static void i9100_springboard_abort_note('),
])
code = r'''
#include <stdio.h>
#include <string.h>
#include <stdint.h>
#include <assert.h>
#define BOARD_CONFIG_EXYNOS4210_I9100 1
#define I9100_ABORT_IMPLEMENTATION 1
#define AUDIT_ARG(...) ((void)0)
#define SIGABRT 6
#define SIGPIPE 13
#define EBADF 9
#define EPIPE 32
#define EINTR 4
#define ERESTART 85
#define EWOULDBLOCK 35
#define FWRITE 2
#define DTYPE_SOCKET 2
#define FG_NOSIGPIPE 1
typedef uint64_t user_addr_t;
typedef uint64_t user_size_t;
typedef int64_t user_ssize_t;
struct proc {char p_comm[17];int p_pid;void *task;};
typedef struct proc *proc_t;
typedef struct {unsigned r[13],sp,lr,pc,cpsr;} arm_saved_state_t;
static struct proc process={"SpringBoard",17,(void*)0x1234};
static arm_saved_state_t state;
static unsigned irq=0,enabled=1,remote=0,copies=0,writes=0,fail_copy=0,write_error=0;
static proc_t current_proc(void){return remote ? NULL : &process;}
static void *current_thread(void){return (void*)1;}
static void *get_threadtask(void *t){assert(t==(void*)1);return remote ? NULL : process.task;}
static unsigned ml_at_interrupt_context(void){return irq;}
static unsigned ml_get_interrupts_enabled(void){return enabled;}
static void *find_user_regs(void *t){assert(t==(void*)1 && !irq);return &state;}
static unsigned char memory[65536];
static int copyin(user_addr_t a,void *out,size_t n){
 copies++;
 if(fail_copy || a<0x10000000 || a>0x10010000 || n>0x10010000-a)return 1;
 memcpy(out,memory+(a-0x10000000),n);return 0;
}
struct global_file {void *fg_cred;unsigned fg_lflags;};
struct fileproc {unsigned f_flag,f_type;struct global_file *f_fglob;void *f_cred;};
static struct global_file global_file;
static struct fileproc file={FWRITE,0,&global_file,NULL};
struct vfs_context {void *vc_ucred;};
static struct vfs_context context;
static struct vfs_context *vfs_context_current(void){return &context;}
struct write_nocancel_args {int fd;user_addr_t cbuf;user_size_t nbyte;};
static int fp_lookup(proc_t p,int fd,struct fileproc **out,int flags){*out=&file;return fd<0?EBADF:0;}
static void fp_drop_written(proc_t p,int fd,struct fileproc *fp){}
static void fp_drop(proc_t p,int fd,struct fileproc *fp,int flags){}
static int dofilewrite(struct vfs_context *c,struct fileproc *fp,user_addr_t a,
 user_size_t n,off_t offset,int flags,user_ssize_t *ret){writes++;if(!write_error)*ret=n;return write_error;}
struct mock_uio {user_addr_t base[12];user_size_t length[12];int count;long resid;};
typedef struct mock_uio *uio_t;
static int uio_iovcnt(uio_t u){return u->count;}
static int uio_getiov(uio_t u,int n,user_addr_t *a,user_size_t *size){*a=u->base[n];*size=u->length[n];return 0;}
static long uio_resid(uio_t u){return u->resid;}
static int fo_write(struct fileproc *fp,uio_t u,int flags,struct vfs_context *c){writes++;if(!write_error)u->resid=0;return write_error;}
static void psignal(proc_t p,int sig){assert(sig==SIGPIPE);}
'''+header+r'''
void ios7i9100_stderr_bytes(unsigned pid,unsigned task,const char *s,unsigned n){i9100_stderr_append(pid,task,s,n);}
void ios7i9100_abort_publish(const struct I9100AbortTrace *r){i9100_abort_store(r);}
'''+helpers+r'''
static void text(unsigned offset,const char *s){strcpy((char*)memory+offset,s);}
static void append(const char *s){while(*s){unsigned n=strlen(s);if(n>128)n=128;i9100_stderr_append(17,0x1234,s,n);s+=n;}}
int main(void){
 user_ssize_t ret=0;char line[64];
 text(0,"normal rendering log\n");
 struct write_nocancel_args args={2,0x10000000,strlen((char*)memory)};
 assert(!write_nocancel(&process,&args,&ret) && ret==args.nbyte && writes==1);
 unsigned before=copies;
 args.fd=1;assert(!write_nocancel(&process,&args,&ret) && copies==before);
 args.fd=2;file.f_flag=0;assert(write_nocancel(&process,&args,&ret)==EBADF && copies==before);file.f_flag=FWRITE;
 strcpy(process.p_comm,"SpringBoardHelper");assert(!write_nocancel(&process,&args,&ret) && copies==before);strcpy(process.p_comm,"SpringBoard");
 // Copy errors affect metadata alone; the original write result survives.
 fail_copy=1;assert(!write_nocancel(&process,&args,&ret));fail_copy=0;
 // Actual wr_uio keeps the user's iovec bases/lengths, fd and original write status.
 text(100,"*** Terminating app due to unca");text(200,"ught exception 'NSInvalidArgumentException', reason: test reason\n");
 struct mock_uio u={.base={0x10000064,0x100000c8},.length={strlen((char*)memory+100),strlen((char*)memory+200)},.count=2};u.resid=u.length[0]+u.length[1];
 assert(!wr_uio(&process,2,&u,&ret) && !u.resid && ret==(long)(u.length[0]+u.length[1]));
 assert(u.base[0]==0x10000064 && u.base[1]==0x100000c8 && u.length[0]==strlen((char*)memory+100));
 append("stack dump that would otherwise erase the reason\nlibc++abi.dylib: terminating\n");
 // Read only this task's eight bounded Thumb frame records before coredump.
 state.cpsr=0x30;state.pc=0x38001000;state.lr=0x38188fdd;state.sp=0x10001000;state.r[7]=0x10001000;
 unsigned frames[6]={0x10001008,0x374b7cd7,0x10001010,0x2d400001,0,0x123457};memcpy(memory+4096,frames,sizeof(frames));
 i9100_springboard_abort_note(&process,6);
 assert(i9100_abort_observation.sequence && i9100_abort_observation.trace.count==3 && !i9100_abort_observation.trace.error);
 assert(i9100_abort_observation.text_kind==1 && strstr((const char*)i9100_abort_observation.text,"reason: test reason"));
 assert(i9100_abort_line(0,17,6,line,sizeof(line)) && strstr(line,"PC38001000"));
 assert(!i9100_abort_line(0,18,6,line,sizeof(line)) && !i9100_abort_line(0,17,15,line,sizeof(line)));
 for(unsigned row=0;row<9;row++){struct{char a;char s[8];char b;}small={1,{0},2};assert(i9100_abort_line(row,17,6,small.s,sizeof(small.s)));assert(small.a==1&&small.b==2&&small.s[7]==0);}
 // No extra user reads in IRQ, masked context, remote task or wrong signal.
 before=copies;irq=1;i9100_springboard_abort_note(&process,6);irq=0;enabled=0;i9100_springboard_abort_note(&process,6);enabled=1;remote=1;i9100_springboard_abort_note(&process,6);remote=0;i9100_springboard_abort_note(&process,15);assert(copies==before);
 // Exact sbexit3 native sequence recovers saved descriptor/magic via guarded copyin.
 state.r[7]=0x10001020;
 unsigned native[8]={0x10001040,0x3875ffdd,0x10001060,0x3873fcaf,0x10001080,0x2feefb0b,0,0x2fee0d4f};
 for(unsigned n=0;n<4;n++)memcpy(memory+0x1020+n*32,native+n*2,8);
 unsigned saved[4]={0x10002000,0,0,0xdeafbe01},object=0x10003100,magic=0x12345678;
 memcpy(memory+0x1050,saved,16);memcpy(memory+0x2008,&object,4);memcpy(memory+0x3010,&magic,4);
 i9100_springboard_abort_note(&process,6);
 assert(i9100_abort_observation.trace.slab_status==1 && i9100_abort_observation.trace.slab==0x10003000);
 assert(i9100_abort_observation.trace.slab_expected==0xdeafbe01 && i9100_abort_observation.trace.slab_actual==0x12345678);
 assert(i9100_abort_line(10,17,6,line,sizeof(line)) && strstr(line,"actual12345678"));
 // sbexit4 uses a valid slide above the old arbitrary32MiB limit.
 unsigned base_frames[4]={0x38188fdd,0x38168caf,0x2f918b0b,0x2f909d4f};
 for(unsigned n=0;n<4;n++) { native[2*n+1]=base_frames[n]+0x229e000;memcpy(memory+0x1020+n*32,native+n*2,8); }
 i9100_springboard_abort_note(&process,6);assert(i9100_abort_observation.trace.slab_status==1);
 saved[0]=0xffff0000;memcpy(memory+0x1050,saved,16);i9100_springboard_abort_note(&process,6);assert(i9100_abort_observation.trace.slab_status==2);
 native[5]=0x123457;memcpy(memory+0x1060,native+4,8);i9100_springboard_abort_note(&process,6);assert(!i9100_abort_observation.trace.slab_status);
 // assertion2 slab_alloc uses a different native call chain and aligned frame.
 unsigned alloc_frames[4]={0x38188fdd,0x38168caf,0x2f8f84cd,0x2f8f8313};
 for(unsigned align=0;align<2;align++) {
  unsigned allocator_fp=0x10001300+8*align;
  for(unsigned n=0;n<4;n++) {
   unsigned pair[2]={n==2?allocator_fp:n==3?0:0x10001040+32*n,alloc_frames[n]+0x2d7a000};
   unsigned where=n==3?allocator_fp:0x10001020+32*n;
   memcpy(memory+(where-0x10000000),pair,8);
  }
  state.r[7]=0x10001020;
  unsigned local=((allocator_fp+8-48)&~15U)-112;
  unsigned slots[2]={0x10002004,0xdeafbe07},candidate=0x10003000;
  memcpy(memory+(local-0x10000000)+36,slots,8);memcpy(memory+0x2004,&candidate,4);
  i9100_springboard_abort_note(&process,6);
  assert(i9100_abort_observation.trace.slab_status==1 && i9100_abort_observation.trace.slab==candidate);
  assert(i9100_abort_observation.trace.slab_object==slots[0] && i9100_abort_observation.trace.slab_expected==slots[1]);
  assert(i9100_abort_observation.trace.slab_actual==0x12345678);
  candidate=0x10003004;memcpy(memory+0x2004,&candidate,4);unsigned shifted_magic=0xabcdef01;memcpy(memory+0x3014,&shifted_magic,4);
  i9100_springboard_abort_note(&process,6);assert(i9100_abort_observation.trace.slab_actual==shifted_magic && i9100_abort_observation.trace.slab==candidate);
  slots[1]=0xdeafbeff;memcpy(memory+(local-0x10000000)+36,slots,8);
  i9100_springboard_abort_note(&process,6);assert(i9100_abort_observation.trace.slab_status==2);
 }
 state.r[7]=0x10001000;
 // Cycles, invalid alignment, unmapped pages and user/kernel boundary stop safely.
 frames[0]=0x10001000;memcpy(memory+4096,frames,sizeof(frames));i9100_springboard_abort_note(&process,6);assert(i9100_abort_observation.trace.error==4);
 state.r[7]=0x10001001;i9100_springboard_abort_note(&process,6);assert(i9100_abort_observation.trace.error==1);
 state.r[7]=0x3ffffffc;state.sp=0x3ffff000;i9100_springboard_abort_note(&process,6);assert(i9100_abort_observation.trace.error==1);
 state.r[7]=state.sp=0x20000000;i9100_springboard_abort_note(&process,6);assert(i9100_abort_observation.trace.error==2);
 // Same PID with a different task cannot inherit an old stderr diagnostic.
 process.task=(void*)0x2234;append("still old identity\n");i9100_springboard_abort_note(&process,6);assert(!i9100_abort_observation.text_kind);
 i9100_stderr_append(17,0x2234,"new task plain text\n",20);i9100_springboard_abort_note(&process,6);assert(i9100_abort_observation.text_kind==2);
 for(unsigned i=0;i<30;i++)i9100_stderr_append(17,0x2234,"0123456789012345678901234567890123456789",40);
 i9100_abort_observation.sequence=0xffffffff;i9100_springboard_abort_note(&process,6);assert(i9100_abort_observation.sequence==1&&strlen((const char*)i9100_abort_observation.text)==240);
 puts("PASS: actual write/writev permission/UIO/result preservation, fragmented fatal-line retention, bounded stderr ring, own-task SIGABRT frame capture, bad-pointer/context exclusion both slab_dealloc and aligned slab_alloc snapshots and renderer; ASan/UBSan");
}
'''
with tempfile.TemporaryDirectory(prefix='i9100-abort-') as folder:
    folder = Path(folder)
    (folder/'test.c').write_text(code)
    subprocess.run(['clang', '-O1', '-fsanitize=address,undefined', '-fno-sanitize-recover=all', str(folder/'test.c'),
                    '-o', str(folder/'test')], check=True)
    subprocess.run([str(folder/'test')], check=True)
