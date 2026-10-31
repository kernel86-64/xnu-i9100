/* HTC HD2 integration/publication changes: Garysss123, 2026-10-04. Original license notices are preserved. */
/*
 * Copyright (c) 2000-2007 Apple Inc. All rights reserved.
 *
 * @APPLE_OSREFERENCE_LICENSE_HEADER_START@
 * 
 * This file contains Original Code and/or Modifications of Original Code
 * as defined in and that are subject to the Apple Public Source License
 * Version 2.0 (the 'License'). You may not use this file except in
 * compliance with the License. The rights granted to you under the License
 * may not be used to create, or enable the creation or redistribution of,
 * unlawful or unlicensed copies of an Apple operating system, or to
 * circumvent, violate, or enable the circumvention or violation of, any
 * terms of an Apple operating system software license agreement.
 * 
 * Please obtain a copy of the License at
 * http://www.opensource.apple.com/apsl/ and read it before using this file.
 * 
 * The Original Code and all software distributed under the License are
 * distributed on an 'AS IS' basis, WITHOUT WARRANTY OF ANY KIND, EITHER
 * EXPRESS OR IMPLIED, AND APPLE HEREBY DISCLAIMS ALL SUCH WARRANTIES,
 * INCLUDING WITHOUT LIMITATION, ANY WARRANTIES OF MERCHANTABILITY,
 * FITNESS FOR A PARTICULAR PURPOSE, QUIET ENJOYMENT OR NON-INFRINGEMENT.
 * Please see the License for the specific language governing rights and
 * limitations under the License.
 * 
 * @APPLE_OSREFERENCE_LICENSE_HEADER_END@
 */

/*
 * @OSF_COPYRIGHT@
 */

/*
 * Copyright 2013, winocm. <winocm@icloud.com>
 * All rights reserved.
 * 
 * Redistribution and use in source and binary forms, with or without modification,
 * are permitted provided that the following conditions are met:
 * 
 *   Redistributions of source code must retain the above copyright notice, this
 *   list of conditions and the following disclaimer.
 * 
 *   Redistributions in binary form must reproduce the above copyright notice, this
 *   list of conditions and the following disclaimer in the documentation and/or
 *   other materials provided with the distribution.
 * 
 *   If you are going to use this software in any form that does not involve
 *   releasing the source to this project or improving it, let me know beforehand.
 *
 * THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
 * ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
 * WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
 * DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE FOR
 * ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
 * (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
 * LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON
 * ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
 * (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
 * SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
 */

/*
 * ARM machine routines
 */

#include <arm/machine_routines.h>
#if defined(BOARD_CONFIG_EXYNOS4210_I9100)
#include "i9100_time_math.h"
#endif
#include <arm/io_map_entries.h>
#include <arm/cpu_affinity.h>
#include <mach/processor.h>
#include <kern/processor.h>
#include <kern/machine.h>
#include <kern/cpu_data.h>
#include <kern/cpu_number.h>
#include <kern/thread.h>

#include <vm/pmap.h>

#include <arm/trap.h>
#include <mach/vm_param.h>
#include <arm/pmap.h>

#include <pexpert/arm/boot.h>

#include <arm/cpuid.h>
#if defined(BOARD_CONFIG_EXYNOS4210_I9100)
#include <arm/i9100_diagnostics.h>
#endif

#if defined(BOARD_CONFIG_EXYNOS4210_I9100)
/* UP diagnostic ownership table. No allocation, spinlocks, clock reads or
 * scheduler calls. Raw CPSR exclusion keeps recording independent of the
 * locks it observes. A bounded collision miss is reported as unknown. */
#define I9100_SPIN_SLOTS 2048U
#define I9100_SPIN_PROBES 16U
struct i9100_spin_record {
    uint32_t key, caller, parent, thread, irq, depth;
};
static volatile struct i9100_spin_record i9100_spin_records[I9100_SPIN_SLOTS];
/* Largest distance ever allocated by each hash bucket. A deletion leaves this
 * upper bound intact, so holes cannot hide a colliding live record. Most hot
 * buckets need one/two probes instead of scanning all16 slots on every create.
 * These bytes are protected by the existing raw IRQ/FIQ exclusion. */
