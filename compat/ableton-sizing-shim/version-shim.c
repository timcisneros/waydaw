/* WayDAW app-scoped sizing shim — proxy version.dll for the Proton-exp
 * Ableton runner path ONLY (see docs/ableton-proton-full-height-preapply-options.md).
 *
 * Problem: a full-height window rectangle latches a runtime "desired client
 * height = full workarea" belief in Wine/Ableton, driving the
 * WM_WINDOWPOSCHANGED reconciliation storm (UI thread pegged, input starved).
 * Post-apply clamps (KWin script) fire too late to prevent the latch.
 *
 * Fix: clamp the sizing pipeline at its Windows-side root. Answering
 * WM_GETMINMAXINFO with ptMaxTrackSize.y = cap makes every path respect the
 * cap BEFORE any full-height rectangle exists: the interactive sizing loop,
 * DefWindowProc's WM_WINDOWPOSCHANGING handling of SetWindowPos, and Wine's
 * X11 PMaxSize hint (published race-free by Wine itself, so the WM refuses
 * over-cap grants pre-apply too). WM_WINDOWPOSCHANGING is clamped as
 * belt-and-braces for paths that skip minmax (SWP_NOSENDCHANGING aside).
 * WM_WINDOWPOSCHANGED is deliberately NOT used (post-fact — the KWin cap's
 * mistake); WM_NCCALCSIZE is deliberately NOT used (wrong layer — lying
 * about the client area recreates the divergence).
 *
 * Scope: thread-local WH_CBT hook on the process main thread only (never a
 * global hook); subclasses only top-level (!WS_CHILD) resizable
 * (WS_THICKFRAME) windows — the Ableton main window. Auth dialogs and child
 * windows are never subclassed; other prefix processes (WebView2 etc.) never
 * load this DLL because it only exists in Ableton's Program directory.
 *
 * Loading is gated by WINEDLLOVERRIDES="version=n,b", set only by the
 * proton-exp runner launch env. Without the override the file is inert.
 * No Ableton binary is modified; the DLL lives only in the disposable
 * copied test prefix.
 *
 * Cap: WAYDAW_SIZING_SHIM_MAX_H (Win32 window-height units), default 1000 —
 * the placement value already proven calm at startup (cfg Size.h=1000).
 *
 * Floor: WAYDAW_SIZING_SHIM_MIN_H (Win32 window-height units), default 820.
 * Ableton itself switches to a menu-less compact/borderless presentation
 * (_MOTIF_WM_HINTS decorations 0x0, File/Edit menu row not rendered) when the
 * window gets short — decorated→borderless around frame height ~740-750, with
 * hysteresis back around ~1000+ (see
 * docs/ableton-proton-decoration-menubar-occlusion.md). Raising
 * ptMinTrackSize.y keeps every resize path above that band so the app never
 * enters the menu-less mode. The floor is clamped to never exceed the cap.
 *
 * Logs to stderr with prefix "waydaw-sizing-shim:" (captured by the
 * launcher's tee into logs/ableton.log).
 */

#include <windows.h>
#include <stdio.h>
#include <stdlib.h>

static const WCHAR PROP_ORIG[] = L"waydaw.sizing.shim.orig";

static HMODULE g_real = NULL;
static HHOOK g_cbt = NULL;
static LONG g_cap_h = 1000;
static LONG g_min_h = 820;
static LONG g_minmax_clamps = 0;
static LONG g_minmax_floor_clamps = 0;
static LONG g_pos_clamps = 0;
static LONG g_pos_floor_clamps = 0;

/* ---- logging (rate-limited: first 5 of each kind, then every 100th) ---- */

static int should_log(LONG n)
{
    return n <= 5 || (n % 100) == 0;
}

/* ---- proxy plumbing: forward to the real (builtin) version.dll ---- */

