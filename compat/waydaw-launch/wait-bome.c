/* Launch Bome and acknowledge GUI initialization, then retain its exit status.
 * WaitForInputIdle is an initialization barrier, not MIDI/project readiness.
 */
#ifndef UNICODE
#define UNICODE
#endif
#ifndef _UNICODE
#define _UNICODE
#endif
#include <windows.h>
#include <stdio.h>
#include <stdlib.h>
#include <wchar.h>

/* Quote one argv element using the Windows CRT command-line rules, including
 * quotes and runs of backslashes before quotes or the closing delimiter. */
static wchar_t *quote_argument(wchar_t *output, const wchar_t *input)
{
    *output++ = L'"';
    for (;;) {
        size_t slashes = 0;
        while (*input == L'\\') { ++slashes; ++input; }
        size_t count = (*input == L'"' || !*input) ? 2 * slashes : slashes;
        while (count--) *output++ = L'\\';
        if (!*input) break;
        if (*input == L'"') *output++ = L'\\';
        *output++ = *input++;
    }
    *output++ = L'"';
    *output = 0;
    return output;
}

int wmain(int argc, wchar_t **argv)
{
    if (argc < 4) {
        fputs("Usage: wait-bome.exe ready-file timeout-ms executable [args...]\n", stderr);
        return 1;
    }
    wchar_t *end;
    unsigned long timeout = wcstoul(argv[2], &end, 10);
    if (*end || !timeout || timeout > 30000) return 1;
    size_t capacity = 1;
    for (int i = 3; i < argc; ++i) capacity += 2 * wcslen(argv[i]) + 4;
    wchar_t *command = calloc(capacity, sizeof(*command));
    if (!command) return 1;
    wchar_t *cursor = command;
    for (int i = 3; i < argc; ++i) {
        if (i > 3) *cursor++ = L' ';
        cursor = quote_argument(cursor, argv[i]);
    }
    STARTUPINFOW startup = {0};
    PROCESS_INFORMATION child = {0};
    startup.cb = sizeof(startup);
    if (!CreateProcessW(argv[3], command, NULL, NULL, FALSE, 0, NULL, NULL, &startup, &child)) {
        fprintf(stderr, "Bome CreateProcess failed: %lu\n", GetLastError());
        free(command);
        return 1;
    }
    free(command);
    CloseHandle(child.hThread);
    DWORD idle = WaitForInputIdle(child.hProcess, (DWORD)timeout);
    int result = 1;
    if (idle != 0 || WaitForSingleObject(child.hProcess, 0) != WAIT_TIMEOUT) {
        fprintf(stderr, "Bome exited or failed GUI initialization (wait=%lu).\n", idle);
        goto done;
    }
    /* Publish readiness by rename so the host never sees a partial receipt. */
    size_t length = wcslen(argv[1]) + 5;
    wchar_t *temporary = calloc(length, sizeof(*temporary));
    if (!temporary) goto done;
    swprintf(temporary, length, L"%ls.tmp", argv[1]);
    HANDLE file = CreateFileW(temporary, GENERIC_WRITE, 0, NULL, CREATE_NEW, FILE_ATTRIBUTE_NORMAL, NULL);
    DWORD written = 0;
    BOOL published = file != INVALID_HANDLE_VALUE;
    if (published) {
        published = WriteFile(file, "ready\n", 6, &written, NULL) && written == 6;
        CloseHandle(file);
    }
    if (published) published = MoveFileExW(temporary, argv[1], MOVEFILE_WRITE_THROUGH);
    if (!published) DeleteFileW(temporary);
    free(temporary);
    if (!published) {
        fputs("Could not publish Bome readiness.\n", stderr);
        goto done;
    }
    if (WaitForSingleObject(child.hProcess, INFINITE) == WAIT_OBJECT_0) {
        DWORD status;
        if (GetExitCodeProcess(child.hProcess, &status)) result = (int)status;
    }
done:
    /* On startup failure the supervisor cancels the group and wineserver.
     * Do not leave a failed GUI child running while reporting success. */
    CloseHandle(child.hProcess);
    return result;
}
