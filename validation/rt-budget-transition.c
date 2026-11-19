#define _GNU_SOURCE
#include <errno.h>
#include <sched.h>
#include <stdio.h>
#include <string.h>
#include <sys/resource.h>
#include <sys/prctl.h>
#include <sys/syscall.h>
#include <time.h>
#include <unistd.h>

/* Disposable child only. The separate driver grants RR9 after each ready line. */
static unsigned long long clock_ns(clockid_t clock_id)
{
    struct timespec value;
    if (clock_gettime(clock_id, &value))
        _exit(10);
    return (unsigned long long)value.tv_sec * 1000000000ULL + value.tv_nsec;
}

static void pause_for_200ms(void)
{
    struct timespec delay = {0, 200000000};
    while (nanosleep(&delay, &delay) && errno == EINTR) {}
}

int main(int argc, char **argv)
{
    if (argc != 3 ||
        (strcmp(argv[1], "rr-block") && strcmp(argv[1], "ordinary-block")) ||
        (strcmp(argv[2], "waiting") && strcmp(argv[2], "running")))
        return 2;

    const int block_while_rt = !strcmp(argv[1], "rr-block");
    const int wait_for_command = !strcmp(argv[2], "waiting");
    const struct rlimit limit = {200000, 200000};
    if (setrlimit(RLIMIT_RTTIME, &limit) ||
        prctl(PR_SET_NAME, "waydaw-rt-test", 0, 0, 0))
        return 3;
    setvbuf(stdout, NULL, _IOLBF, 0);

    for (int cycle = 0; cycle < 9; ++cycle) {
        printf("ready %d %d %ld %llu\n", cycle, getpid(),
               syscall(SYS_gettid), clock_ns(CLOCK_THREAD_CPUTIME_ID));

        if (wait_for_command) {
            char command;
            if (read(STDIN_FILENO, &command, 1) != 1 || command != 'g')
                return 4;
        } else {
            const unsigned long long deadline = clock_ns(CLOCK_MONOTONIC) + 2000000000ULL;
            while (sched_getscheduler(0) != (SCHED_RR | SCHED_RESET_ON_FORK)) {
                if (clock_ns(CLOCK_MONOTONIC) > deadline)
                    return 4;
            }
        }

        struct sched_param priority;
        if (sched_getscheduler(0) != (SCHED_RR | SCHED_RESET_ON_FORK) ||
            sched_getparam(0, &priority) || priority.sched_priority != 9)
            return 5;

        const unsigned long long start = clock_ns(CLOCK_THREAD_CPUTIME_ID);
        while (clock_ns(CLOCK_THREAD_CPUTIME_ID) - start < 35000000ULL)
            __asm__ volatile("" ::: "memory");
        printf("busy_complete %d %llu %llu\n", cycle, start,
               clock_ns(CLOCK_THREAD_CPUTIME_ID));

        if (block_while_rt)
            pause_for_200ms();
        const struct sched_param ordinary = {0};
        if (sched_setscheduler(0, SCHED_OTHER | SCHED_RESET_ON_FORK, &ordinary))
            return 6;
        if (!block_while_rt)
            pause_for_200ms();
    }
    return 0;
}