static uint8_t i9100_spin_span[I9100_SPIN_SLOTS];
static volatile uint32_t i9100_spin_drops;
void i9100_spin_acquired(uint32_t,uint32_t,uint32_t,uint32_t);
void i9100_spin_forget(uint32_t,uint32_t,uint32_t,uint32_t);
void i9100_spin_busy(uint32_t,uint32_t,uint32_t,uint32_t) __attribute__((noreturn));

static uint32_t i9100_spin_mask(void)
{
    uint32_t value;
    __asm__ volatile("mrs %0,cpsr\n\tcpsid if" : "=r"(value) :: "memory");
    return value;
}
static void i9100_spin_restore(uint32_t value)
{
    __asm__ volatile("msr cpsr_c,%0" :: "r"(value) : "memory");
}
/* Only the log lock is watched: unrelated lock traffic cannot evict its
 * history. These are completed hook observations, not atomic lock transitions.
 * OP=1 acquired, 2 unlocked, 3 initialized. Never alter the observed lock. */
struct i9100_log_event { uint32_t sequence,kind,value,caller,thread; };
static volatile struct i9100_log_event i9100_log_events[16];
static uint32_t i9100_log_key,i9100_log_sequence;
void i9100_log_watch(uint32_t key)
{
    uint32_t mask=i9100_spin_mask();
    if(!i9100_log_key)i9100_log_key=key;
    i9100_spin_restore(mask);
}
static void i9100_log_event(uint32_t key,uint32_t kind,uint32_t caller,uint32_t thread)
{
    if(key!=i9100_log_key)return;
    uint32_t sequence=++i9100_log_sequence;
    volatile struct i9100_log_event *p=&i9100_log_events[sequence&15U];
    p->kind=kind;p->value=*(volatile uint32_t *)(uintptr_t)key;
    p->caller=caller;p->thread=thread;p->sequence=sequence;
}
/* Keep failed user-fault entry values across printf and exception delivery.
 * Records are historical: FAULT is the sequence of the last failed fault for
 * this thread, not a claim that every later panic is caused by that fault. */
struct i9100_failed_fault { struct i9100_fault_snapshot state; uint32_t sequence; };
static volatile struct i9100_failed_fault i9100_failed_faults[16];
static uint32_t i9100_fault_sequence;
void i9100_fault_failed(const struct i9100_fault_snapshot *s,uint32_t result)
{
    uint32_t mask=i9100_spin_mask(),sequence=++i9100_fault_sequence;
    volatile struct i9100_failed_fault *p=&i9100_failed_faults[sequence&15U];
    p->state.thread=s->thread;p->state.type=s->type;
    p->state.pc=s->pc;p->state.lr=s->lr;p->state.sp=s->sp;
    p->state.far=s->far;p->state.fsr=s->fsr;p->state.psr=s->psr;
    p->state.result=result;p->sequence=sequence;
    i9100_spin_restore(mask);
}
static const struct i9100_failed_fault i9100_no_fault;
static const volatile struct i9100_failed_fault *i9100_fault_find(uint32_t thread)
{
    for(uint32_t n=0;n<16U;n++){
        uint32_t sequence=i9100_fault_sequence-n;
        volatile struct i9100_failed_fault *p=&i9100_failed_faults[sequence&15U];
        if(p->sequence && p->sequence==sequence && p->state.thread==thread)return p;
    }
    return &i9100_no_fault;
}
#define I9100_FAULT_FORMAT "\nFAULT=%u TYPE=%u RET=%x\nPC=%08x LR=%08x SP=%08x\nFAR=%08x FSR=%08x PSR=%08x"
#define I9100_FAULT_ARGS(f) (f)->sequence,(f)->state.type,(f)->state.result, \
    (f)->state.pc,(f)->state.lr,(f)->state.sp,(f)->state.far,(f)->state.fsr,(f)->state.psr
