#!/usr/bin/env python3
"""Exercise actual ARM syscall marshaling, psynch tail and uthread prefix."""
from pathlib import Path
import re
import subprocess
import tempfile

root = Path(__file__).resolve().parent.parent
source = (root/'bsd/dev/arm/unix_syscalls.c').read_text()


def function(marker):
    start = source.index(marker)
    pos = source.index('{', start)+1
    depth = 1
    while depth:
        depth += (source[pos] == '{')-(source[pos] == '}')
        pos += 1
    return source[start:pos]


user = (root/'bsd/sys/user.h').read_text()
prefix = user[user.index('struct uthread {'):user.index('char uu_cursig;')+len('char uu_cursig;')]+ '\n};'
# Model only the 32-bit kernel pointer on this 64-bit host; scalar field order
# and ARM argument declaration come directly from user.h.
prefix = re.sub(r'int\s*\*uu_ap', 'uint32_t uu_ap', prefix)
assert 'uu_arg[12]' in prefix
code = r'''
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <assert.h>
#include <stddef.h>
#define __arm__ 1
#define EINVAL 22
#define EFAULT 14
typedef int32_t mach_exception_code_t;
typedef int32_t mach_exception_subcode_t;
typedef uint64_t user_addr_t;
static uint32_t user_tail[4]={0x12345678,0xaabbccdd,0x13572468,0x87654321};
static unsigned bad_copy;
static int copyin(user_addr_t from,void *to,size_t size){
 if(bad_copy||from!=0x1000001c||size!=16)return EFAULT;
 memcpy(to,user_tail,size);return 0;
}
'''+prefix+function('static int arm_syscall_store_args(')+function('static int\nios7lab_psynch_stack_tail(')+r'''
static unsigned regs[13];
int main(void){
 for(unsigned i=0;i<13;i++)regs[i]=0x12340000+i*0x111;
 struct uthread u;memset(&u,0xa5,sizeof(u));
#ifdef OLD_CONTROL
 unsigned arg_count=11;
 for(unsigned i=0;i<12;i++){u.uu_arg[i]=regs[i];if(i==arg_count)break;}
 assert(u.uu_exception==(int)regs[11] && u.uu_ap==regs[8]);
 assert(!ios7lab_psynch_stack_tail(304,0x10000000,u.uu_arg,11));
 u.uu_rval[0]=u.uu_rval[1]=0;
 unsigned actual;memcpy(&actual,(char*)&u+10*4,4);
 assert(actual==0 && user_tail[3]!=0);
 puts("OLD CONTROL: 11-word CV syscall overwrites uu_ap/uu_rval/uu_exception; retval reset destroys the final flags/tail words");
 return 23;
#else
 _Static_assert(offsetof(struct uthread,uu_ap)==48,"ARM32 prefix");
 unsigned cases=0;
 for(unsigned shift=0;shift<2;shift++)for(unsigned capacity=0;capacity<=12;capacity++)for(unsigned count=0;count<=16;count++){
  memset(&u,0xa5,sizeof(u));struct uthread previous=u;
  int error=arm_syscall_store_args(u.uu_arg,capacity,regs,count,shift);
  int reject=count>capacity || count>12-shift;
  assert(error==(reject?EINVAL:0));
  for(unsigned i=0;i<12;i++)assert(u.uu_arg[i]==(!reject&&i<count?regs[i+shift]:previous.uu_arg[i]));
  assert(!memcmp((char*)&u+48,(char*)&previous+48,sizeof(u)-48));cases++;
 }
 for(unsigned call=303;call<=305;call++){
  memset(&u,0xa5,sizeof(u));struct uthread previous=u;
  assert(!arm_syscall_store_args(u.uu_arg,12,regs,11,0));
  assert(!ios7lab_psynch_stack_tail(call,0x10000000,u.uu_arg,11));
  u.uu_rval[0]=u.uu_rval[1]=0;
  assert(!memcmp(u.uu_arg,regs,28) && !memcmp(u.uu_arg+7,user_tail,16));
  assert(u.uu_exception==previous.uu_exception && u.uu_ap==previous.uu_ap);
  bad_copy=1;unsigned before[12];memcpy(before,u.uu_arg,48);
  assert(ios7lab_psynch_stack_tail(call,0x10000000,u.uu_arg,11)==EFAULT && !memcmp(before,u.uu_arg,48));bad_copy=0;
  assert(ios7lab_psynch_stack_tail(call,0x10000000,u.uu_arg,10)==EINVAL);
 }
 assert(!arm_syscall_store_args(NULL,0,NULL,0,0));
 printf("PASS: actual uthread ARM32 prefix and marshaler %u boundary/direct/indirect cases; all3 actual psynch tails survive retval initialization, invalid-copy exclusion; ASan/UBSan\n",cases);
#endif
}
'''
with tempfile.TemporaryDirectory(prefix='i9100-sysargs-') as folder:
    folder = Path(folder)
    (folder/'new.c').write_text(code)
    subprocess.run(['clang','-O1','-fsanitize=address,undefined','-fno-sanitize-recover=all',
                    str(folder/'new.c'),'-o',str(folder/'new')],check=True)
    subprocess.run([str(folder/'new')],check=True)
    (folder/'old.c').write_text(code.replace('uu_arg[12]', 'uu_arg[8]'))
    subprocess.run(['clang','-O0','-DOLD_CONTROL',str(folder/'old.c'),'-o',str(folder/'old')],check=True)
    result = subprocess.run([str(folder/'old')])
    assert result.returncode == 23, result.returncode
