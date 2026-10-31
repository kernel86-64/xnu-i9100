#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include "i9100_cache_policy.h"
#define BOARD_CONFIG_EXYNOS4210_I9100 1
#define PAGE_SHIFT 12
#define PAGE_SIZE 4096U
#define L2_ADDR_MASK 0xfffff000U
#define ARM_L2_C_BIT 4U
#define PMAP_OSPTE_TYPE_NOCACHE 0x10U
#define VM_MEM_NOT_CACHEABLE 4U
#define VM_MEM_WRITE_THROUGH 8U
#define VM_WIMG_IO 7U
#define VM_WIMG_COPYBACK 2U
#define FALSE 0
#define TRUE 1
#define PMAP_NULL NULL
typedef uint32_t ppnum_t, pt_entry_t, vm_offset_t, vm_map_offset_t;
typedef int boolean_t;
struct mock_map { pt_entry_t direct, alias; };
typedef struct mock_map *pmap_t;
struct pv { pmap_t pmap; uint32_t va, flags; struct { struct pv *next; } qlink; };
typedef struct pv *pv_rooted_entry_t, *pv_hashed_entry_t;
#define queue_next(q) ((q)->next)
static struct mock_map kernel, user;
static pmap_t kernel_pmap = &kernel;
static struct pv root_pv, alias_pv;
static int pmap_initialized, preemption, drains, flushes, breaks, makes;
static pt_entry_t *cleaned;
static uint32_t avail_start = 0x41000000U, avail_end = 0x80000000U;
static uint32_t first_avail, avail_remaining;
uint32_t i9100_ram_start = 0x40000000U, i9100_ram_bytes = 0x40000000U;
uint32_t i9100_scanout_start = 0x43e00000U, i9100_scanout_end = 0x44000000U;
#define PN (0x42001000U >> PAGE_SHIFT)
#define DIRECT_VA 0x82001000U
#define USER_VA 0x00100000U
#define ALIAS_VA 0xc0010000U
#define pa_index(pa) ((pa) >> PAGE_SHIFT)
#define LOCK_PVH(pn) do { (void)(pn); ++preemption; } while (0)
#define UNLOCK_PVH(pn) do { (void)(pn); assert(preemption > 0); --preemption; } while (0)
#define kprintf(...) ((void)0)
#define panic(...) abort()
static uint32_t phys_to_virt(uint32_t pa) { return pa + 0x40000000U; }
static struct pv *pai_to_pvh(ppnum_t pn) { assert(pn == PN); return &root_pv; }
static unsigned phys_attribute_test(ppnum_t pn, unsigned bits)
{ return pai_to_pvh(pn)->flags & bits; }
static void phys_attribute_set(ppnum_t pn, unsigned bits) { pai_to_pvh(pn)->flags |= bits; }
static void phys_attribute_clear(ppnum_t pn, unsigned bits) { pai_to_pvh(pn)->flags &= ~bits; }
static pt_entry_t *pmap_pte(pmap_t map, uint32_t va)
{
    if (map == &kernel && va == DIRECT_VA) return &kernel.direct;
    if (map == &kernel && va == ALIAS_VA) return &kernel.alias;
    assert(map == &user && va == USER_VA);
    return &user.alias;
}
static void pte_sync(pt_entry_t *pte) { cleaned = pte; }
static void pmap_flush_tlbs(pmap_t map, uint32_t start, uint32_t end)
{
    assert(end - start == PAGE_SIZE && drains && preemption);
    pt_entry_t *pte = pmap_pte(map, start);
    assert(cleaned == pte); /* Clean must precede invalidate. */
    cleaned = NULL;
    if (*pte == 0) ++breaks; else ++makes;
    ++flushes;
}
static void arm_dcache_wbinv_range(uint32_t va, uint32_t size)
{ assert(va == DIRECT_VA && size == PAGE_SIZE && preemption); ++drains; }
#include "pmap-under-test.inc"