static volatile struct i9100_spin_record *i9100_spin_find(uint32_t key,int create)
{
    uint32_t slot=((key>>2)^(key>>13))&(I9100_SPIN_SLOTS-1U);
    uint32_t limit=i9100_spin_span[slot];
    if(limit>I9100_SPIN_PROBES)limit=I9100_SPIN_PROBES;
    volatile struct i9100_spin_record *empty=0;
    for(uint32_t n=0;n<limit;n++){
        volatile struct i9100_spin_record *p=&i9100_spin_records[(slot+n)&(I9100_SPIN_SLOTS-1U)];
        if(p->key==key)return p;
        if(!p->key && !empty)empty=p;
    }
    if(!create)return 0;
    if(empty)return empty;
    for(uint32_t n=limit;n<I9100_SPIN_PROBES;n++){
        volatile struct i9100_spin_record *p=&i9100_spin_records[(slot+n)&(I9100_SPIN_SLOTS-1U)];
        if(!p->key){i9100_spin_span[slot]=(uint8_t)(n+1U);return p;}
    }
    return 0;
}
static uint32_t i9100_spin_parent(uint32_t frame,uint32_t raw_thread)
{
    thread_t thread=(thread_t)(uintptr_t)raw_thread;
    if(!thread || (frame&3U))return 0;
    uint32_t base=(uint32_t)thread->kernel_stack;
    cpu_data_t *cpu=current_cpu_datap();
    if((base>=0x80000000U && frame>=base && frame-base<=KERNEL_STACK_SIZE-8U) ||
       (cpu && cpu->cpu_int_stack_top>=INTSTACK_SIZE &&
        frame>=cpu->cpu_int_stack_top-INTSTACK_SIZE && frame<=cpu->cpu_int_stack_top-8U))
        return ((volatile uint32_t *)(uintptr_t)frame)[1];
    return 0;
}
/* Track every explicit assembly increment by thread and resulting depth.
 * Records are removed before the matching generic decrement. This includes
 * raw scopes and mutex interlocks, not just held spinlocks. */
#define I9100_SCOPE_SLOTS 1024U
struct i9100_scope_record {uint32_t thread,depth,caller,parent,site;};
static volatile struct i9100_scope_record i9100_scope_records[I9100_SCOPE_SLOTS];
static uint8_t i9100_scope_span[I9100_SCOPE_SLOTS];
static volatile uint32_t i9100_scope_drops;
void i9100_preempt_enter(uint32_t,uint32_t,uint32_t,uint32_t);
void i9100_preempt_leave(uint32_t);
static volatile struct i9100_scope_record *i9100_scope_find(uint32_t thread,uint32_t depth,int create)
{
    uint32_t slot=((thread>>4)^(thread>>14)^(depth*31U))&(I9100_SCOPE_SLOTS-1U);
    uint32_t limit=i9100_scope_span[slot];
    if(limit>16U)limit=16U;
    volatile struct i9100_scope_record *empty=0;
    for(uint32_t n=0;n<limit;n++){
        volatile struct i9100_scope_record *p=&i9100_scope_records[(slot+n)&(I9100_SCOPE_SLOTS-1U)];
        if(p->thread==thread && p->depth==depth)return p;
        if(!p->thread && !empty)empty=p;
    }
    if(!create)return 0;
    if(empty)return empty;
    for(uint32_t n=limit;n<16U;n++){
        volatile struct i9100_scope_record *p=&i9100_scope_records[(slot+n)&(I9100_SCOPE_SLOTS-1U)];
        if(!p->thread){i9100_scope_span[slot]=(uint8_t)(n+1U);return p;}
    }
    return 0;
}
void i9100_preempt_enter(uint32_t raw_thread,uint32_t caller,uint32_t frame,uint32_t site)
{
    uint32_t mask=i9100_spin_mask();
    thread_t thread=(thread_t)(uintptr_t)raw_thread;
    uint32_t depth=thread?thread->machine.preempt_count:0;
    if(depth){
        volatile struct i9100_scope_record *p=i9100_scope_find(raw_thread,depth,1);
        if(p){p->depth=depth;p->caller=caller;p->parent=i9100_spin_parent(frame,raw_thread);p->site=site;p->thread=raw_thread;}
        else i9100_scope_drops++;
    }
    i9100_spin_restore(mask);
}
void i9100_preempt_leave(uint32_t raw_thread)
{
    uint32_t mask=i9100_spin_mask();
    thread_t thread=(thread_t)(uintptr_t)raw_thread;
    if(thread){
        volatile struct i9100_scope_record *p=i9100_scope_find(raw_thread,thread->machine.preempt_count,0);
        if(p)p->thread=0;
    }
    i9100_spin_restore(mask);
}

