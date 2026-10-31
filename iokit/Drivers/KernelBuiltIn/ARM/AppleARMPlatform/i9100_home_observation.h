#ifndef I9100_HOME_OBSERVATION_H
#define I9100_HOME_OBSERVATION_H
#include <stdint.h>
typedef struct I9100HomeObservation {
 uint32_t enabled,down,opened,edges,enqueued,head,tail;
} I9100HomeObservation;
#ifdef __cplusplus
extern "C" {
#endif
extern volatile I9100HomeObservation i9100_home_observation;
#ifdef __cplusplus
}
#endif
/* Diagnostic only: individual RAM reads, no MMIO, locks or allocation in IRQ.
 * Q is successful Home enqueue, H/T are Home queue cursors. Neither proves
 * BackBoard accepted an event. At least 46 bytes are required for line. */
static inline void i9100_home_status_text(char line[46])
{
 const char *pattern="HOME E0 P0 O0 D00000000 Q00000000 H0000 T0000";
 unsigned n;for(n=0;pattern[n];n++)line[n]=pattern[n];line[n]=0;
 line[6]=i9100_home_observation.enabled?'1':'0';
 line[9]=i9100_home_observation.down?'1':'0';
 line[12]=i9100_home_observation.opened?'1':'0';
 uint32_t edges=i9100_home_observation.edges,sent=i9100_home_observation.enqueued;
 uint32_t head=i9100_home_observation.head,tail=i9100_home_observation.tail;
 for(n=0;n<8;n++){
  line[15+n]="0123456789abcdef"[(edges>>((7U-n)*4))&15U];
  line[25+n]="0123456789abcdef"[(sent>>((7U-n)*4))&15U];
 }
 for(n=0;n<4;n++){
  line[35+n]="0123456789abcdef"[(head>>((3U-n)*4))&15U];
  line[41+n]="0123456789abcdef"[(tail>>((3U-n)*4))&15U];
 }
}
#endif
