#!/usr/bin/env python3
"""Exercise actual UI exit/signal observers, publishers and retained text."""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parent.parent
source = (root/'bsd/kern/kern_exit.c').read_text()
start = source.index('static void i9100_springboard_exit_note(')
helper = source[start:source.index('\n#endif', start)]
sigsource = (root/'bsd/kern/kern_sig.c').read_text()
start = sigsource.index('static void i9100_springboard_signal_note(')
signal_helper = sigsource[start:sigsource.index('\n#endif', start)]
board = (root/'pexpert/arm/pe_exynos4210_i9100.c').read_text()
start = board.index('void ios7i9100_signal_request(')
publishers = board[start:board.index('\nstatic void i9100_perf_text', start)]
# Model only the two raw CPSR instructions; compile the actual C bodies.
save = '__asm__ volatile("mrs %0,cpsr\\n\\tcpsid if" : "=r"(mask) :: "memory");'
restore = '__asm__ volatile("msr cpsr_c,%0" :: "r"(mask) : "memory");'
assert publishers.count(save) == publishers.count(restore) == 2
publishers = publishers.replace(save, 'mask=test_mask; test_mask |= 0xc0;')
publishers = publishers.replace(restore, 'test_mask=mask;')
header = (root/'pexpert/arm/i9100_process_observation.h').read_text()
code = r'''
#include <stdio.h>
#include <string.h>
#include <stdint.h>
#include <assert.h>
/* Darwin wait encoding, independent of the host's signal number table. */
#define WIFSIGNALED(s) (((s)&0x7f)!=0 && ((s)&0x7f)!=0x7f)
#define WIFEXITED(s) (((s)&0x7f)==0)
#define WTERMSIG(s) ((s)&0x7f)
#define WEXITSTATUS(s) (((s)>>8)&0xff)
#define PROC_NULL NULL
#define TASK_NULL NULL
#define P_LEXIT 1
#define P_REBOOT 2
#define SIGTERM 15
#define SIGKILL 9
#define SIGABRT 6
struct proc {char p_comm[17];int p_pid;void *task;unsigned p_lflag,p_flag;};
typedef struct proc *proc_t;
typedef void *task_t;
typedef struct {unsigned pc,lr,cpsr;} arm_saved_state_t;
struct thread {struct {arm_saved_state_t *uss;} machine;};
typedef struct thread *thread_t;
struct uthread {unsigned uu_exception,uu_code,uu_subcode;};
static void *get_threadtask(thread_t thread){return thread;}
static unsigned vm_page_free_count=12345;
static unsigned test_mask, irq;
static struct thread running;
static proc_t context;
static task_t context_task;
static unsigned ml_at_interrupt_context(void){return irq;}
static task_t current_task(void){assert(!irq);return context_task;}
static proc_t get_bsdtask_info(task_t task){assert(!irq && task==context_task);return context;}
static int is_kerneltask(task_t task){return task==(void*)0x9999;}
static thread_t current_thread(void){assert(!irq);return &running;}
static void *find_user_regs(thread_t thread){assert(!irq && thread==&running);return thread->machine.uss;}
'''+header+r'''
volatile struct I9100ProcessExit i9100_process_exit;
volatile struct I9100ProcessExit i9100_backboard_exit;
volatile struct I9100SignalRequest i9100_signal_pending[3], i9100_signal_exit;
'''+publishers+helper+signal_helper+r'''
int main(void){
 char a[64],b[64];
 assert(!i9100_process_text(a,b,sizeof(a)));
 struct proc p={"Preferences",73,(void*)1};
 struct uthread ut={1,2,0x12345678};
 i9100_springboard_exit_note(&p,11,(void*)1,&ut);
 assert(!i9100_process_exit.sequence);
 strcpy(p.p_comm,"SpringBoardHelper");
 i9100_springboard_exit_note(&p,11,(void*)1,&ut);
 assert(!i9100_process_exit.sequence);
 strcpy(p.p_comm,"SpringBoard");
 i9100_springboard_exit_note(&p,11|0x80,(void*)1,&ut);
 assert(i9100_process_exit.sequence==1 && i9100_process_exit.signal==11);
 assert(i9100_process_exit.exception_known==1 && i9100_process_exit.subcode==0x12345678);
 assert(i9100_process_text(a,b,sizeof(a)) && strstr(a,"SIG11 EXIT0 X1") && strstr(b,"SUB12345678"));
 assert(i9100_signal_text(a,b,sizeof(a)) && strstr(a,"unavailable") && !b[0]);
 // Remote SIGKILL must not even dereference the external uthread pointer.
 i9100_springboard_exit_note(&p,9,(void*)2,(struct uthread*)(uintptr_t)1);
 assert(i9100_process_exit.sequence==2 && i9100_process_exit.signal==9);
 assert(!i9100_process_exit.exception_known && !i9100_process_exit.exception && !i9100_process_exit.code && !i9100_process_exit.subcode);
 assert(i9100_process_text(a,b,sizeof(a)) && strstr(a,"SIG9 EXIT0 X0") && strstr(b,"FREE12345"));
 i9100_springboard_exit_note(&p,7<<8,(void*)1,&ut);
 assert(i9100_process_exit.signal==0 && i9100_process_exit.exit_code==7);
 i9100_process_exit.sequence=0xffffffff;
 i9100_springboard_exit_note(&p,0,(void*)1,&ut);
 assert(i9100_process_exit.sequence==1);
 struct {char before;char a[8];char after;} small={0x55,{0},0x66};
 i9100_process_text(small.a,b,sizeof(small.a));
 assert(small.before==0x55 && small.after==0x66 && small.a[7]==0);
 // The other UI service gets independent status, without erasing SpringBoard.
 strcpy(p.p_comm,"backboardd");
 i9100_springboard_exit_note(&p,11,(void*)1,&ut);
 assert(i9100_backboard_exit.sequence==1 && i9100_process_exit.sequence==1);
 assert(i9100_backboard_text(a,b,sizeof(a)) && strstr(a,"BBEXIT #1 PID73 SIG11 X1 EXC1"));
 i9100_springboard_exit_note(&p,9,(void*)2,(struct uthread*)(uintptr_t)1);
 assert(!i9100_backboard_exit.exception_known && !i9100_backboard_exit.exception);
 strcpy(p.p_comm,"SpringBoard");
 struct proc sender={"launchd",1,(void*)3};
 arm_saved_state_t regs={0x37001000,0x74e7,0x10};
 running.machine.uss=&regs;context=&sender;context_task=sender.task;
 // All original CPSR mask combinations survive actual publication/latching C.
 for(unsigned mask=0;mask<4;mask++){
  test_mask=(mask&1?0x80:0)|(mask&2?0x40:0);
  unsigned saved=test_mask;
  i9100_springboard_signal_note(&p,15,0x80123457,0);
  assert(test_mask==saved);
  assert(i9100_signal_pending[0].context_pid==1 && i9100_signal_pending[0].lr==0x74e7);
  assert(i9100_signal_pending[0].caller_pc==0x80123457);
  // Posting another fatal signal cannot erase the SIGTERM request.
  i9100_springboard_signal_note(&p,9,0x80123499,1);
  i9100_springboard_exit_note(&p,15,(void*)1,&ut);
  assert(test_mask==saved && i9100_signal_exit.signal==15);
  assert(!i9100_signal_pending[0].sequence && !i9100_signal_pending[1].sequence);
  assert(i9100_signal_text(a,b,sizeof(a)) && strstr(a,"SIG15 CTX1:launchd IRQ0 F0"));
  assert(!strcmp(b,"K80123457 U37001000 LR000074e7"));
 }
 // A respawn's signal request must not change the retained exit origin.
 p.p_pid=74;p.task=(void*)4;
 i9100_springboard_signal_note(&p,9,0x80123499,4);
 assert(i9100_signal_text(a,b,sizeof(a)) && strstr(b,"LR000074e7"));
 // PID alone is not enough: a different task must not inherit this record.
 p.task=(void*)5;
 i9100_springboard_exit_note(&p,9,(void*)2,(struct uthread*)(uintptr_t)1);
 assert(!i9100_signal_exit.sequence);
 // IRQ context must never touch a stale or poisoned user register pointer.
 irq=1;running.machine.uss=(void*)1;context=(void*)1;
 i9100_springboard_signal_note(&p,15,0x801234a1,0);
 assert(i9100_signal_pending[0].irq==1 && !i9100_signal_pending[0].context_pid);
 assert(!i9100_signal_pending[0].pc && !i9100_signal_pending[0].lr);
 assert(!strcmp((const char*)i9100_signal_pending[0].context_name,"kernel"));
 irq=0;context_task=(void*)0x9999;
 i9100_springboard_signal_note(&p,15,0x801234a1,0);
 assert(!i9100_signal_pending[0].context_pid && !i9100_signal_pending[0].pc);
 context_task=sender.task;context=NULL;
 i9100_springboard_signal_note(&p,15,0x801234a1,0);
 assert(!i9100_signal_pending[0].context_pid && !i9100_signal_pending[0].pc);
 context_task=sender.task;context=&sender;running.machine.uss=&regs;
 regs.cpsr=0x13;
 i9100_springboard_signal_note(&p,15,0x801234a1,0);
 assert(!i9100_signal_pending[0].pc && !i9100_signal_pending[0].lr);
 unsigned seq=i9100_signal_pending[0].sequence;
 i9100_springboard_signal_note(&p,0,1,0);
 i9100_springboard_signal_note(&p,11,1,0);
 i9100_springboard_signal_note(NULL,15,1,0);
 p.p_lflag=P_LEXIT;i9100_springboard_signal_note(&p,15,1,0);p.p_lflag=0;
 p.p_flag=P_REBOOT;i9100_springboard_signal_note(&p,15,1,0);p.p_flag=0;
 strcpy(p.p_comm,"SpringBoardHelper");i9100_springboard_signal_note(&p,15,1,0);
 assert(i9100_signal_pending[0].sequence==seq);
 // Bounded name capture also works with an exactly 16-character process name.
 strcpy(sender.p_comm,"1234567890123456");strcpy(p.p_comm,"SpringBoard");
 i9100_signal_pending[0].sequence=0xffffffff;
 i9100_springboard_signal_note(&p,15,0x801234a1,0);
 assert(i9100_signal_pending[0].sequence==1);
 i9100_springboard_exit_note(&p,15,(void*)2,(struct uthread*)(uintptr_t)1);
 i9100_signal_text(small.a,b,sizeof(small.a));
 assert(small.before==0x55 && small.after==0x66 && small.a[7]==0);
 regs.cpsr=0x10;
 i9100_springboard_signal_note(&p,6,0x801234ab,4);
 assert(i9100_signal_pending[2].signal==6);
 i9100_springboard_exit_note(&p,6,(void*)2,(struct uthread*)(uintptr_t)1);
 assert(i9100_signal_exit.signal==6 && !i9100_signal_pending[2].sequence);
 puts("PASS: actual UI exit/signal hooks + publishers; SIGTERM/SIGKILL independent capture; task identity, respawn retention, IRQ/kernel poisoned-register exclusion, all4 CPSR masks, bounded text and wrap; ASan/UBSan");
}
'''
with tempfile.TemporaryDirectory(prefix='i9100-process-') as folder:
    path = Path(folder)
    (path/'test.c').write_text(code)
    subprocess.run(['clang', '-O1', '-fsanitize=address,undefined', str(path/'test.c'),
                    '-o', str(path/'test')], check=True)
    subprocess.run([str(path/'test')], check=True)