void i9100_spin_acquired(uint32_t key,uint32_t caller,uint32_t frame,uint32_t raw_thread)
{
    uint32_t mask=i9100_spin_mask();
    i9100_log_event(key,1,caller,raw_thread);
    volatile struct i9100_spin_record *p=i9100_spin_find(key,1);
    if(p){
        cpu_data_t *cpu=current_cpu_datap();
        thread_t thread=(thread_t)(uintptr_t)raw_thread;
        p->caller=caller;p->parent=i9100_spin_parent(frame,raw_thread);
        p->thread=raw_thread;p->irq=cpu?(uint32_t)cpu->cpu_interrupt_level:0;
        p->depth=thread?thread->machine.preempt_count:0;p->key=key;
    }else i9100_spin_drops++;
    i9100_spin_restore(mask);
}
void i9100_spin_forget(uint32_t key,uint32_t caller,uint32_t kind,uint32_t raw_thread)
{
    uint32_t mask=i9100_spin_mask();
    i9100_log_event(key,kind,caller,raw_thread);
    volatile struct i9100_spin_record *p=i9100_spin_find(key,0);
    if(p)p->key=0;
    i9100_spin_restore(mask);
}
void i9100_spin_busy(uint32_t key,uint32_t caller,uint32_t frame,uint32_t raw_thread)
{
    uint32_t mask=i9100_spin_mask();
    volatile struct i9100_spin_record *p=i9100_spin_find(key,0);
    uint32_t owner=p?p->caller:0,parent=p?p->parent:0,thread=p?p->thread:0;
    uint32_t irq=p?p->irq:0,depth=p?p->depth:0,known=p?1U:0;
    uint32_t attempted_parent=i9100_spin_parent(frame,raw_thread);
    cpu_data_t *cpu=current_cpu_datap();
    uint32_t attempt_irq=cpu?(uint32_t)cpu->cpu_interrupt_level:0;
    const volatile struct i9100_failed_fault *fault=i9100_fault_find(raw_thread);
    /* Zero events when the failed lock is not the watched log lock. */
    static const struct i9100_log_event empty;
    const volatile struct i9100_log_event *h0=&empty,*h1=&empty;
    if(key==i9100_log_key && i9100_log_sequence){
        h0=&i9100_log_events[i9100_log_sequence&15U];
        if(i9100_log_sequence>1)h1=&i9100_log_events[(i9100_log_sequence-1U)&15U];
    }
    /* Remain excluded on this terminal path; do not release a lock or retry. */
    (panic)("hw_lock busy L=%08x V=%08x\n"
          "ATT=%08x UP=%08x T=%08x IRQ=%u\n"
          "OWNER=%08x UP=%08x T=%08x IRQ=%u DEP=%u\n"
          "KNOWN=%u MASK=%08x DROPS=%u" I9100_FAULT_FORMAT
          "\nH0=%u OP=%u V=%x PC=%08x T=%08x"
          "\nH1=%u OP=%u V=%x PC=%08x T=%08x\nTRACE=%u",
          key,*(volatile uint32_t *)(uintptr_t)key,caller,attempted_parent,raw_thread,attempt_irq,
          owner,parent,thread,irq,depth,known,mask,i9100_spin_drops,
          I9100_FAULT_ARGS(fault),
          h0->sequence,h0->kind,h0->value,h0->caller,h0->thread,
          h1->sequence,h1->kind,h1->value,h1->caller,h1->thread,I9100_LOCK_TRACE);
    for(;;) __asm__ volatile("wfi");
}
/* Preserve the scheduler's terminal check, adding the held-lock context that
 * a plain preemption count cannot identify. Only called on the fatal path. */
