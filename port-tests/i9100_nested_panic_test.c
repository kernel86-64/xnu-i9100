/* Actual panic_prologue and raw board stop gate are injected by the runner. */
typedef unsigned int uint32_t;typedef uint32_t spl_t;
#define TRUE 1
#define FALSE 0
static unsigned kdebug_enable,disable_debug_output,debug_mode,paniccpu,panicwait,nestedpanic;
static const char *panicstr,*original;
static unsigned locked,outputs,used;
static char output[128];
static void semihost(uint32_t op,const void*p){register uint32_t r0 __asm__("r0")=op;register const void*r1 __asm__("r1")=p;__asm__ volatile("svc 0x123456":"+r"(r0):"r"(r1):"memory");}
static void __attribute__((noreturn)) finish(uint32_t c){uint32_t v[2]={0x20026,c};semihost(0x20,v);for(;;){}}
#define CHECK(x) do{if(!(x)){semihost(4,"FAIL: " #x "\n");finish(1);}}while(0)
static void test_stop(void) __attribute__((noreturn));
static void i9100_puts(const char*);
static spl_t splhigh(void){return 42;}
static void disable_preemption(void){}
static void panic_safe(void){}
static void ml_set_interrupts_enabled(int b){(void)b;}
static void kdbg_dump_trace_to_file(const char*s){(void)s;}
static int cpu_number(void){return 0;}
static void Debugger(const char*s){(void)s;semihost(4,"FAIL: nested panic entered Debugger\n");finish(1);}
static int printf(const char*s,...){(void)s;CHECK(0);return 0;}
static void panic_stop(void){CHECK(0);}
#define PANIC_LOCK() do{CHECK(!locked);locked=1;}while(0)
#define PANIC_UNLOCK() do{CHECK(locked);locked=0;}while(0)
#include "nested-under-test.inc"
static void i9100_puts(const char*s){
 outputs++;
 if(TEST_REENTER)ios7i9100_nested_panic_stop();
 while(*s){CHECK(used<127);output[used++]=*s++;}
}
static void test_stop(void){
 uint32_t mask;__asm__ volatile("mrs %0,cpsr":"=r"(mask));
 CHECK((mask&0xc0)==0xc0 && !locked);
 CHECK(nestedpanic==1 && panicstr==original && panicwait==1 && outputs==1);
 if(TEST_REENTER)CHECK(!used);else CHECK(used>20);
 semihost(4,"ARM double-panic guard: primary message retained, panic lock released, no Debugger, IRQ/FIQ masked, recursive raw-output entry halted\n");finish(0);
}
void run(void){
 original="primary failure";
 CHECK(panic_prologue(original)==42 && panicstr==original && !locked && !outputs);
 panic_prologue("secondary failure");CHECK(0);
}
