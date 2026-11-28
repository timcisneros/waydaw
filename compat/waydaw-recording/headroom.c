/* Bind the verified PipeWire node before inspecting or changing headroom. */
#define _GNU_SOURCE
#include <dirent.h>
#include <errno.h>
#include <limits.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <unistd.h>

#include <pipewire/pipewire.h>
#include <spa/param/props.h>
#include <spa/pod/builder.h>
#include <spa/pod/iter.h>

#define ALSA_PATH "api.alsa.path"
#define HEADROOM "api.alsa.headroom"

enum stage { DISCOVER, BIND, READ, CONFIRM };
enum outcome { OK, FAILED, RETIRED, CONFLICT, BUSY, USAGE = 64 };

struct change {
    struct pw_main_loop *loop;
    struct pw_core *core;
    struct pw_registry *registry;
    struct pw_node *node;
    struct spa_hook core_hook, registry_hook, node_hook, proxy_hook;
    const char *serial, *name, *alsa_path;
    uint32_t node_id;
    pid_t server_pid;
    unsigned long long server_birth;
    enum stage stage;
    enum pw_node_state node_state;
    int sync, result;
    int32_t current, expected, target;
    bool found, info, value, write, finished;
};

static bool parse_number(const char *text, unsigned long long maximum,
                         unsigned long long *number)
{
    char *end;
    errno = 0;
    if (*text < '0' || *text > '9')
        return false;
    *number = strtoull(text, &end, 10);
    return errno == 0 && *end == '\0' && *number <= maximum;
}

static bool process_birth(pid_t pid, unsigned long long birth)
{
    char name[64], buffer[4096];
    snprintf(name, sizeof(name), "/proc/%ld/stat", (long)pid);
    FILE *file = fopen(name, "r");
    if (file == NULL)
        return false;
    bool read = fgets(buffer, sizeof(buffer), file) != NULL;
    fclose(file);
    char *comm = read ? strrchr(buffer, ')') : NULL;
    if (comm == NULL || comm[1] != ' ')
        return false;
    char *save = NULL;
    char *field = strtok_r(comm + 2, " ", &save);
    for (int index = 0; field != NULL && index < 19; ++index)
        field = strtok_r(NULL, " ", &save);
    unsigned long long actual;
    return field != NULL && parse_number(field, ULLONG_MAX, &actual) && actual == birth;
}


/* Socket activation makes SO_PEERCRED identify the listening systemd
 * manager. Check the socket listener held by the known daemon as well. */
static bool owns_listener(const char *socket_path, pid_t server)
{
    FILE *sockets = fopen("/proc/net/unix", "r");
    if (sockets == NULL)
        return false;
    char line[512];
    unsigned long long inode = 0;
    while (fgets(line, sizeof(line), sockets) != NULL) {
        unsigned flags, type, state;
        unsigned long long candidate;
        int path_offset = 0;
        int fields = sscanf(line, "%*s %*s %*s %x %x %x %llu %n",
                            &flags, &type, &state, &candidate, &path_offset);
        if (fields != 4 || path_offset == 0 || flags != 0x10000 ||
            type != SOCK_STREAM || state != 1)
            continue;
        line[strcspn(line, "\n")] = '\0';
        if (strcmp(line + path_offset, socket_path) == 0) {
            if (inode != 0) {
                inode = 0;
                break;
            }
            inode = candidate;
        }
    }
    fclose(sockets);
    if (inode == 0)
        return false;

    char proc_path[64], target[64], link[64];
    snprintf(proc_path, sizeof(proc_path), "/proc/%ld/fd", (long)server);
    snprintf(target, sizeof(target), "socket:[%llu]", inode);
    DIR *descriptors = opendir(proc_path);
    if (descriptors == NULL)
        return false;
    bool matches = false;
    struct dirent *entry;
    while ((entry = readdir(descriptors)) != NULL) {
        ssize_t length = readlinkat(dirfd(descriptors), entry->d_name, link, sizeof(link) - 1);
        if (length < 0)
            continue;
        link[length] = '\0';
        if (strcmp(target, link) == 0) {
            matches = true;
            break;
        }
    }
    closedir(descriptors);
    return matches;
}