void i9100_preempt_panic(int level) __attribute__((noreturn));
void i9100_preempt_panic(int level)
{
    (void)i9100_spin_mask();
    uint32_t raw_thread;
    __asm__ volatile("mrc p15,0,%0,c13,c0,4" : "=r"(raw_thread));
    uint32_t count=0,k0=0,c0=0,p0=0,k1=0,c1=0,p1=0;
    for(uint32_t n=0;n<I9100_SPIN_SLOTS;n++){
        volatile struct i9100_spin_record *p=&i9100_spin_records[n];
        if(!p->key || p->thread!=raw_thread)continue;
        if(!count){k0=p->key;c0=p->caller;p0=p->parent;}
        else if(count==1){k1=p->key;c1=p->caller;p1=p->parent;}
        count++;
    }
    cpu_data_t *cpu=current_cpu_datap();
    volatile struct i9100_scope_record *scope=i9100_scope_find(raw_thread,1,0);
    const volatile struct i9100_failed_fault *fault=i9100_fault_find(raw_thread);
    (panic)("thread_invoke PL=%d T=%08x IRQ=%u OWNED=%u\n"
          "L0=%08x PC=%08x UP=%08x\n"
          "L1=%08x PC=%08x UP=%08x\nSPIN_DROPS=%u\n"
          "RAW=%u PC=%08x UP=%08x SITE=%08x DROP=%u" I9100_FAULT_FORMAT "\nTRACE=%u",
          level,raw_thread,cpu?(uint32_t)cpu->cpu_interrupt_level:0,count,
          k0,c0,p0,k1,c1,p1,i9100_spin_drops,
          scope?1U:0,scope?scope->caller:0,scope?scope->parent:0,scope?scope->site:0,i9100_scope_drops,
          I9100_FAULT_ARGS(fault),I9100_LOCK_TRACE);
    for(;;)__asm__ volatile("wfi");
}

#endif

#define DBG(x...)	kprintf("DBG: " x)

uint32_t MutexSpin;
uint32_t LockTimeOut;

/**
 * ml_io_map
 *
 * Map memory mapped IO space to a virtual address.
 */
vm_offset_t ml_io_map(vm_offset_t phys_addr, vm_size_t size)
{
    return (io_map(phys_addr, size, VM_WIMG_IO));
}

/**
 * ml_static_malloc
 *
 * Unused.
 */
vm_offset_t ml_static_malloc(__unused vm_size_t size)
{
    return ((vm_offset_t) NULL);
}

/**
 * ml_vtophys
 *
 * Shim for kvtophys.
 */
vm_offset_t ml_vtophys(vm_offset_t vaddr)
{
    return (vm_offset_t) kvtophys(vaddr);
}

/**
 * ml_stack_remaining
 *
 * return the remaining kernel stack size
 */
vm_offset_t ml_stack_remaining(void)
{
    uintptr_t local = (uintptr_t)&local;

    if (ml_at_interrupt_context() != 0) {
        return (local - (current_cpu_datap()->cpu_int_stack_top - INTSTACK_SIZE));
    } else {
        return (local - current_thread()->kernel_stack);
    }
}

/**
 * ml_init_interrupt
 *
 * Set interrupts enabled to true.
 */
void ml_init_interrupt(void)
{
    (void) ml_set_interrupts_enabled(TRUE);
}

/**
 * ml_cpu_up
 *
 * This is called from the machine-independent routine cpu_up()
 * to perform machine-dependent info updates. Defer to cpu_thread_init().
 */
void ml_cpu_up(void)
{
    (void) hw_atomic_add(&machine_info.physical_cpu, 1);
    (void) hw_atomic_add(&machine_info.logical_cpu, 1);
    return;
}

/**
 * ml_cpu_down
 *
 * This is called from the machine-independent routine cpu_down()
 * to perform machine-dependent info updates.
 */