typedef BOOL  (WINAPI *pGetFileVersionInfoA)(LPCSTR, DWORD, DWORD, LPVOID);
typedef BOOL  (WINAPI *pGetFileVersionInfoW)(LPCWSTR, DWORD, DWORD, LPVOID);
typedef DWORD (WINAPI *pGetFileVersionInfoSizeA)(LPCSTR, LPDWORD);
typedef DWORD (WINAPI *pGetFileVersionInfoSizeW)(LPCWSTR, LPDWORD);
typedef BOOL  (WINAPI *pVerQueryValueA)(LPCVOID, LPCSTR, LPVOID *, PUINT);
typedef BOOL  (WINAPI *pVerQueryValueW)(LPCVOID, LPCWSTR, LPVOID *, PUINT);

static pGetFileVersionInfoA     r_GetFileVersionInfoA;
static pGetFileVersionInfoW     r_GetFileVersionInfoW;
static pGetFileVersionInfoSizeA r_GetFileVersionInfoSizeA;
static pGetFileVersionInfoSizeW r_GetFileVersionInfoSizeW;
static pVerQueryValueA          r_VerQueryValueA;
static pVerQueryValueW          r_VerQueryValueW;

/* Load the real DLL by explicit system-directory path so the "version=n,b"
 * override cannot resolve back to this proxy (self-recursion guard). */
static int ensure_real(void)
{
    WCHAR path[MAX_PATH];
    UINT n;

    if (g_real)
        return 1;
    n = GetSystemDirectoryW(path, MAX_PATH);
    if (!n || n > MAX_PATH - 16)
        return 0;
    lstrcatW(path, L"\\version.dll");
    g_real = LoadLibraryW(path);
    if (!g_real) {
        fprintf(stderr, "waydaw-sizing-shim: ERROR failed to load real %ls\n", path);
        return 0;
    }
    r_GetFileVersionInfoA     = (pGetFileVersionInfoA)(void *)GetProcAddress(g_real, "GetFileVersionInfoA");
    r_GetFileVersionInfoW     = (pGetFileVersionInfoW)(void *)GetProcAddress(g_real, "GetFileVersionInfoW");
    r_GetFileVersionInfoSizeA = (pGetFileVersionInfoSizeA)(void *)GetProcAddress(g_real, "GetFileVersionInfoSizeA");
    r_GetFileVersionInfoSizeW = (pGetFileVersionInfoSizeW)(void *)GetProcAddress(g_real, "GetFileVersionInfoSizeW");
    r_VerQueryValueA          = (pVerQueryValueA)(void *)GetProcAddress(g_real, "VerQueryValueA");
    r_VerQueryValueW          = (pVerQueryValueW)(void *)GetProcAddress(g_real, "VerQueryValueW");
    return 1;
}

BOOL WINAPI GetFileVersionInfoA(LPCSTR f, DWORD h, DWORD len, LPVOID data)
{
    if (!ensure_real() || !r_GetFileVersionInfoA) return FALSE;
    return r_GetFileVersionInfoA(f, h, len, data);
}

BOOL WINAPI GetFileVersionInfoW(LPCWSTR f, DWORD h, DWORD len, LPVOID data)
{
    if (!ensure_real() || !r_GetFileVersionInfoW) return FALSE;
    return r_GetFileVersionInfoW(f, h, len, data);
}

DWORD WINAPI GetFileVersionInfoSizeA(LPCSTR f, LPDWORD h)
{
    if (!ensure_real() || !r_GetFileVersionInfoSizeA) return 0;
    return r_GetFileVersionInfoSizeA(f, h);
}

DWORD WINAPI GetFileVersionInfoSizeW(LPCWSTR f, LPDWORD h)
{
    if (!ensure_real() || !r_GetFileVersionInfoSizeW) return 0;
    return r_GetFileVersionInfoSizeW(f, h);
}

