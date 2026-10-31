#ifndef I9100_TOUCH_OBSERVATION_H
#define I9100_TOUCH_OBSERVATION_H
#include <stdint.h>
typedef struct I9100TouchObservation {
 uint32_t ready,init_result,stage,opened,polls,reports,enqueued,head,tail,errors;
} I9100TouchObservation;
#ifdef __cplusplus
extern "C" {
#endif
extern volatile I9100TouchObservation i9100_touch_observation;
#ifdef __cplusplus
}
#endif
/* Individual scalar RAM reads only. No MMIO, allocation, queue consumption or
 * locks in the display/timer reader. Counters/cursors show their low16 bits.
 * These values localize progress; they do not prove BackBoard accepted input. */
static inline void i9100_touch_status_text(char line[64])
{
 const char *pattern="TCH R0 I00000000 S0 O0 P0000 N0000 Q0000 H0000 T0000 E0000";
 unsigned n;for(n=0;pattern[n];n++)line[n]=pattern[n];line[n]=0;
 line[5]=i9100_touch_observation.ready?'1':'0';
 line[18]="0123456789abcdef"[i9100_touch_observation.stage&15U];
 line[21]=i9100_touch_observation.opened?'1':'0';
 uint32_t initial=i9100_touch_observation.init_result;
 for(n=0;n<8;n++)line[8+n]="0123456789abcdef"[(initial>>((7U-n)*4))&15U];
 uint32_t values[6];
 values[0]=i9100_touch_observation.polls;values[1]=i9100_touch_observation.reports;
 values[2]=i9100_touch_observation.enqueued;values[3]=i9100_touch_observation.head;
 values[4]=i9100_touch_observation.tail;values[5]=i9100_touch_observation.errors;
 for(unsigned field=0;field<6;field++)for(n=0;n<4;n++)
  line[24+field*6+n]="0123456789abcdef"[(values[field]>>((3U-n)*4))&15U];
}
#endif