static int connect_peer(const char *path, pid_t pid, unsigned long long birth)
{
    struct sockaddr_un address = { .sun_family = AF_UNIX };
    if (path[0] != '/' || strlen(path) >= sizeof(address.sun_path) ||
        !process_birth(pid, birth) || !owns_listener(path, pid))
        return -1;
    strcpy(address.sun_path, path);
    int fd = socket(AF_UNIX, SOCK_STREAM | SOCK_CLOEXEC, 0);
    if (fd < 0)
        return -1;
    struct ucred peer;
    socklen_t size = sizeof(peer);
    if (connect(fd, (const struct sockaddr *)&address, sizeof(address)) == 0 &&
        getsockopt(fd, SOL_SOCKET, SO_PEERCRED, &peer, &size) == 0 &&
        size == sizeof(peer) && peer.uid == getuid() &&
        process_birth(pid, birth) && owns_listener(path, pid))
        return fd;
    close(fd);
    return -1;
}

static void stop(struct change *data, enum outcome result, const char *why)
{
    if (data->finished)
        return;
    data->result = result;
    data->finished = true;
    if (why != NULL)
        fprintf(stderr, "%s\n", why);
    pw_main_loop_quit(data->loop);
}

static bool same_property(const struct spa_dict *props, const char *key, const char *want)
{
    const char *actual = props != NULL ? spa_dict_lookup(props, key) : NULL;
    return actual != NULL && strcmp(actual, want) == 0;
}

static void on_global(void *handle, uint32_t id, uint32_t permissions, const char *type,
                      uint32_t version, const struct spa_dict *props)
{
    (void)permissions;
    (void)version;
    struct change *data = handle;
    if (id != data->node_id || data->finished)
        return;
    if (strcmp(type, PW_TYPE_INTERFACE_Node) != 0 ||
        !same_property(props, PW_KEY_OBJECT_SERIAL, data->serial))
        stop(data, RETIRED, "The previous PipeWire node id now belongs to another object.");
    else
        data->found = true;
}

static void on_global_remove(void *handle, uint32_t id)
{
    struct change *data = handle;
    if (id == data->node_id)
        stop(data, RETIRED, "The original PipeWire node was removed.");
}

static void on_info(void *handle, const struct pw_node_info *info)
{
    struct change *data = handle;
    if (data->finished)
        return;
    const char *serial = info->props ? spa_dict_lookup(info->props, PW_KEY_OBJECT_SERIAL) : NULL;
    const char *name = info->props ? spa_dict_lookup(info->props, PW_KEY_NODE_NAME) : NULL;
    const char *path = info->props ? spa_dict_lookup(info->props, ALSA_PATH) : NULL;
    if (info->id != data->node_id ||
        (serial != NULL && strcmp(serial, data->serial) != 0) ||
        (name != NULL && strcmp(name, data->name) != 0) ||
        (path != NULL && strcmp(path, data->alsa_path) != 0)) {
        stop(data, RETIRED, "The bound PipeWire node does not match the saved identity.");
        return;
    }
    if (serial != NULL && name != NULL && path != NULL)
        data->info = true;
    if ((info->change_mask & PW_NODE_CHANGE_MASK_STATE) != 0)
        data->node_state = info->state;
}

static void on_param(void *handle, int seq, uint32_t id, uint32_t index,
                     uint32_t next, const struct spa_pod *pod)
{
    (void)seq;
    (void)index;
    (void)next;
    struct change *data = handle;
    if (data->finished || id != SPA_PARAM_Props || pod == NULL || !spa_pod_is_object(pod))
        return;
    const struct spa_pod_prop *params = spa_pod_find_prop(pod, NULL, SPA_PROP_params);
    if (params == NULL || !spa_pod_is_struct(&params->value))
        return;
    const struct spa_pod *item;
    bool key = true, headroom = false;
    SPA_POD_STRUCT_FOREACH(&params->value, item) {
        if (key) {
            const char *name;
            headroom = spa_pod_get_string(item, &name) == 0 && strcmp(name, HEADROOM) == 0;
        } else if (headroom) {
            if (data->value || spa_pod_get_int(item, &data->current) < 0) {
                stop(data, FAILED, "Ambiguous ALSA headroom readback.");
                return;
            }
            data->value = true;
        }
        key = !key;
    }
}