BOOL WINAPI VerQueryValueA(LPCVOID block, LPCSTR sub, LPVOID *buf, PUINT len)
{
    if (!ensure_real() || !r_VerQueryValueA) return FALSE;
    return r_VerQueryValueA(block, sub, buf, len);
}

BOOL WINAPI VerQueryValueW(LPCVOID block, LPCWSTR sub, LPVOID *buf, PUINT len)
{
    if (!ensure_real() || !r_VerQueryValueW) return FALSE;
    return r_VerQueryValueW(block, sub, buf, len);
}

/* ---- the sizing clamp ---- */

static LRESULT CALLBACK sub_proc(HWND hwnd, UINT msg, WPARAM wp, LPARAM lp)
{
    WNDPROC orig = (WNDPROC)GetPropW(hwnd, PROP_ORIG);
    LRESULT r;

    /* Run the app's handling first, then clamp its answer, so the clamp
     * always wins regardless of what the app or DefWindowProc filled in. */
    r = orig ? CallWindowProcW(orig, hwnd, msg, wp, lp)
             : DefWindowProcW(hwnd, msg, wp, lp);

    if (msg == WM_GETMINMAXINFO && lp) {
        MINMAXINFO *mmi = (MINMAXINFO *)lp;
        LONG before = mmi->ptMaxTrackSize.y;
        LONG before_min = mmi->ptMinTrackSize.y;
        if (mmi->ptMaxTrackSize.y > g_cap_h)
            mmi->ptMaxTrackSize.y = g_cap_h;
        if (mmi->ptMaxSize.y > g_cap_h)
            mmi->ptMaxSize.y = g_cap_h;
        if (before > g_cap_h) {
            LONG n = ++g_minmax_clamps;
            if (should_log(n))
                fprintf(stderr,
                        "waydaw-sizing-shim: clamp WM_GETMINMAXINFO #%ld hwnd=%p maxtrack.y %ld -> %ld\n",
                        (long)n, (void *)hwnd, (long)before, (long)g_cap_h);
        }
        if (mmi->ptMinTrackSize.y < g_min_h)
            mmi->ptMinTrackSize.y = g_min_h;
        if (before_min < g_min_h) {
            LONG n = ++g_minmax_floor_clamps;
            if (should_log(n))
                fprintf(stderr,
                        "waydaw-sizing-shim: floor WM_GETMINMAXINFO #%ld hwnd=%p mintrack.y %ld -> %ld\n",
                        (long)n, (void *)hwnd, (long)before_min, (long)g_min_h);
        }
    } else if (msg == WM_WINDOWPOSCHANGING && lp) {
        WINDOWPOS *pos = (WINDOWPOS *)lp;
        if (!(pos->flags & SWP_NOSIZE) && pos->cy > g_cap_h) {
            LONG n = ++g_pos_clamps;
            if (should_log(n))
                fprintf(stderr,
                        "waydaw-sizing-shim: clamp WM_WINDOWPOSCHANGING #%ld hwnd=%p cy %ld -> %ld\n",
                        (long)n, (void *)hwnd, (long)pos->cy, (long)g_cap_h);
            pos->cy = g_cap_h;
        }
        /* Belt-and-braces floor for paths that skip WM_GETMINMAXINFO. The
         * cy >= 200 guard leaves minimize/iconify rectangles (tiny cy) and
         * other special placements alone; only plausible short resizes of
         * the tracked top-level window are raised to the floor. */
        if (!(pos->flags & SWP_NOSIZE) && pos->cy >= 200 && pos->cy < g_min_h
            && !IsIconic(hwnd)) {
            LONG n = ++g_pos_floor_clamps;
            if (should_log(n))
                fprintf(stderr,
                        "waydaw-sizing-shim: floor WM_WINDOWPOSCHANGING #%ld hwnd=%p cy %ld -> %ld\n",
                        (long)n, (void *)hwnd, (long)pos->cy, (long)g_min_h);
            pos->cy = g_min_h;
        }
    } else if (msg == WM_NCDESTROY) {
        if (orig) {
            SetWindowLongPtrW(hwnd, GWLP_WNDPROC, (LONG_PTR)orig);
            RemovePropW(hwnd, PROP_ORIG);
        }
    }
    return r;
}

