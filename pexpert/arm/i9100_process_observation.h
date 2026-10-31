/* Rare SpringBoard exit observations. Scalars only; no hot-path tracing. */
#ifndef I9100_PROCESS_OBSERVATION_H
#define I9100_PROCESS_OBSERVATION_H
struct I9100ProcessExit {
    unsigned sequence, pid, signal, exit_code, exception_known;
    unsigned exception, code, subcode, free_pages;
};
extern volatile struct I9100ProcessExit i9100_process_exit;
extern volatile struct I9100ProcessExit i9100_backboard_exit;
void ios7i9100_process_exit(unsigned, unsigned, unsigned, unsigned,
    unsigned, unsigned, unsigned, unsigned, unsigned, unsigned);

struct I9100SignalRequest {
    unsigned sequence, pid, task, signal, context_pid;
    unsigned pc, lr, caller_pc, irq, flavor;
    char context_name[17];
};
extern volatile struct I9100SignalRequest i9100_signal_pending[3], i9100_signal_exit;
void ios7i9100_signal_request(unsigned, unsigned, unsigned, unsigned,
    const char *, unsigned, unsigned, unsigned, unsigned, unsigned);

static void i9100_signal_publish(volatile struct I9100SignalRequest *out,
    unsigned pid, unsigned task, unsigned signal, unsigned context_pid,
    const char *name, unsigned pc, unsigned lr, unsigned caller_pc,
    unsigned irq, unsigned flavor)
{
    unsigned next = out->sequence + 1U;
    out->sequence = 0;
    out->pid = pid; out->task = task; out->signal = signal;
    out->context_pid = context_pid;
    out->pc = pc; out->lr = lr; out->caller_pc = caller_pc;
    out->irq = irq; out->flavor = flavor;
    unsigned n = 0;
    for (; n < sizeof(out->context_name)-1 && name[n]; n++)
        out->context_name[n] = name[n];
    for (; n < sizeof(out->context_name); n++) out->context_name[n] = 0;
    out->sequence = next ? next : 1U;
}

/* Latch only the exiting task's matching signal request. A later respawn must
 * not overwrite the displayed origin. A request is still not a delivery proof. */
static void i9100_signal_latch(unsigned pid, unsigned task, unsigned signal)
{
    volatile struct I9100SignalRequest *in = &i9100_signal_pending[signal == 9 ? 1 : signal == 6 ? 2 : 0];
    i9100_signal_exit.sequence = 0;
    if (in->sequence && in->pid == pid && in->task == task) {
        if (signal && in->signal == signal) {
            char name[17];
            for (unsigned n = 0; n < sizeof(name); n++) name[n] = in->context_name[n];
            i9100_signal_publish(&i9100_signal_exit, pid, task, signal,
                in->context_pid, name, in->pc, in->lr, in->caller_pc,
                in->irq, in->flavor);
        }
    }
    for (unsigned n = 0; n < 3; n++)
        if (i9100_signal_pending[n].pid == pid && i9100_signal_pending[n].task == task)
            i9100_signal_pending[n].sequence = 0;
}

static void i9100_process_publish(volatile struct I9100ProcessExit *out,
    unsigned pid, unsigned signal, unsigned exit_code, unsigned known,
    unsigned exception, unsigned code, unsigned subcode, unsigned free_pages)
{
    unsigned next = out->sequence + 1U;
    out->sequence = 0;
    out->pid = pid; out->signal = signal; out->exit_code = exit_code;
    out->exception_known = known;
    out->exception = known ? exception : 0;
    out->code = known ? code : 0; out->subcode = known ? subcode : 0;
    out->free_pages = free_pages;
    out->sequence = next ? next : 1U;
}

/* The caller serializes with the short publisher or runs in timer IRQ. */
static int i9100_process_text(char *first, char *second, unsigned capacity)
{
    unsigned sequence = i9100_process_exit.sequence;
    if (!sequence) return 0;
    unsigned pid = i9100_process_exit.pid, signal = i9100_process_exit.signal;
    unsigned exit_code = i9100_process_exit.exit_code;
    unsigned known = i9100_process_exit.exception_known;
    unsigned exception = i9100_process_exit.exception, code = i9100_process_exit.code;
    unsigned subcode = i9100_process_exit.subcode, free_pages = i9100_process_exit.free_pages;
    if (sequence != i9100_process_exit.sequence) return 0;
    snprintf(first, capacity, "SBEXIT #%u PID%u SIG%u EXIT%u X%u",
        sequence, pid, signal, exit_code, known);
    snprintf(second, capacity, "EXC%u CODE%08x SUB%08x FREE%u",
        exception, code, subcode, free_pages);
    return 1;
}

static int i9100_signal_text(char *first, char *second, unsigned capacity)
{
    unsigned sequence = i9100_signal_exit.sequence;
    if (!i9100_process_exit.sequence) return 0;
    if (!sequence) {
        snprintf(first, capacity, "SBREQ unavailable (no matching signal request)");
        snprintf(second, capacity, "");
        return 1;
    }
    char name[17];
    for (unsigned n = 0; n < sizeof(name); n++) name[n] = i9100_signal_exit.context_name[n];
    name[16] = 0;
    unsigned signal = i9100_signal_exit.signal, pid = i9100_signal_exit.context_pid;
    unsigned irq = i9100_signal_exit.irq, flavor = i9100_signal_exit.flavor;
    unsigned pc = i9100_signal_exit.pc, lr = i9100_signal_exit.lr;
    unsigned caller = i9100_signal_exit.caller_pc;
    if (sequence != i9100_signal_exit.sequence) return 0;
    snprintf(first, capacity, "SBREQ SIG%u CTX%u:%.16s IRQ%u F%u", signal, pid, name, irq, flavor);
    snprintf(second, capacity, "K%08x U%08x LR%08x", caller, pc, lr);
    return 1;
}

static int i9100_backboard_text(char *first, char *second, unsigned capacity)
{
    unsigned sequence = i9100_backboard_exit.sequence;
    if (!sequence) return 0;
    unsigned pid = i9100_backboard_exit.pid, signal = i9100_backboard_exit.signal;
    unsigned code = i9100_backboard_exit.code, subcode = i9100_backboard_exit.subcode;
    unsigned known = i9100_backboard_exit.exception_known;
    unsigned exception = i9100_backboard_exit.exception, free_pages = i9100_backboard_exit.free_pages;
    if (sequence != i9100_backboard_exit.sequence) return 0;
    snprintf(first, capacity, "BBEXIT #%u PID%u SIG%u X%u EXC%u", sequence, pid, signal, known, exception);
    snprintf(second, capacity, "CODE%08x SUB%08x FREE%u", code, subcode, free_pages);
    return 1;
}
#endif