static void on_removed(void *handle)
{
    stop(handle, RETIRED, "The bound PipeWire object was retired.");
}

static void on_error(void *handle, uint32_t id, int seq, int res, const char *message)
{
    (void)id;
    (void)seq;
    (void)res;
    stop(handle, FAILED, message);
}

static void on_proxy_error(void *handle, int seq, int res, const char *message)
{
    on_error(handle, 0, seq, res, message);
}

static const struct pw_node_events node_events = {
    PW_VERSION_NODE_EVENTS,
    .info = on_info,
    .param = on_param,
};

static const struct pw_proxy_events proxy_events = {
    PW_VERSION_PROXY_EVENTS,
    .removed = on_removed,
    .error = on_proxy_error,
};

static void next(struct change *data, enum stage stage)
{
    data->stage = stage;
    data->sync = pw_core_sync(data->core, PW_ID_CORE, 0);
    if (data->sync < 0)
        stop(data, FAILED, "Could not synchronize the PipeWire connection.");
}

static void query(struct change *data, enum stage stage)
{
    data->value = false;
    if (pw_node_enum_params(data->node, 0, SPA_PARAM_Props, 0, UINT32_MAX, NULL) < 0)
        stop(data, FAILED, "Could not query the bound PipeWire node.");
    else
        next(data, stage);
}

static int set_bound_headroom(struct change *data)
{
    unsigned char storage[256];
    struct spa_pod_builder builder = SPA_POD_BUILDER_INIT(storage, sizeof(storage));
    struct spa_pod_frame object, list;
    spa_pod_builder_push_object(&builder, &object, SPA_TYPE_OBJECT_Props, SPA_PARAM_Props);
    spa_pod_builder_prop(&builder, SPA_PROP_params, 0);
    spa_pod_builder_push_struct(&builder, &list);
    spa_pod_builder_string(&builder, HEADROOM);
    spa_pod_builder_int(&builder, data->target);
    spa_pod_builder_pop(&builder, &list);
    const struct spa_pod *props = spa_pod_builder_pop(&builder, &object);
    return props != NULL ? pw_node_set_param(data->node, SPA_PARAM_Props, 0, props) : -EIO;
}

static void on_done(void *handle, uint32_t id, int seq)
{
    struct change *data = handle;
    if (data->finished || id != PW_ID_CORE || seq != data->sync)
        return;
    if (!process_birth(data->server_pid, data->server_birth)) {
        stop(data, RETIRED, "The original PipeWire daemon was replaced.");
        return;
    }
    switch (data->stage) {
    case DISCOVER:
        if (!data->found) {
            stop(data, RETIRED, "The original PipeWire node is absent.");
            return;
        }
        data->node = pw_registry_bind(data->registry, data->node_id,
                                      PW_TYPE_INTERFACE_Node, PW_VERSION_NODE, 0);
        if (data->node == NULL) {
            stop(data, FAILED, "Could not bind the original PipeWire node.");
            return;
        }
        pw_proxy_add_listener((struct pw_proxy *)data->node, &data->proxy_hook, &proxy_events, data);
        if (pw_node_add_listener(data->node, &data->node_hook, &node_events, data) < 0)
            stop(data, FAILED, "Could not observe the bound PipeWire node.");
        else
            next(data, BIND);
        break;
    case BIND:
        if (!data->info)
            stop(data, FAILED, "The bound node did not report its full identity.");
        else
            query(data, READ);
        break;
    case READ:
        if (!data->value) {
            stop(data, FAILED, "The bound node did not report ALSA headroom.");
        } else if (!data->write) {
            printf("%d\n", data->current);
            stop(data, OK, NULL);
        } else if (data->current != data->expected) {
            stop(data, CONFLICT, "The current ALSA headroom differs from the lease.");
        } else if (data->target != 0 && data->node_state != PW_NODE_STATE_SUSPENDED) {
            stop(data, BUSY, "The original playback node is no longer suspended.");
        } else if (set_bound_headroom(data) < 0) {
            stop(data, FAILED, "The bound node rejected the ALSA headroom request.");
        } else {
            query(data, CONFIRM);
        }
        break;
    case CONFIRM:
        if (data->value && data->current == data->target)
            stop(data, OK, NULL);
        else
            stop(data, FAILED, "The ALSA headroom request was not confirmed.");
        break;
    }
}

