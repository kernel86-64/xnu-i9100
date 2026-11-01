#!/usr/bin/env python3
"""Cross-build the original iOS7 ARMv7 smoke client using symbol-only stubs."""
from pathlib import Path
import subprocess
here=Path(__file__).resolve().parent
root=here.parents[1]
headers=(root/'xnu' if (root/'xnu/iokit').is_dir() else root)/'iokit/Drivers/KernelBuiltIn/ARM/AppleARMPlatform'
out=here/'out';out.mkdir(exist_ok=True)
for name,path,symbols in [
 ('IOKit','/System/Library/Frameworks/IOKit.framework/Versions/A/IOKit',['IOServiceMatching','IOServiceGetMatchingService','IOServiceOpen','IOObjectRelease','IOServiceClose','IOConnectCallStructMethod']),
 ('System','/usr/lib/libSystem.B.dylib',['mach_task_self_','printf','puts','usleep','dyld_stub_binder'])]:
 text='--- !tapi-tbd-v3\narchs: [ armv7 ]\nplatform: ios\ninstall-name: '+path+'\nexports:\n  - archs: [ armv7 ]\n    symbols: [ '+', '.join(s if s=='dyld_stub_binder' else '_'+s for s in symbols)+' ]\n...\n'
 (out/('lib'+name+'.tbd')).write_text(text)
command=['xcrun','clang','--target=armv7-apple-ios7.0','-mthumb','-O2','-fno-stack-protector','-nostdlib','-Wl,-ld_classic','-Wl,-e,_main','-I',str(headers),str(here/'i9100-mali-smoke.c'),'-L',str(out),'-lIOKit','-lSystem','-o',str(out/'i9100-mali-smoke')]
subprocess.run(command,check=True)
subprocess.run(['codesign','--force','--sign','-','--digest-algorithm','sha1,sha256','--identifier','org.i9100.mali-smoke',str(out/'i9100-mali-smoke')],check=True)
print(out/'i9100-mali-smoke')
