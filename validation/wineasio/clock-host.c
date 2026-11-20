#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <objbase.h>
#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>

enum { PERIOD = 1024, OBSERVATIONS = 8, SUPPORTS_TIME_INFO = 7 };

typedef struct {
    ULONG hi, lo;
} AsioWords;

typedef struct {
    LONG input, channel;
    void *buffers[2];
} AsioBuffer;

typedef struct {
    LONG reserved[4];
    double speed;
    AsioWords timestamp, position;
    double rate;
    ULONG flags;
} AsioTime;

typedef struct {
    void (CALLBACK *swap)(LONG, LONG);
    void (CALLBACK *rate_changed)(double);
    LONG (CALLBACK *message)(LONG, LONG, void *, double *);
    void *(CALLBACK *swap_with_time)(AsioTime *, LONG, LONG);
} AsioCallbacks;

typedef struct Driver Driver;
typedef void (WINAPI *UnusedMethod)(void);

struct Driver {
    const struct {
        UnusedMethod query_interface, add_ref;
        ULONG (WINAPI *release)(Driver *);
        LONG (WINAPI *init)(Driver *, void *);
        UnusedMethod name, version, error_message;
        LONG (WINAPI *start)(Driver *);
        LONG (WINAPI *stop)(Driver *);
        UnusedMethod channels, latencies, buffer_size, can_sample_rate;
        LONG (WINAPI *sample_rate)(Driver *, double *);
        UnusedMethod set_sample_rate, clock_sources, set_clock_source;
        LONG (WINAPI *position)(Driver *, AsioWords *, AsioWords *);
        UnusedMethod channel_info;
        LONG (WINAPI *create_buffers)(Driver *, AsioBuffer *, LONG, LONG, AsioCallbacks *);
        LONG (WINAPI *dispose_buffers)(Driver *);
    } *methods;
};

static Driver *driver;
static HANDLE complete;
static LONG time_info_mode;
static LONG written;
static struct {
    uint64_t getter, notification;
    LONG result;
    int has_notification;
} observations[OBSERVATIONS];

static uint64_t decode(AsioWords words)
{
    return ((uint64_t)words.hi << 32) | words.lo;
}

static void observe(const AsioTime *time)
{
    LONG index = InterlockedIncrement(&written) - 1;
    if (index >= OBSERVATIONS)
        return;
    AsioWords position = {0}, timestamp = {0};
    observations[index].result = driver->methods->position(driver, &position, &timestamp);
    observations[index].getter = decode(position);
    observations[index].has_notification = time != NULL;
    observations[index].notification = time ? decode(time->position) : 0;
    if (index == OBSERVATIONS - 1)
        SetEvent(complete);
}

static void CALLBACK swap(LONG buffer, LONG process_now)
{
    (void)buffer;
    (void)process_now;
    observe(NULL);
}

static void *CALLBACK swap_with_time(AsioTime *time, LONG buffer, LONG process_now)
{
    (void)buffer;
    (void)process_now;
    observe(time);
    return NULL;
}

static void CALLBACK rate_changed(double rate)
{
    (void)rate;
}

static LONG CALLBACK message(LONG selector, LONG value, void *data, double *options)
{
    (void)value;
    (void)data;
    (void)options;
    return selector == SUPPORTS_TIME_INFO ? time_info_mode : 0;
}

static int run_cycle(const char *seed_text, uint64_t seed)
{
    if (!SetEnvironmentVariableA("WAYDAW_TEST_ASIO_START_POSITION", seed_text) ||
        !ResetEvent(complete))
        return 1;
    InterlockedExchange(&written, 0);
    if (driver->methods->start(driver) != 0) {
        fprintf(stderr, "Start failed\n");
        return 1;
    }
    DWORD wait = WaitForSingleObject(complete, 4000);
    LONG stop = driver->methods->stop(driver);
    if (wait != WAIT_OBJECT_0 || stop != 0) {
        fprintf(stderr, "Callback wait/Stop failed: %lu/%ld\n", wait, stop);
        return 1;
    }
    int wrong = 0;
    for (unsigned int i = 0; i < OBSERVATIONS; i++) {
        uint64_t expected = seed + i * PERIOD;
        printf("%s,%u,%" PRIu64 ",%" PRIu64 ",%" PRIu64 ",%d,%ld\n",
               seed_text ? seed_text : "restart", i, expected, observations[i].getter,
               observations[i].notification, observations[i].has_notification, observations[i].result);
        if (observations[i].result || observations[i].getter != expected ||
            observations[i].has_notification != time_info_mode ||
            (time_info_mode && observations[i].notification != expected))
            wrong = 1;
    }
    return wrong ? 2 : 0;
}

int main(int argc, char **argv)
{
    if (argc != 3 ||
        (strcmp(argv[1], "basic") && strcmp(argv[1], "time")) ||
        (strcmp(argv[2], "0") && strcmp(argv[2], "2147481600") && strcmp(argv[2], "4294965248"))) {
        fprintf(stderr, "usage: wineasio-clock-host basic|time 0|2147481600|4294965248\n");
        return 1;
    }
    const CLSID id = {0x48d0c522, 0xbfcc, 0x45cc, {0x8b, 0x84, 0x17, 0xf2, 0x5f, 0x33, 0xe6, 0xe8}};
    if (FAILED(CoInitializeEx(NULL, COINIT_APARTMENTTHREADED)))
        return 1;
    HRESULT result = CoCreateInstance(&id, NULL, CLSCTX_INPROC_SERVER, &id, (void **)&driver);
    if (FAILED(result)) {
        fprintf(stderr, "Driver creation failed: %08lx\n", (unsigned long)result);
        CoUninitialize();
        return 1;
    }
    time_info_mode = strcmp(argv[1], "time") == 0;
    complete = CreateEventW(NULL, TRUE, FALSE, NULL);
    AsioBuffer buffer = {0};
    AsioCallbacks callbacks = {swap, rate_changed, message, swap_with_time};
    double rate;
    int outcome = 1;
    if (complete && driver->methods->init(driver, NULL) &&
        driver->methods->sample_rate(driver, &rate) == 0 && rate == 48000.0 &&
        driver->methods->create_buffers(driver, &buffer, 1, PERIOD, &callbacks) == 0) {
        /* Recreate the driver in each process. A replay within the same prepared driver
         * verifies that a new Start resets the sample position. */
        puts("seed,callback,expected,getter,notification,has_notification,result");
        int boundary = run_cycle(argv[2], strtoull(argv[2], NULL, 10));
        int restart = boundary == 1 ? 1 : run_cycle(NULL, 0);
        if (driver->methods->dispose_buffers(driver) == 0)
            outcome = boundary == 1 || restart != 0 ? 1 : boundary;
    } else {
        fprintf(stderr, "Driver setup failed (expected a private 48000 Hz clock)\n");
    }
    driver->methods->release(driver);
    if (complete)
        CloseHandle(complete);
    CoUninitialize();
    return outcome;
}