static const struct pw_core_events core_events = {
    PW_VERSION_CORE_EVENTS,
    .done = on_done,
    .error = on_error,
};

static const struct pw_registry_events registry_events = {
    PW_VERSION_REGISTRY_EVENTS,
    .global = on_global,
    .global_remove = on_global_remove,
};

int main(int argc, char **argv)
{
    struct change data = { .result = FAILED, .node_state = PW_NODE_STATE_ERROR };
    unsigned long long pid, birth, id, serial, expected = 0, target = 0;
    if ((argc != 8 && argc != 10) || !parse_number(argv[2], INT_MAX, &pid) || pid < 2 ||
        !parse_number(argv[3], ULLONG_MAX, &birth) || birth == 0 ||
        !parse_number(argv[4], UINT32_MAX - 1, &id) ||
        !parse_number(argv[5], ULLONG_MAX, &serial) ||
        (argc == 10 && (!parse_number(argv[8], 1024, &expected) ||
                       !parse_number(argv[9], 1024, &target) ||
                       !((expected == 0 && target == 1024) || (expected == 1024 && target == 0))))) {
        fprintf(stderr, "Usage: %s SOCKET PID BIRTH NODE SERIAL NAME ALSA_PATH [EXPECTED TARGET]\n", argv[0]);
        return USAGE;
    }
    data.write = argc == 10;
#ifdef WAYDAW_READ_ONLY
    if (data.write)
        return USAGE;
#endif
    data.node_id = (uint32_t)id;
    data.server_pid = (pid_t)pid;
    data.server_birth = birth;
    data.serial = argv[5];
    data.name = argv[6];
    data.alsa_path = argv[7];
    data.expected = (int32_t)expected;
    data.target = (int32_t)target;
    int fd = connect_peer(argv[1], (pid_t)pid, birth);
    if (fd < 0) {
        fprintf(stderr, "The requested original PipeWire server peer could not be verified.\n");
        return process_birth((pid_t)pid, birth) ? FAILED : RETIRED;
    }

    pw_init(NULL, NULL);
    data.loop = pw_main_loop_new(NULL);
    struct pw_context *context = data.loop != NULL ?
        pw_context_new(pw_main_loop_get_loop(data.loop), NULL, 0) : NULL;
    if (context != NULL) {
        data.core = pw_context_connect_fd(context, fd, NULL, 0);
        fd = -1;
        if (data.core != NULL && pw_core_add_listener(data.core, &data.core_hook, &core_events, &data) >= 0) {
            data.registry = pw_core_get_registry(data.core, PW_VERSION_REGISTRY, 0);
            if (data.registry != NULL && pw_registry_add_listener(data.registry, &data.registry_hook,
                                                                 &registry_events, &data) >= 0) {
                next(&data, DISCOVER);
                if (!data.finished)
                    pw_main_loop_run(data.loop);
            }
        }
        pw_context_destroy(context);
    }
    if (data.loop != NULL)
        pw_main_loop_destroy(data.loop);
    if (fd >= 0)
        close(fd);
    pw_deinit();
    return data.result;
}