static void policy_checks(void)
{
    /* Decode TEX/C/B independently: standard ARMv7 Normal WBWA is 001/11. */
    assert(((I9100_L2_NORMAL_WBWA >> 6) & 7) == 1);
    assert(((I9100_L2_NORMAL_WBWA >> 2) & 3) == 3);
    assert(((I9100_L2_NORMAL_NC >> 6) & 7) == 1);
    assert((I9100_L2_NORMAL_NC & 0xc) == 0);
    assert(!(I9100_L2_NORMAL_WBWA & (1U << 10))); /* Single CPU: S=0. */
    for (uint32_t pa = i9100_ram_start; pa < 0x80000000U; pa += PAGE_SIZE) {
        unsigned expected = pa >= i9100_scanout_start && pa < i9100_scanout_end ?
            I9100_L2_NORMAL_NC : I9100_L2_NORMAL_WBWA;
        assert(i9100_cache_policy(pa, 0) == expected);
        assert(i9100_cache_policy(pa, 1) == I9100_L2_NORMAL_NC);
    }
    const uint32_t devices[] = {0x10050000, 0x10480000, 0x10490000,
        0x11000000, 0x11400000, 0x11c00000, 0x12530000, 0x13820000, 0x80000000};
    for (unsigned i = 0; i < sizeof(devices) / sizeof(devices[0]); i++) {
        assert(i9100_cache_policy(devices[i], 0) == 0);
        assert(i9100_cache_policy(devices[i], 1) == 0);
        assert(pmap_get_cache_attributes(devices[i] >> PAGE_SHIFT) == 0);
    }
    assert(pmap_get_cache_attributes(PN) == I9100_L2_NORMAL_WBWA);
    assert(pmap_get_cache_attributes(i9100_scanout_start >> PAGE_SHIFT) == I9100_L2_NORMAL_NC);
    puts("Cache policy: all 262144 RAM pages, reserved scanout, MMIO and TEX/C/B decoding passed");
}

static void alias_checks(void)
{
    const uint32_t preserved = (PN << PAGE_SHIFT) | 0xa33U;
    kernel.direct = kernel.alias = user.alias = preserved | I9100_L2_NORMAL_WBWA;
    root_pv.pmap = &user; root_pv.va = USER_VA; root_pv.qlink.next = &alias_pv;
    alias_pv.pmap = &kernel; alias_pv.va = ALIAS_VA; alias_pv.qlink.next = &root_pv;
    pmap_initialized = TRUE;
    const unsigned requests[] = {4, 4, 0, 8, 2, 0x80, 6, 0};
    for (unsigned i = 0; i < sizeof(requests) / sizeof(requests[0]); i++) {
        unsigned attr = (requests[i] & 12) ? I9100_L2_NORMAL_NC : I9100_L2_NORMAL_WBWA;
        pmap_set_cache_attributes(PN, requests[i]);
        assert(kernel.direct == (preserved | attr));
        assert(kernel.alias == kernel.direct && user.alias == kernel.direct);
        assert(pmap_get_cache_attributes(PN) == attr && !preemption);
        assert(pmap_cache_attributes(PN) == (attr == I9100_L2_NORMAL_WBWA ? 2U : 7U));
    }
    assert(drains == 6 && breaks == 18 && makes == 18 && flushes == 36);
    /* MMIO and reserved scanout have no managed PV roots. */
    pmap_set_cache_attributes(0x12530000 >> PAGE_SHIFT, 2);
    pmap_set_cache_attributes(i9100_scanout_start >> PAGE_SHIFT, 2);
    assert(!preemption && drains == 6);
    puts("Actual pmap: default/WT/inhibit/reset, all three aliases, data drain and break/clean/TLBI/make ordering passed");
}

static void reservation_checks(void)
{
    first_avail = i9100_scanout_start - PAGE_SIZE;
    avail_end = i9100_scanout_end + PAGE_SIZE;
    reservation_count();
    assert(avail_remaining == 2);
    ppnum_t pn;
    assert(pmap_next_page(&pn) && pn == (i9100_scanout_start >> PAGE_SHIFT) - 1);
    assert(pmap_next_page(&pn) && pn == (i9100_scanout_end >> PAGE_SHIFT));
    assert(avail_remaining == 0 && !pmap_next_page(&pn));
    assert(!pmap_valid_page(i9100_scanout_start >> PAGE_SHIFT));
    assert(!pmap_valid_page((i9100_scanout_end - 1) >> PAGE_SHIFT));
    assert(pmap_valid_page((i9100_scanout_start - PAGE_SIZE) >> PAGE_SHIFT));
    first_avail = i9100_scanout_end;
    reservation_count(); assert(avail_remaining == 1);
    first_avail = i9100_scanout_start;
    avail_end = i9100_scanout_end;
    reservation_count(); assert(avail_remaining == 0);
    first_avail = i9100_scanout_start - PAGE_SIZE;
    avail_end = i9100_scanout_start + PAGE_SIZE;
    reservation_count(); assert(avail_remaining == 1);
    puts("Actual VM allocator: skips 2MiB live scanout without returning a framebuffer page");
}
int main(void) { policy_checks(); alias_checks(); reservation_checks(); return 0; }
