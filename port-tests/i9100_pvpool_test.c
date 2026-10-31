#include <stdint.h>
#include <stddef.h>
typedef unsigned int u_int;typedef uint32_t vm_map_offset_t,ppnum_t;typedef int boolean_t;
typedef void *pmap_t;static pmap_t kernel_pmap=(void*)1;static int pmap_initialized;
typedef struct q{struct q *next,*prev;}queue_head_t;typedef queue_head_t *queue_entry_t;
typedef void *thread_call_t;typedef int thread_call_data_t;
#define decl_simple_lock_data(a,b) int b;
static int locks,queued,in_zone,expect_exhaustion;
static unsigned zone_count,held_count;
static void semihost(uint32_t op,const void*p){register uint32_t r0 __asm__("r0")=op;register const void*r1 __asm__("r1")=p;__asm__ volatile("svc 0x123456":"+r"(r0):"r"(r1):"memory");}
static void __attribute__((noreturn)) finish(uint32_t c){uint32_t v[2]={0x20026,c};semihost(0x20,v);for(;;){}}
#define CHECK(x) do{if(!(x)){semihost(4,"FAIL: " #x "\n");finish(1);}}while(0)
static int same(const char*a,const char*b){while(*a&&*a==*b){a++;b++;}return *a==*b;}
static void __attribute__((noreturn)) test_panic(const char *s){
 CHECK(same(s,"pmap mapping PV reserve exhausted"));CHECK(!locks);
#if TEST_OLD
 CHECK(!zone_count && !held_count && !queued);
 semihost(4,"CONTROL: WIRE14 actual empty free lists panic on the first kernel PV request, before any zone allocation\n");finish(0);
#else
 CHECK(expect_exhaustion && !in_zone);
 semihost(4,"ARM PV startup: empty lists seeded before publication; kernel mapping before priming; real 10050-node prime with recursive zone-page metadata; NULL-callout guard, recycling, coalescing and explicit exhaustion passed\n");finish(0);
#endif
}
#define panic(fmt,...) test_panic(fmt)
static void simple_lock(int *l){CHECK(!*l);*l=1;locks++;}
static void simple_unlock(int *l){CHECK(*l);*l=0;locks--;}
static int hw_compare_and_store(u_int old,u_int n,u_int *p){if(*p!=old)return 0;*p=n;return 1;}
static void thread_call_enter(thread_call_t p){CHECK(p!=NULL);queued++;}
static void *pv_hashed_list_zone;static void *zalloc(void *p);
#include "pvpool-under-test.inc"
#if !TEST_OLD
static struct pv_hashed_entry zone_nodes[5*PV_HASHED_ALLOC_CHUNK+PV_HASHED_KERN_ALLOC_CHUNK];
static pv_hashed_entry_t held[20000],unique[32768];
static pv_hashed_entry_t take(void){
 pv_hashed_entry_t spare=0,p=leo_node_get(kernel_pmap,&spare);CHECK(p && held_count<20000);
 unsigned slot=((uintptr_t)p>>2)&32767;
 while(unique[slot]){CHECK(unique[slot]!=p);slot=(slot+1)&32767;}
 unique[slot]=p;held[held_count++]=p;return p;
}
#endif
static void *zalloc(void *p){
 (void)p;CHECK(!locks && !in_zone);in_zone=1;
#if TEST_OLD
 CHECK(0);return 0;
#else
 CHECK(zone_count<sizeof(zone_nodes)/sizeof(zone_nodes[0]));
 // Model a zone backing-page allocation needing another kernel mapping alias.
 if(!(zone_count%(4096/sizeof(struct pv_hashed_entry))))take();
 void *node=&zone_nodes[zone_count++];in_zone=0;return node;
#endif
}
void run(void){
#if TEST_OLD
 pv_hashed_entry_t spare=0;pmap_initialized=1;leo_node_get(kernel_pmap,&spare);CHECK(0);
#else
 CHECK(!pv_hashed_free_list&&!pv_hashed_kern_free_list&&!mapping_adjust_call);
 i9100_pv_bootstrap_seed();CHECK(pv_hashed_kern_free_count==I9100_PV_BOOTSTRAP_NODES);
 pmap_initialized=1;take();CHECK(!zone_count&&!queued&&!mappingrecurse);
 mapping_free_prime();CHECK(zone_count==10050 && !in_zone && !queued && !mappingrecurse);
 CHECK(pv_hashed_free_count==10000);
 while(pv_hashed_free_list||pv_hashed_kern_free_list)take();
 CHECK(held_count==I9100_PV_BOOTSTRAP_NODES+zone_count);
 CHECK(!pv_hashed_free_count&&!pv_hashed_kern_free_count&&!queued&&!mappingrecurse);
 // Refill one node: low-water notification becomes legal only after callout setup.
 pv_hashed_entry_t p=held[0],spare=0;mapping_adjust_call=&mapping_adjust_call_data;
 PV_HASHED_FREE_LIST(p,p,1);CHECK(leo_node_get(kernel_pmap,&spare)==p);CHECK(queued==1&&mappingrecurse==1);
 PV_HASHED_FREE_LIST(p,p,1);CHECK(leo_node_get(kernel_pmap,&spare)==p);CHECK(queued==1);
 mappingrecurse=0;PV_HASHED_FREE_LIST(p,p,1);CHECK(leo_node_get(kernel_pmap,&spare)==p);CHECK(queued==2);
 for(unsigned n=0;n<held_count;n++){p=held[n];PV_HASHED_FREE_LIST(p,p,1);}
 CHECK(pv_hashed_free_count==(int)held_count);
 for(unsigned n=0;n<held_count;n++){p=leo_node_get(kernel_pmap,&spare);CHECK(p);}
 CHECK(!pv_hashed_free_list&&!pv_hashed_kern_free_list&&!pv_hashed_free_count);
 expect_exhaustion=1;leo_node_get(kernel_pmap,&spare);CHECK(0);
#endif
}