static void subclass(HWND hwnd, DWORD style)
{
    WNDPROC orig;
    WCHAR cls[64];

    if (GetPropW(hwnd, PROP_ORIG))
        return;
    orig = (WNDPROC)GetWindowLongPtrW(hwnd, GWLP_WNDPROC);
    if (!orig)
        return;
    if (!SetPropW(hwnd, PROP_ORIG, (HANDLE)orig))
        return;
    if (!SetWindowLongPtrW(hwnd, GWLP_WNDPROC, (LONG_PTR)sub_proc)) {
        RemovePropW(hwnd, PROP_ORIG);
        return;
    }
    cls[0] = 0;
    GetClassNameW(hwnd, cls, 64);
    fprintf(stderr,
            "waydaw-sizing-shim: subclassed hwnd=%p class=%ls style=0x%08lx cap_h=%ld min_h=%ld\n",
            (void *)hwnd, cls, (unsigned long)style, (long)g_cap_h, (long)g_min_h);
}

static LRESULT CALLBACK cbt_proc(int code, WPARAM wp, LPARAM lp)
{
    if (code == HCBT_CREATEWND) {
        HWND hwnd = (HWND)wp;
        CBT_CREATEWNDW *cw = (CBT_CREATEWNDW *)lp;
        if (hwnd && cw && cw->lpcs) {
            DWORD style = (DWORD)cw->lpcs->style;
            /* Top-level resizable windows only: the Ableton main window.
             * Dialogs (no thick frame) and child windows are left alone. */
            if (!(style & WS_CHILD) && (style & WS_THICKFRAME))
                subclass(hwnd, style);
        }
    }
    return CallNextHookEx(g_cbt, code, wp, lp);
}

BOOL WINAPI DllMain(HINSTANCE inst, DWORD reason, LPVOID reserved)
{
    (void)inst;
    (void)reserved;
    if (reason == DLL_PROCESS_ATTACH) {
        const char *env = getenv("WAYDAW_SIZING_SHIM_MAX_H");
        const char *env_min = getenv("WAYDAW_SIZING_SHIM_MIN_H");
        DisableThreadLibraryCalls(inst);
        if (env) {
            long v = strtol(env, NULL, 10);
            if (v >= 200 && v <= 8000)
                g_cap_h = (LONG)v;
        }
        if (env_min) {
            long v = strtol(env_min, NULL, 10);
            if (v >= 200 && v <= 8000)
                g_min_h = (LONG)v;
        }
        /* The floor must never exceed the cap or the legal band is empty. */
        if (g_min_h > g_cap_h) {
            fprintf(stderr,
                    "waydaw-sizing-shim: WARNING min_h %ld > cap_h %ld; lowering min_h to cap\n",
                    (long)g_min_h, (long)g_cap_h);
            g_min_h = g_cap_h;
        }
        /* Thread-local hook on the loading (main) thread only — the thread
         * that creates the Ableton main window. Never a global hook. */
        g_cbt = SetWindowsHookExW(WH_CBT, cbt_proc, NULL, GetCurrentThreadId());
        fprintf(stderr, "waydaw-sizing-shim: loaded (cap_h=%ld, min_h=%ld, cbt=%s, tid=%lu)\n",
                (long)g_cap_h, (long)g_min_h, g_cbt ? "installed" : "FAILED",
                (unsigned long)GetCurrentThreadId());
    } else if (reason == DLL_PROCESS_DETACH) {
        if (g_cbt)
            UnhookWindowsHookEx(g_cbt);
        if (g_real)
            FreeLibrary(g_real);
    }
    return TRUE;
}
