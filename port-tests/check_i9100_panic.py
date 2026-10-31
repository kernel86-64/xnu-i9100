#!/usr/bin/env python3
"""Exercise actual board panic renderer after graphics handover with mock MMIO."""
from pathlib import Path
import re
import subprocess
import tempfile
root=Path(__file__).resolve().parent.parent
s=(root/'pexpert/arm/pe_exynos4210_i9100.c').read_text()
def function(name):
 m=re.search(r'(?m)^(?:static )?(?:int|void)\s+'+name+r'\([^;]*?\)\s*\{',s)
 if not m:raise RuntimeError(name)
 depth=1
 for end in range(m.end(),len(s)):
  depth+=(s[end]=='{')-(s[end]=='}')
  if not depth:return s[m.start():end+1]
 raise RuntimeError('Unclosed function')
functions=['i9100f_blank_line','i9100f_scroll_up','i9100f_newline','ios7i9100_fast_putc','i9100_puts','i9100_puthex','ios7i9100_fatal_report','ios7i9100_panic_text_begin','ios7i9100_panic_text_putc','ios7i9100_panic_text_end']
code=r'''
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <strings.h>
typedef uintptr_t vm_offset_t;typedef uintptr_t vm_map_offset_t;
#define VM_WIMG_WTHRU 0
static volatile unsigned int *i9100_pixels;
static vm_offset_t i9100_fimd_map;
static unsigned int i9100_fb_physical,i9100_stage=10;
static unsigned int i9100_fatal_active,i9100_fatal_category,i9100_fatal_state[8];
static unsigned int i9100f_cx,i9100f_cy,i9100_panic_text_mode;
static unsigned int i9100_panic_header_frozen,i9100_fatal_callsite;
static unsigned int i9100_panic_text_len,i9100_panic_text_truncated;
static unsigned int i9100_panic_reason,i9100_panic_reason_known;
static char i9100_panic_text[768];
static int i9100f_wiped,i9100f_remapped,i9100_panel_console_enabled;
static int pmap_initialized=1;
static unsigned char iso_font[256*16];
static char rendered[4096];static unsigned rendered_count;
static char serial[4096];static unsigned serial_count,switched;
static void ios7i9100_debug_putc(char c){if(serial_count<sizeof(serial)-1)serial[serial_count++]=c;}
static struct {void (*uart_putc)(char);} gPESocDispatch={ios7i9100_debug_putc};
static int switch_to_serial_console(void){switched++;return 0;}
static vm_offset_t io_map_spec(vm_map_offset_t p,unsigned n,unsigned flags){(void)p;(void)n;(void)flags;assert(!"panic attempted IO allocation");return 0;}
static vm_offset_t ml_io_map(unsigned p,unsigned n){(void)p;(void)n;assert(!"panic attempted IO allocation");return 0;}
void ios7i9100_fast_putc(char c);
static void i9100_puts(const char *s);
static void i9100_puthex(unsigned int v);
'''
code+='\n'.join(function(n) for n in functions)
code=code.replace('void ios7i9100_fast_putc(char c)\n{','void ios7i9100_fast_putc(char c)\n{\n if(rendered_count<sizeof(rendered)-1)rendered[rendered_count++]=c;')
code=code.replace('__asm__ volatile("dsb sy" ::: "memory");','__asm__ volatile("" ::: "memory");')
code+=r'''
int main(void) {
 static unsigned int guard[480*800+2],registers[0x200/4];
 memset(iso_font,0xff,sizeof(iso_font));
 for(unsigned n=0;n<480*800+2;n++)guard[n]=0x12345678;
 i9100_pixels=guard+1;i9100_fimd_map=(uintptr_t)registers;
 assert(ios7i9100_fatal_report(0xf101,0x12345678,0,0,0,0,0,"fault %u")==1);
 assert(i9100_fatal_active && i9100_panel_console_enabled && switched==1);
 assert(guard[0]==0x12345678 && guard[480*800+1]==0x12345678);
 unsigned white=0,black=0;
 for(unsigned n=1;n<=480*800;n++){assert(guard[n]==0xff000000 || guard[n]==0xffffffff);white+=guard[n]==0xffffffff;black+=guard[n]==0xff000000;}
 assert(white && black && registers[0x1a4/4]==3);
 assert(strstr(serial,"CALL=12345678"));
 assert(ios7i9100_fatal_report(0xf103,0,0,0,0,0,0,"nested")==0);
 assert(i9100_fatal_state[0]==0xf101);
 assert(!ios7i9100_panic_text_begin(0,0,0));
 assert(ios7i9100_panic_text_begin(42,1,1));
 // Full FAULT11 busy-lock witness must fit the pinned area, not just capture.
 const char *witness="hw_lock busy L=8057af14 V=00000001\n"
 "ATT=800c141f UP=8002cfbb T=c1e79a38 IRQ=4294967295\n"
 "OWNER=00000000 UP=00000000 T=00000000 IRQ=4294967295 DEP=4294967295\n"
 "KNOWN=0 MASK=00000193 DROPS=4294967295\n"
 "FAULT=4294967295 TYPE=4 RET=2\n"
 "PC=3ab5680a LR=30000001 SP=2ffff000\n"
 "FAR=12345678 FSR=00000805 PSR=00000030\n"
 "H0=4294967295 OP=2 V=0 PC=8002cfcf T=c1e79a38\n"
 "H1=4294967294 OP=1 V=1 PC=8002cfbb T=c1e79a38";
 rendered_count=0;memset(rendered,0,sizeof(rendered));
 for(unsigned n=0;witness[n];n++)ios7i9100_panic_text_putc(witness[n]);
 ios7i9100_panic_text_end();
 assert(!i9100_panic_text_truncated && !strstr(rendered,"message truncated"));
 assert(strstr(rendered,"H1=4294967294"));
 i9100_panic_text_mode=0;i9100_panic_header_frozen=0;i9100_panic_text_len=0;
 assert(ios7i9100_panic_text_begin(42,1,1));
 const char *text="real formatted value=123";
 for(unsigned n=0;text[n];n++)ios7i9100_panic_text_putc(text[n]);
 assert(i9100_panic_text_len==strlen(text));
 assert(!memcmp(i9100_panic_text,text,strlen(text)));
 // Keep the beginning of a long formatted panic when the capture fills.
 for(unsigned n=0;n<4000;n++)ios7i9100_panic_text_putc(n%73?'X':'\n');
 ios7i9100_panic_text_end();
 assert(i9100_panic_text_mode==2 && registers[0x1a4/4]==3);
 assert(i9100_panic_header_frozen && i9100f_cy==256);
 assert(i9100_panic_text_len==sizeof(i9100_panic_text) && i9100_panic_text_truncated);
 assert(!memcmp(i9100_panic_text,text,strlen(text)));
 static unsigned int pinned[480*256];
 memcpy(pinned,(const void*)i9100_pixels,sizeof(pinned));
 // Simulate many pages of debugger/user backtrace after _doprnt completes.
 for(unsigned n=0;n<20000;n++)ios7i9100_fast_putc(n%67?'B':'\n');
 assert(!memcmp(pinned,(const void*)i9100_pixels,sizeof(pinned)));
 // Console carriage returns/tabs and an externally reset cursor cannot enter it.
 i9100f_cy=0;i9100f_cx=0;
 ios7i9100_fast_putc('Q');ios7i9100_fast_putc('\r');ios7i9100_fast_putc('\t');
 assert(i9100f_cy>=256 && !memcmp(pinned,(const void*)i9100_pixels,sizeof(pinned)));
 assert(!ios7i9100_panic_text_begin(0,0,1));
 assert(guard[0]==0x12345678 && guard[480*800+1]==0x12345678);
 // Panic before a framebuffer is available must remain allocation-free.
 i9100_pixels=0;i9100_fimd_map=0;i9100_fatal_active=0;i9100_panic_text_mode=0;i9100_panic_header_frozen=0;i9100_panic_text_len=0;
 assert(ios7i9100_fatal_report(0xf101,0,0,0,0,0,0,"early")==1);
 assert(ios7i9100_panic_text_begin(0,0,1));
 ios7i9100_panic_text_putc('X');ios7i9100_panic_text_end();
 puts("Panic renderer: reclaim after graphics, first-owner capture, CALL field, bounded first-message capture, pinned header across 20K debugger characters, wrap/scroll guards, FIMD trigger and no mapping/allocation with or without framebuffer passed");
}
'''
with tempfile.TemporaryDirectory(prefix='i9100-panic-') as d:
 d=Path(d);(d/'test.c').write_text(code)
 subprocess.run(['cc','-std=c11','-D_DEFAULT_SOURCE','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',str(d/'test.c'),'-o',str(d/'test')],check=True)
 subprocess.run([str(d/'test')],check=True)
