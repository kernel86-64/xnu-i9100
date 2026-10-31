/* SPDX-License-Identifier: GPL-2.0-only
 * GT-I9100 / Samsung U1 Atmel mXT224/mXT224E touch transport.
 * Board wiring and maXTouch protocol: Samsung's mxt224_u1.c / gpio-u1.h.
 */
#ifndef I9100_TOUCH_H
#define I9100_TOUCH_H
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
#define I9100_TOUCH_GPIO1_PA 0x11400000U
#define I9100_TOUCH_GPIO2_PA 0x11000000U
#define I9100_TOUCH_OBJECT_CAP 64U
#define I9100_TOUCH_INFO_BYTES (7U + I9100_TOUCH_OBJECT_CAP * 6U + 3U)
enum {
 I9100_TOUCH_OK=0, I9100_TOUCH_ARGUMENT=-1, I9100_TOUCH_NACK=-2,
 I9100_TOUCH_TIMEOUT=-3, I9100_TOUCH_BUS=-4, I9100_TOUCH_PROTOCOL=-5,
 I9100_TOUCH_CRC=-6, I9100_TOUCH_NOT_READY=-7
};
/* GPIO1: GPA1[2]=SDA, GPA1[3]=SCL. GPIO2: GPL0[3]=power, GPX0[4]=CHG.
 * Callbacks use aligned 32-bit MMIO offsets in two owned 4KiB mappings. */
struct i9100_touch_gpio_io {
 void *cookie;
 uint32_t (*read)(void *,uint32_t region,uint32_t offset);
 void (*write)(void *,uint32_t region,uint32_t offset,uint32_t value);
 int (*delay_us)(void *,uint32_t);
 uint32_t poll_bound;
 void (*enter_transfer)(void *);
 void (*leave_transfer)(void *);
};
struct i9100_touch_bus {
 struct i9100_touch_gpio_io io;
 uint32_t saved_a[3],saved_l[3],saved_x[2];
 uint32_t configured,transfers,recoveries;
 uint32_t last_phase,last_register;
 int last_error;
};
int i9100_touch_bus_init(struct i9100_touch_bus *,const struct i9100_touch_gpio_io *);
void i9100_touch_bus_fini(struct i9100_touch_bus *);
int i9100_touch_bus_read(void *,uint16_t,uint8_t *,uint32_t);
int i9100_touch_bus_write(void *,uint16_t,const uint8_t *,uint32_t);
int i9100_touch_bus_changed(void *);
/* Protocol callbacks return zero only for a full transfer. Poll and init are
 * serialized by the owning HID service; all work and messages are bounded. */
struct i9100_touch_io {
 void *cookie;
 int (*read)(void *,uint16_t,uint8_t *,uint32_t);
 int (*write)(void *,uint16_t,const uint8_t *,uint32_t);
 int (*changed)(void *);
};
struct i9100_touch_report {
 uint32_t sequence;
 uint16_t x,y;
 uint8_t down,contacts,raw[9];
};
struct i9100_touch_state {
 struct i9100_touch_io io;
 uint8_t info[I9100_TOUCH_INFO_BYTES];
 uint32_t ready,stage,id_word,errors,packets,polls,sequence,last_status;
 uint32_t active_mask,empty_messages,other_messages;
 uint16_t message_address,command_address,power_address,touch_address;
 uint16_t message_size,touch_size,x_max,y_max,last_x,last_y;
 uint8_t first_report,report_count,primary,orientation,x_drop,y_drop;
 uint8_t command_report,last_contacts;
 int last_result;
};
int i9100_touch_init(struct i9100_touch_state *,const struct i9100_touch_io *);
/* 1 = actual contact transition/motion, 0 = no report, negative = failure.
 * No timeout generates Up. Output is unchanged on no-data/errors. */
int i9100_touch_poll(struct i9100_touch_state *,struct i9100_touch_report *);
/* Decoder is shared by polling and host regression checks. */
int i9100_touch_decode(struct i9100_touch_state *,const uint8_t *,uint32_t,
                       struct i9100_touch_report *);
#ifdef __cplusplus
}
#endif
#endif