void ml_cpu_down(void)
{
    (void) hw_atomic_sub(&machine_info.physical_cpu, 1);
    (void) hw_atomic_sub(&machine_info.logical_cpu, 1);
    return;
}

/**
 * ml_cpu_cache_size
 *
 * Get the cpu memory size based on the level requested.
 * 0 == ram, 1 == L1 cache, 2 == L2 cache, ect.
 */
uint64_t ml_cpu_cache_size(unsigned int level)
{
    if (level == 0) {
        return machine_info.max_mem;
    } else if ( 1 <= level && level <= MAX_CACHE_DEPTH) {
        return arm_processor_id.cache_levels[level - 1].size;
    } else {
        return 0;
    }
}

/**
 * ovbcopy
 *
 * Overlapped bcopy.
 */
void ovbcopy(void *from, void *to, vm_size_t bytes)
{
    bcopy(from, to, bytes);
}

/**
 * bzero_phys
 *
 * Zero out a physical address. 
 */
void bzero_phys(addr64_t src64, uint32_t bytes)
{
#ifndef __LP64__
    bzero((void *)phys_to_virt((uint32_t) src64), bytes);
#else
    bzero((void *)phys_to_virt((uint64_t) src64), bytes);
#endif
}

/**
 * bcopy_phys
 *
 * The equivalent of bzero_phys but with additional copying features.
 * (patent pending)
 */
void bcopy_phys(addr64_t src64, addr64_t dst64, vm_size_t bytes)
{
#ifndef __LP64__
    bcopy((void *)phys_to_virt((uint32_t) src64), (void *)phys_to_virt((uint32_t) dst64), bytes);
#else
    bcopy((void *)phys_to_virt((uint64_t) src64), (void *)phys_to_virt((uint64_t) dst64), bytes);
#endif
    return;
}

/**
 * ml_init_lock_timeout
 */
void ml_init_lock_timeout(void)
{
    uint64_t abstime;
    uint32_t mtxspin;
    uint64_t default_timeout_ns = NSEC_PER_SEC >> 2;
    uint32_t slto;
    uint32_t prt;

    if (PE_parse_boot_argn("slto_us", &slto, sizeof(slto)))
        default_timeout_ns = slto * NSEC_PER_USEC;

    /*
     * LockTimeOut is absolutetime
     */
    nanoseconds_to_absolutetime(default_timeout_ns, &abstime);
    LockTimeOut = (uint32_t) abstime;

    if (PE_parse_boot_argn("mtxspin", &mtxspin, sizeof(mtxspin))) {
        if (mtxspin > USEC_PER_SEC >> 4)
            mtxspin = USEC_PER_SEC >> 4;
        nanoseconds_to_absolutetime(mtxspin * NSEC_PER_USEC, &abstime);
    } else {
        nanoseconds_to_absolutetime(10 * NSEC_PER_USEC, &abstime);
    }

    MutexSpin = (unsigned int) abstime;
}

/**
 * ml_get_max_cpus
 *
 * Since this is a uniprocessor system, we return 0.
 */
int ml_get_max_cpus(void)
{
    return (machine_info.max_cpus);
}

void ml_init_max_cpus(unsigned long max_cpus)
{
    machine_info.max_cpus = max_cpus;
    machine_info.physical_cpu_max = max_cpus;
    machine_info.logical_cpu_max = max_cpus;
    return;
}

void ml_install_interrupt_handler(void *nub, int source, void *target,
                                  IOInterruptHandler handler, void *refCon)
{
    boolean_t current_state;
    cpu_data_t *datap;

    current_state = ml_get_interrupts_enabled();

    datap = current_cpu_datap();
    assert(datap);
    datap->nub = nub;
    datap->target = target;
    datap->handler = handler;
    datap->refCon = refCon;

    (void) ml_set_interrupts_enabled(current_state);

    initialize_screen(NULL, kPEAcquireScreen);
}

/**
 * ml_processor_register
 *
 * Register a processor with the system and add it to the master list.
 */

/*
 * initialize and bring up the CPU.
 */
