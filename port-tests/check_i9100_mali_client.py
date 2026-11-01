#!/usr/bin/env python3
"""Run the actual userspace client against actual Mali C through a mock IOKit transport."""
from pathlib import Path
import ast
import subprocess
import tempfile
root=Path(__file__).resolve().parent.parent
helper=ast.parse((root/'port-tests/check_i9100_mali.py').read_text())
fixture=next(ast.literal_eval(n.value) for n in helper.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='code' for t in n.targets))
fixture=fixture[:fixture.index('int main(void){')]
client=(root/'userland/mali/i9100-mali-smoke.c').read_text().replace('int main(void){','int client_entry(void){')
code=fixture+client+r'''
port_t mach_task_self_=99;
static unsigned mode,opens,closes,draws,tries;
void *IOServiceMatching(const char *name){assert(!strcmp(name,"IOS7I9100Mali"));return (void*)1;}
port_t IOServiceGetMatchingService(port_t master,void *dict){assert(!master && dict==(void*)1);return mode==1?0:123;}
int IOServiceOpen(port_t service,port_t task,uint32_t type,port_t *out){assert(service==123 && task==99 && !type);opens++;*out=321;return mode==2?1:0;}
int IOObjectRelease(port_t service){assert(service==123);return 0;}
int IOServiceClose(port_t connection){assert(connection==321);closes++;return 0;}
int usleep(unsigned value){assert(value==100000);return 0;}
int IOConnectCallStructMethod(port_t connection,uint32_t selector,const void *input,size_t in,void *output,size_t *out){
 assert(connection==321 && selector==0 && input && in==32 && output && *out==1040);
 if(mode==3)return (int)0xe00002d8U;
 if(mode==4 && tries++<2)return (int)0xe00002d8U;
 struct i9100_mali_request r;memcpy(&r,input,sizeof(r));assert(i9100_mali_request_valid(&r));
 initialize(OK,0);m.user_request=1;
 struct i9100_mali_io io={NULL,read32,write32,delay,barrier,pmic_read,pmic_write};
 struct i9100_mali_status s={0};struct i9100_mali_reply reply={1};
 reply.error=i9100_mali_render_request(&io,m.arena,pa,sizeof(m.arena),&s,&r);
 reply.restore=s.restore;reply.pixels=s.pixels;assert(!reply.error && s.guard);
 for(unsigned n=0;n<256;n++)reply.output[n]=m.arena[0x8080/4+n];
 if(mode==5)reply.output[70]^=0x00101010;
 if(mode==6)reply.error=-12;
 memcpy(output,&reply,sizeof(reply));*out=sizeof(reply);draws++;return 0;
}
int main(void){
 for(mode=0;mode<7;mode++){
  opens=closes=draws=tries=0;int result=client_entry();
  if(mode==0 || mode==4)assert(result==0 && draws==3 && closes==1);
  if(mode==1)assert(result==1 && !opens && !draws);
  if(mode==2)assert(result==2 && !draws);
  if(mode==3 || mode==6)assert(result==3 && closes==1);
  if(mode==5)assert(result==4 && closes==1);
 }
 puts("PASS: original userspace C + original Mali core with mock IOKit: clear/copy/blend wire/readback, bounded startup retry, absent service/open/fault/pixel failures; ASan/UBSan. Not a device test.");
}
'''
folder=root/'iokit/Drivers/KernelBuiltIn/ARM/AppleARMPlatform'
with tempfile.TemporaryDirectory(prefix='mali-client-') as d:
 d=Path(d);(d/'test.c').write_text(code)
 subprocess.run(['clang','-O1','-fsanitize=address,undefined','-I',str(folder),str(folder/'i9100_mali.c'),str(d/'test.c'),'-o',str(d/'test')],check=True)
 subprocess.run([str(d/'test')],check=True)