kern_return_t ml_processor_register(cpu_id_t cpu_id,
                                    processor_t * processor_out,
                                    ipi_handler_t * ipi_handler)
{
#if BOARD_CONFIG_QSD8250_LEO
    /* Bind the actual already bootstrapped single Scorpion master to IOKit.
     * No secondary CPU, allocation, synthetic processor or IPI implementation. */
    cpu_data_t *data = current_cpu_datap();
    if (!cpu_id || !processor_out || !ipi_handler || !data ||
        cpu_number() != master_cpu || master_cpu != 0 ||
        master_processor == PROCESSOR_NULL ||
        data->cpu_processor != master_processor)
        return KERN_INVALID_ARGUMENT;
    if (data->cpu_id && data->cpu_id != cpu_id)
        return KERN_FAILURE;
    data->cpu_id = cpu_id;
    *processor_out = master_processor;
    *ipi_handler = NULL; /* UP has no supported target-IPI transport. */
#endif
    return KERN_SUCCESS;
}

/*
 * Stubbed.
 */
void ml_thread_policy(__unused thread_t thread, __unused unsigned policy_id,
                      __unused unsigned policy_info)
{

}

int ml_get_max_affinity_sets(void)
{
    return 1;
}

processor_set_t ml_affinity_to_pset(uint32_t affinity_num)
{
    return processor_pset(master_processor);
}

vm_offset_t ml_static_ptovirt(vm_offset_t paddr)
{
    return phys_to_virt(paddr);
}

void ml_get_power_state(boolean_t * icp, boolean_t * pidlep)
{
    *pidlep = FALSE;
}

void machine_track_platform_idle(boolean_t entry)
{
    return;
}

void ml_static_mfree(vm_offset_t vaddr, vm_size_t size)
{
    addr64_t vaddr_cur;
    ppnum_t ppn;
    uint32_t freed_pages = 0;
    assert(vaddr >= VM_MIN_KERNEL_ADDRESS);

    assert((vaddr & (PAGE_SIZE-1)) == 0); /* must be page aligned */

    /* Disconnect all mappings for the pages. */
    for (vaddr_cur = vaddr;
         vaddr_cur < round_page_64(vaddr+size);
         vaddr_cur += PAGE_SIZE) {
        ppn = pmap_find_phys(kernel_pmap, vaddr_cur);
        if (ppn != (vm_offset_t)NULL) {
#if !BOARD_CONFIG_QSD8250_LEO
                kernel_pmap->pm_stats.resident_count++;
            if (kernel_pmap->pm_stats.resident_count >
                kernel_pmap->pm_stats.resident_max) {
                kernel_pmap->pm_stats.resident_max =
                    kernel_pmap->pm_stats.resident_count;
            }
#endif
            pmap_remove(kernel_pmap, vaddr_cur, vaddr_cur+PAGE_SIZE);
            freed_pages++;
        }
    }

#if DEBUG
    kprintf("ml_static_mfree: Released 0x%x pages at VA %p, size:0x%llx, last ppn: 0x%x\n", freed_pages, (void *)vaddr, (uint64_t)size, ppn);
#endif
}

/*
 *	kvtophys(addr)
 *
 *	Convert a kernel virtual address to a physical address
 */
addr64_t kvtophys(vm_offset_t addr)
{
    pmap_paddr_t pa;
    pa = ((pmap_paddr_t) pmap_extract(kernel_pmap, addr));
    return (addr64_t) pa;
}

/*
 *	Routine:        ml_nofault_copy
 *	Function:	Perform a physical mode copy if the source and
 *			destination have valid translations in the kernel pmap.
 *			If translations are present, they are assumed to
 *			be wired; i.e. no attempt is made to guarantee that the
 *			translations obtained remained valid for
 *			the duration of the copy process.
 */

vm_size_t ml_nofault_copy(vm_offset_t virtsrc, vm_offset_t virtdst, vm_size_t size)
{
    addr64_t cur_phys_dst, cur_phys_src;
    uint32_t count, nbytes = 0;

    while (size > 0) {
        if (!(cur_phys_src = kvtophys(virtsrc)))
            break;
        if (!(cur_phys_dst = kvtophys(virtdst)))
            break;
        if (!pmap_valid_page(atop(cur_phys_dst))
            || !pmap_valid_page(atop(cur_phys_src)))
            break;
        count = (uint32_t) (PAGE_SIZE - (cur_phys_src & PAGE_MASK));
        if (count > (PAGE_SIZE - (cur_phys_dst & PAGE_MASK)))
            count = (uint32_t) (PAGE_SIZE - (cur_phys_dst & PAGE_MASK));
        if (count > size)
            count = (uint32_t) size;

        bcopy_phys(cur_phys_src, cur_phys_dst, count);

        nbytes += count;
        virtsrc += count;
        virtdst += count;
        size -= count;
    }

    return nbytes;
}

boolean_t ml_thread_is64bit(thread_t thread)
{
    return FALSE;
}

/*
 *  Routine:        ml_cpu_get_info
 *  Function:
 */
extern int arm_pdcache_line_size, arm_pdcache_size, arm_picache_size;

void ml_cpu_get_info(ml_cpu_info_t * ml_cpu_info)
{
    if (ml_cpu_info == 0)
        return;

    ml_cpu_info->vector_unit = 1;

    ml_cpu_info->cache_line_size = arm_processor_id.cache_levels[0].linesize;

    ml_cpu_info->l1_icache_size = arm_processor_id.cache_levels[0].size;
    ml_cpu_info->l1_dcache_size = arm_processor_id.cache_levels[0].size;

    ml_cpu_info->l2_settings = (arm_processor_id.cache_levels[1].size > 0) ? 1 : 0;
    ml_cpu_info->l2_cache_size = (arm_processor_id.cache_levels[1].size > 0) ? arm_processor_id.cache_levels[1].size : 0xFFFFFFFF;

    ml_cpu_info->l3_settings = 0;
    ml_cpu_info->l3_cache_size = 0xFFFFFFFF;

    return;
}

boolean_t ml_delay_should_spin(uint64_t interval)
{
#if defined(BOARD_CONFIG_EXYNOS4210_I9100)
    return i9100_delay_should_spin(interval) ? TRUE : FALSE;
#else
    return FALSE;
#endif
}

/*
 * Not right now.
 */
boolean_t ml_at_interrupt_context(void)
{
    boolean_t ret;
    cpu_data_t* datap = current_cpu_datap();
    assert(datap);

    ret = (datap->cpu_interrupt_level) ? TRUE : FALSE;

    return(ret);
}

/**
 * ml_cpu_cache_sharing
 */
uint64_t ml_cpu_cache_sharing(unsigned int level)
{
    return 1;
}

/*
 * ml_phys_read_*.
 */

#define ml_phys_read_write_comb_gen(ret, cast, type, suffix)        \
    ret ml_phys_read ##suffix (type paddr) {                        \
        return (ret)(*(cast*)(phys_to_virt(paddr)));                \
    }                                                               \
    void ml_phys_write ##suffix (type paddr, ret data) {            \
        (*(volatile cast*)(phys_to_virt(paddr))) = (cast)data;      \
    }

ml_phys_read_write_comb_gen(unsigned int, unsigned char, vm_offset_t, _byte)
ml_phys_read_write_comb_gen(unsigned int, unsigned char, addr64_t, _byte_64)

ml_phys_read_write_comb_gen(unsigned int, unsigned short, vm_offset_t, _half)
ml_phys_read_write_comb_gen(unsigned int, unsigned short, addr64_t, _half_64)

ml_phys_read_write_comb_gen(unsigned int, unsigned int, vm_offset_t,)
ml_phys_read_write_comb_gen(unsigned int, unsigned int, addr64_t, _64)
ml_phys_read_write_comb_gen(unsigned int, unsigned int, vm_offset_t, _word)
ml_phys_read_write_comb_gen(unsigned int, unsigned int, addr64_t, _word_64)

ml_phys_read_write_comb_gen(unsigned long long, unsigned long long, vm_offset_t, _double) 
ml_phys_read_write_comb_gen(unsigned long long, unsigned long long, addr64_t, _double_64)
