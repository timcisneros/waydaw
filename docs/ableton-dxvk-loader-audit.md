# Ableton DXVK loader audit

Prepared: 2026-06-19.

Purpose: determine why alternate Wine runners fail to load the copied
source-prefix DXVK DLLs when launched with:

```bash
WINEDLLOVERRIDES=d3d11,dxgi=n
```

This is a read-only audit. No launch command was run for this audit, and the
working prefix was not touched.

## Candidate status

```text
candidate1_status=blocked_backend_loader
candidate2_status=blocked_backend_loader
```

Candidate 1, Kron4ek Proton Experimental 11.0:

```text
status=blocked_backend_loader
official_usability_result=no
reason=without enforcement runner overwrote DXVK with Wine builtin DLLs; with --enforce-dxvk hashes matched source but Ableton failed before launch with d3d11.dll not found / status c0000135
working_prefix_touched=no
```

Candidate 2, Kron4ek Wine 11.11 staging-tkg:

```text
status=blocked_backend_loader
official_usability_result=no
reason=with --enforce-dxvk, copied-prefix DXVK hashes matched source but Ableton failed before launch; backend_effective=invalid_builtin_dll_for_dxvk_comparison; ableton_launched=no; window_detected=no
working_prefix_touched=no
```

## DLL file and hash comparison

`file` output:

```text
source_system32_d3d11_file=PE32+ executable for WINE (DLL), x86-64, 20 sections
source_system32_dxgi_file=PE32+ executable for WINE (DLL), x86-64, 20 sections
candidate2_system32_d3d11_file=PE32+ executable for WINE (DLL), x86-64, 20 sections
candidate2_system32_dxgi_file=PE32+ executable for WINE (DLL), x86-64, 20 sections
```

Hashes:

```text
source_system32_d3d11_sha256=557c1f50e7ff73bcd24968a02352519df89d8b3fe037d47580091ffafe1940dd
candidate2_system32_d3d11_sha256=557c1f50e7ff73bcd24968a02352519df89d8b3fe037d47580091ffafe1940dd
source_system32_dxgi_sha256=f31cd64b547c59441956b17e2a013791dcb62abb1e671fb31d49ff4d6c2b3fd7
candidate2_system32_dxgi_sha256=f31cd64b547c59441956b17e2a013791dcb62abb1e671fb31d49ff4d6c2b3fd7
source_hashes_match_candidate2=yes
```

Interpretation: the Candidate 2 enforced prefix did contain byte-identical
copies of the source prefix's 64-bit DXVK `d3d11.dll` and `dxgi.dll`.

## Registry override comparison

Source prefix `HKCU\Software\Wine\DllOverrides` section:

```text
"*concrt140"="native,builtin"
"*msvcp140"="native,builtin"
"*msvcp140_1"="native,builtin"
"*msvcp140_2"="native,builtin"
"*msvcp140_atomic_wait"="native,builtin"
"*msvcp140_codecvt_ids"="native,builtin"
"*vcamp140"="native,builtin"
"*vccorlib140"="native,builtin"
"*vcomp140"="native,builtin"
"*vcruntime140"="native,builtin"
"*vcruntime140_1"="native,builtin"
```

Candidate 2 enforced prefix `HKCU\Software\Wine\DllOverrides` section:

```text
"*concrt140"="native,builtin"
"*msvcp140"="native,builtin"
"*msvcp140_1"="native,builtin"
"*msvcp140_2"="native,builtin"
"*msvcp140_atomic_wait"="native,builtin"
"*msvcp140_codecvt_ids"="native,builtin"
"*vcamp140"="native,builtin"
"*vccorlib140"="native,builtin"
"*vcomp140"="native,builtin"
"*vcruntime140"="native,builtin"
"*vcruntime140_1"="native,builtin"
"ddraw"="native,builtin"
"dinput"="native,builtin"
"dinput8"="native,builtin"
"dsound"="native,builtin"
"version"="native,builtin"
"winhttp"="native,builtin"
"winmm"="native,builtin"
```

```text
source_registry_dlloverrides=no d3d11/dxgi overrides in registry section
candidate2_registry_dlloverrides=no d3d11/dxgi overrides in registry section; runner added unrelated native,builtin overrides
```

Interpretation: there is no persistent registry override for `d3d11` or `dxgi`
in either prefix. The only D3D override for the enforced run was the process
environment marker:

```text
export WINEDLLOVERRIDES=d3d11,dxgi=n
```

## Loader context

Candidate 2 enforced run:

```text
run_dir=logs/ableton-runner-tests/20260619-172535-candidate2-kron4ek-wine-11-11-dxvk-enforced
dxvk_hashes_match_source=yes
launch_winedlloverrides=d3d11,dxgi=n
ableton_launched=no
window_detected=no
backend_effective=invalid_builtin_dll_for_dxvk_comparison
```

Candidate 2 `logs/ableton.log` segment contains only the harness marker and no
Wine loader lines:

```text
log_segment_start=498120
log_segment_line_count=12
runner_log_dxvk_lines=0
runner_log_loader_error_lines=0
```

Candidate 1 enforced run did show the explicit loader failure:

```text
Library d3d11.dll (needed by Ableton Live 12 Suite.exe) not found
loader_init failed, status c0000135
```

Candidate 2 did not show that exact line in the run bundle, but it ended in the
same pre-window state: `ableton_launched=no`, `window_detected=no`, no DXVK log
lines, and no live usability result.

## Hypotheses

Hypothesis A: native-only `d3d11,dxgi=n` is too strict for these runners;
`n,b` may allow launch while still preferring DXVK.

Hypothesis B: the source DXVK DLLs have dependencies or assumptions compatible
with system Wine but not these alternate runners.

Hypothesis C: runner prefix update/registry state is different enough that
copied DXVK files alone are insufficient.

## Loader-only probe result

Probe tool:

```text
bin/ableton-dxvk-loader-probe
```

Run:

```text
runner=.local-runners/kron4ek-wine-11.11-staging-tkg
wine_version=wine-11.11.r0.g4d000a90 ( TkG Staging NTsync )
run_root=logs/ableton-dxvk-loader-probes/20260619-173904-candidate2-kron4ek-wine-11-11-*
ableton_launched=no
working_prefix_touched=no
```

Native-only mode:

```text
override_mode=native_only
launch_command=WINEDEBUG=+loaddll,+module WINEDLLOVERRIDES=d3d11,dxgi=n wine rundll32.exe d3d11.dll,DllRegisterServer ; wine rundll32.exe dxgi.dll,DllRegisterServer
dxvk_hashes_match_source=yes
d3d11_signature=DXVK
dxgi_signature=DXVK
loader_loaded_native_d3d11=no
loader_loaded_native_dxgi=no
loader_mapped_prefix_d3d11=no
loader_mapped_prefix_dxgi=no
loader_fell_back_builtin_d3d11=no
loader_fell_back_builtin_dxgi=no
```

Native-only raw loader evidence:

```text
get_load_order_value got environment n for L"d3d11"
Failed to load module L"d3d11.dll"; status=c0000135
get_load_order_value got environment n for L"dxgi"
Failed to load module L"dxgi.dll"; status=c0000135
```

Native-then-builtin mode:

```text
override_mode=native_then_builtin
launch_command=WINEDEBUG=+loaddll,+module WINEDLLOVERRIDES=d3d11,dxgi=n,b wine rundll32.exe d3d11.dll,DllRegisterServer ; wine rundll32.exe dxgi.dll,DllRegisterServer
dxvk_hashes_match_source=yes
d3d11_signature=DXVK
dxgi_signature=DXVK
loader_loaded_native_d3d11=no
loader_loaded_native_dxgi=no
loader_mapped_prefix_d3d11=yes
loader_mapped_prefix_dxgi=yes
loader_fell_back_builtin_d3d11=yes
loader_fell_back_builtin_dxgi=yes
```

Native-then-builtin raw loader evidence:

```text
get_load_order_value got environment n,b for L"d3d11"
map_image_into_view mapping PE file L"\\??\\C:\\windows\\system32\\d3d11.dll"
map_image_into_view mapping PE file L"\\??\\C:\\windows\\system32\\dxgi.dll"
load_dll looking for L"wined3d.dll"
Loaded L"C:\\windows\\system32\\wined3d.dll" ... builtin
get_load_order_value got environment n,b for L"dxgi"
map_image_into_view mapping PE file L"\\??\\C:\\windows\\system32\\dxgi.dll"
load_dll looking for L"wined3d.dll"
Loaded L"C:\\windows\\system32\\wined3d.dll" ... builtin
```

Interpretation:

- `d3d11,dxgi=n` is too strict for Candidate 2 with copied source-prefix DXVK
  DLLs: both DLL loads fail with `status=c0000135`.
- `d3d11,dxgi=n,b` changes loader behavior and maps the copied prefix DLLs, but
  it also loads builtin `wined3d.dll`; that is not clean DXVK evidence and does
  not justify changing `--enforce-dxvk` to `n,b` for official runner comparisons.
- Continue to treat Candidate 1 and Candidate 2 as `blocked_backend_loader`.

## System Wine control and import audit

System Wine control run:

```text
runner=/usr
wine_version=wine-11.0 (Staging)
run_root=logs/ableton-dxvk-loader-probes/20260619-212030-system-wine-11-staging-control-*
ableton_launched=no
working_prefix_touched=no
```

System Wine native-only mode:

```text
override_mode=native_only
dxvk_hashes_match_source=yes
d3d11_signature=DXVK
dxgi_signature=DXVK
loader_mapped_prefix_d3d11=no
loader_mapped_prefix_dxgi=no
loader_loaded_wined3d=no
raw_result=d3d11.dll and dxgi.dll both fail with status=c0000135
```

System Wine native-then-builtin mode:

```text
override_mode=native_then_builtin
dxvk_hashes_match_source=yes
d3d11_signature=DXVK
dxgi_signature=DXVK
loader_mapped_prefix_d3d11=yes
loader_mapped_prefix_dxgi=yes
loader_loaded_wined3d=no
raw_result=copied d3d11.dll and dxgi.dll are mapped; no wined3d.dll load was observed
```

Interpretation: because system Wine also fails the `rundll32` native-only probe,
`rundll32.exe d3d11.dll,DllRegisterServer` is not a valid clean DXVK-load
control. The difference that still matters is the `n,b` behavior:

- system Wine maps the copied source-prefix DXVK DLLs without loading
  `wined3d.dll`;
- Candidate 2 maps the copied DLLs but loads builtin `wined3d.dll`.

This points away from a simple missing copied DLL and toward runner PE/builtin
resolution or Wine build behavior differences.

Read-only import inspection of source-prefix DLLs:

```text
d3d11.dll_sha256=557c1f50e7ff73bcd24968a02352519df89d8b3fe037d47580091ffafe1940dd
d3d11_imports=ADVAPI32.dll, dxgi.dll, GDI32.dll, KERNEL32.dll, msvcrt.dll, SETUPAPI.dll, USER32.dll
dxgi.dll_sha256=f31cd64b547c59441956b17e2a013791dcb62abb1e671fb31d49ff4d6c2b3fd7
dxgi_imports=ADVAPI32.dll, KERNEL32.dll, msvcrt.dll, SETUPAPI.dll, USER32.dll
suspected_missing_dependency=none obvious from PE imports; no direct vulkan-1.dll, msvcp*, or vcruntime* import was listed
```

`winedump` prints `This is a Wine builtin DLL` for these PE files even though
strings/signature checks identify the source-prefix files as DXVK. Treat Wine's
`builtin` label in `+loaddll` output as ambiguous unless paired with hash,
signature, and `wined3d.dll` evidence.

Candidate 2 runner file inspection:

```text
runner_x86_64_d3d11=.local-runners/kron4ek-wine-11.11-staging-tkg/lib/wine/x86_64-windows/d3d11.dll
runner_x86_64_dxgi=.local-runners/kron4ek-wine-11.11-staging-tkg/lib/wine/x86_64-windows/dxgi.dll
runner_x86_64_wined3d=.local-runners/kron4ek-wine-11.11-staging-tkg/lib/wine/x86_64-windows/wined3d.dll
runner_x86_64_vulkan=.local-runners/kron4ek-wine-11.11-staging-tkg/lib/wine/x86_64-windows/vulkan-1.dll
runner_i386_counterparts=present
```

## PE loader-control probe status

Added source and wrapper:

```text
tools/dxvk-load-probe.c
bin/ableton-dxvk-pe-loader-probe
```

The intended PE program is loader-only and does not create a D3D device. It
calls:

```text
LoadLibraryW(L"dxgi.dll")
LoadLibraryW(L"d3d11.dll")
GetProcAddress(dxgi, "CreateDXGIFactory1")
GetProcAddress(d3d11, "D3D11CreateDevice")
```

Build availability check:

```text
command -v x86_64-w64-mingw32-gcc=no
command -v clang=no
pe_loader_probe_build_available=no
missing_compilers=x86_64-w64-mingw32-gcc clang
```

Follow-up after reported interactive install attempt:

```text
rpm -q mingw64-gcc=not installed
command -v x86_64-w64-mingw32-gcc=no
installed_mingw_support_packages=yes
installed_compiler_package=no
```

Installed MinGW support/runtime packages include `mingw64-crt`,
`mingw64-libgcc`, `mingw64-libstdc++`, and related libraries, but the compiler
binary package `mingw64-gcc` is still absent. No PE executable can be built from
`tools/dxvk-load-probe.c` yet.

Second follow-up after reported compiler install:

```text
rpm -q mingw64-gcc=not installed
command -v x86_64-w64-mingw32-gcc=no
/usr/bin/*mingw*gcc*=none
installed_mingw_support_packages=yes
installed_compiler_package=no
pe_loader_probe_build_available=no
```

The installed package set still contains MinGW runtime/support packages but not
the actual `mingw64-gcc` compiler package.

Final compiler verification:

```text
rpm -q mingw64-gcc=mingw64-gcc-16.1.1-1.fc44.x86_64
compiler_path=/usr/bin/x86_64-w64-mingw32-gcc
compiler_version=x86_64-w64-mingw32-gcc (GCC) 16.1.1 20260501 (Fedora MinGW 16.1.1-1.fc44)
```

The PE loader-control diagnostic was then built and run against copied prefixes
only. Ableton was not launched.

Generated path note:

```text
.local-tools/dxvk-load-probe.exe=PE32+ executable for MS Windows 5.02 (console), x86-64
```

PE loader-control run:

```text
run_root=logs/ableton-dxvk-pe-loader-probes/20260619-213942-*
ableton_launched=no
working_prefix_touched=no
```

System Wine native-only:

```text
runner=/usr
wine_version=wine-11.0 (Staging)
override_mode=native_only
dxvk_hashes_match_source=yes
probe_exit_code=1
probe_stdout=LoadLibraryW_dxgi=failed error=126; LoadLibraryW_d3d11=failed error=126
loader_mapped_prefix_d3d11=no
loader_mapped_prefix_dxgi=no
loader_loaded_wined3d=no
```

System Wine native-then-builtin:

```text
runner=/usr
wine_version=wine-11.0 (Staging)
override_mode=native_then_builtin
dxvk_hashes_match_source=yes
probe_exit_code=0
probe_stdout=LoadLibraryW_dxgi=ok; LoadLibraryW_d3d11=ok; GetProcAddress_CreateDXGIFactory1=ok; GetProcAddress_D3D11CreateDevice=ok
loader_mapped_prefix_d3d11=yes
loader_mapped_prefix_dxgi=yes
loader_loaded_wined3d=no
```

Candidate 2 native-only:

```text
runner=.local-runners/kron4ek-wine-11.11-staging-tkg
wine_version=wine-11.11.r0.g4d000a90 ( TkG Staging NTsync )
override_mode=native_only
dxvk_hashes_match_source=yes
probe_exit_code=1
probe_stdout=LoadLibraryW_dxgi=failed error=126; LoadLibraryW_d3d11=failed error=126
loader_mapped_prefix_d3d11=no
loader_mapped_prefix_dxgi=no
loader_loaded_wined3d=no
```

Candidate 2 native-then-builtin:

```text
runner=.local-runners/kron4ek-wine-11.11-staging-tkg
wine_version=wine-11.11.r0.g4d000a90 ( TkG Staging NTsync )
override_mode=native_then_builtin
dxvk_hashes_match_source=yes
probe_exit_code=0
probe_stdout=LoadLibraryW_dxgi=ok; LoadLibraryW_d3d11=ok; GetProcAddress_CreateDXGIFactory1=ok; GetProcAddress_D3D11CreateDevice=ok
loader_mapped_prefix_d3d11=yes
loader_mapped_prefix_dxgi=yes
loader_loaded_wined3d=yes
```

PE interpretation:

- Native-only `d3d11,dxgi=n` fails for both system Wine and Candidate 2, so it
  is not a usable standalone DXVK loader-control mode.
- `d3d11,dxgi=n,b` succeeds for both runners at the minimal
  `LoadLibraryW`/`GetProcAddress` level.
- Candidate 2 still differs materially because it loads `wined3d.dll` in the
  PE probe, while system Wine does not.
- Candidate 2 remains `blocked_backend_loader` for official Ableton runner
  comparison until the `wined3d` involvement is explained or avoided.

## PE loader sequence audit

Existing logs only were inspected:

```text
logs/ableton-dxvk-pe-loader-probes/20260619-213942-system-wine-11-staging-control-native_then_builtin/winedebug-loader.log
logs/ableton-dxvk-pe-loader-probes/20260619-213942-candidate2-kron4ek-wine-11-11-native_then_builtin/winedebug-loader.log
```

System Wine `native_then_builtin` sequence:

```text
override=d3d11,dxgi=n,b
dxgi_load_order=n,b
dxgi_mapped=C:\windows\system32\dxgi.dll
dxgi_process_attach=completed
d3d11_load_order=n,b
d3d11_mapped=C:\windows\system32\d3d11.dll
d3d11_reused_existing_dxgi=yes
d3d11_process_attach=completed
wined3d_loaded=no
```

Candidate 2 `native_then_builtin` sequence:

```text
override=d3d11,dxgi=n,b
dxgi_load_order=n,b
dxgi_mapped=C:\windows\system32\dxgi.dll
wined3d_loaded=during_dxgi_load_before_dxgi_process_attach_completed
wined3d_mapped=C:\windows\system32\wined3d.dll
dxgi_process_attach=completed_after_wined3d_attach
d3d11_load_order=n,b
d3d11_mapped=C:\windows\system32\d3d11.dll
d3d11_reused_existing_dxgi=yes
d3d11_reused_existing_wined3d=yes
d3d11_process_attach=completed
```

Runner file inspection, Candidate 2:

```text
runner_x86_64_d3d11_sha256=0bdc3d4549a4a1faf4b6fdbdb17fd5cf67fe5d9a12ba9e513d10ce6155b46ae2
runner_x86_64_d3d11_signature=PE32+ executable for WINE (DLL); Wine builtin DLL
runner_x86_64_dxgi_sha256=f730132df3d7d79f37a65a0ec01a8f6f116a119b18d2350483e864ae1b5971a6
runner_x86_64_dxgi_signature=PE32+ executable for WINE (DLL); Wine builtin DLL
runner_x86_64_wined3d_sha256=8e760f40480ea96018c19173d42a27c82af019eb575ba9c703a3f72c1564d027
runner_x86_64_wined3d_signature=PE32+ executable for WINE (DLL); Wine builtin DLL; WineD3D_OpenGL strings present
runner_x86_64_vulkan1_sha256=864f86add1f60e8442e8bb1a56304404cd7883e32562a7e3b18ea34b6e095f64
runner_x86_64_vulkan1_signature=PE32+ executable for WINE (DLL); Wine builtin DLL; winevulkan strings present
```

Sequence interpretation:

- Candidate 2 maps `C:\windows\system32\dxgi.dll` before `wined3d.dll` appears,
  but `wined3d.dll` is loaded during the Candidate 2 DXGI load/attach path.
- Candidate 2 then maps `C:\windows\system32\d3d11.dll`; that D3D11 load reuses
  the already-loaded `dxgi.dll` and `wined3d.dll`.
- No `Failed to load module` or `status=c0000135` line was observed in the
  Candidate 2 `native_then_builtin` PE sequence before `wined3d.dll` loaded.
- The log labels `C:\windows\system32\d3d11.dll` and `dxgi.dll` as `builtin`
  even when they map the copied prefix paths, so this sequence alone cannot
  prove whether Candidate 2 used runner builtin `d3d11`/`dxgi` instead of the
  copied prefix files. It does prove Candidate 2 pulled in runner WineD3D during
  the minimal PE loader path while system Wine did not.

Decision: Candidate 2 is not a clean DXVK runner for the official comparison
path. Leave it as `blocked_backend_loader` and abandon it for now unless a later
task specifically investigates runner PE/builtin resolution.

Candidate 2 final decision:

```text
Candidate 2 final status=abandoned_for_official_comparison
official_usability_result=no
reason=PE loader sequence shows Candidate 2 maps dxgi.dll, then loads wined3d.dll during DXGI load/attach before d3d11.dll; system Wine does not load wined3d in the same PE n,b control path
working_prefix_touched=no
```

Candidate 3 acquisition status:

```text
Candidate 3 status=acquisition_blocked
official_usability_result=no
reason=GitHub Actions artifact metadata visible, but artifact archive download returned HTTP 401 authentication required; no local artifact, no SHA256, no extraction, no prepare-only, no PE gate
ableton_launched=no
working_prefix_touched=no
```

Candidate 4 PE loader-control preflight:

```text
candidate4_selected=Lutris Wine 7.2-2
runner=.local-runners/lutris-wine-7.2-2-wine64-shim
wine_version=wine-7.2-1-g1f8837bdccd (Staging)
candidate4_dxvk_hashes_match_source=yes
candidate4_native_only=failed_before_dll_mapping_/lib/ld-linux.so.2_could_not_open
candidate4_native_then_builtin=failed_before_dll_mapping_/lib/ld-linux.so.2_could_not_open
candidate4_n_b_probe_exit_code=1
candidate4_n_b_maps_d3d11=no
candidate4_n_b_maps_dxgi=no
candidate4_n_b_loads_wined3d=no
candidate4_pe_gate_result=fail
status=blocked_pe_loader_preflight
official_usability_result=no
ableton_launched=no
working_prefix_touched=no
```

Interpretation: Candidate 4 does not reach the DXVK loader-control gate. The
standalone Lutris tarball's default `wine` requires `/lib/ld-linux.so.2`, which
is absent on this host; a local wine64 shim can report the Wine version and pass
prepare-only, but the PE probe still fails before mapping copied `d3d11.dll` or
`dxgi.dll`.

Candidate 4B PE loader-control preflight:

```text
candidate4b_selected=Bottles Soda 9.0-1
runner=.local-runners/bottles-soda-9.0-1-wine64-shim
wine_version=wine-experimental.bleeding.edge.9.0.93696.20240429 ( TkG Plain )
component_file_checksum=8806df3e294dd37cf461ed3432d65318
component_file_checksum_type=md5
md5_verified=yes
sha256=c38fe0ad3c12a49b61ec1fcaea5c5d8da4a3d1afc5991befe2af6b125f014c28
candidate4b_dxvk_hashes_match_source=yes
candidate4b_native_only=failed_before_dll_mapping_/lib/ld-linux.so.2_could_not_open
candidate4b_native_then_builtin=failed_before_dll_mapping_/lib/ld-linux.so.2_could_not_open
candidate4b_n_b_probe_exit_code=1
candidate4b_n_b_maps_d3d11=no
candidate4b_n_b_maps_dxgi=no
candidate4b_n_b_loads_wined3d=no
candidate4b_pe_gate_result=fail
status=blocked_pe_loader_preflight
official_usability_result=no
ableton_launched=no
working_prefix_touched=no
```

Interpretation: Candidate 4B does not reach the DXVK loader-control gate. It is
blocked by the same missing `/lib/ld-linux.so.2` runtime issue before copied
DXVK DLLs can be mapped.

Candidate 4 i686 loader retest:

```text
ld_linux_so_2_present=yes
glibc_i686_installed=glibc-2.43-6.fc44.i686
candidate4a_wine_runs=no_exit_159
candidate4a_probe_root=logs/ableton-dxvk-pe-loader-probes/20260619-221914-candidate4a-lutris-wine-7-2-2-after-i686-loader-*
candidate4a_native_only_dxvk_hashes_match_source=yes
candidate4a_native_only_probe_exit_code=1
candidate4a_native_only_maps_d3d11=no
candidate4a_native_only_maps_dxgi=no
candidate4a_native_only_loads_wined3d=no
candidate4a_native_only_error=run_wineboot_boot_event_wait_timed_out_then_c0000135_for_dxgi_and_d3d11
candidate4a_native_then_builtin_result=not_completed_no_result_env
candidate4a_pe_gate_result=fail_no_valid_native_then_builtin_gate_result
candidate4b_wine_runs=no_exit_159
candidate4b_probe_root=logs/ableton-dxvk-pe-loader-probes/20260619-222841-candidate4b-bottles-soda-9-0-1-after-i686-loader-native_only
candidate4b_native_only_result=not_completed_no_result_env
candidate4b_native_then_builtin_result=not_run_no_result_env
candidate4b_pe_gate_result=fail_no_valid_native_then_builtin_gate_result
ableton_launched=no
working_prefix_touched=no
```

Interpretation: Installing `glibc.i686` resolves the literal
`/lib/ld-linux.so.2` absence, but it does not make either Candidate 4 runner pass
the loader gate. Candidate 4A can start far enough to produce a native-only
result, but copied DXVK is not mapped and the valid `n,b` gate does not complete.
Candidate 4B does not produce a candidate result before timeout. Treat both as
blocked at PE loader preflight, not as usability-tested runners.

Candidate 4 shim-entrypoint retest:

```text
shim_wineboot_replaced_with_wine64_wrapper=yes
candidate4a_runner=.local-runners/lutris-wine-7.2-2-wine64-shim
candidate4a_wine_version=wine-7.2-1-g1f8837bdccd (Staging)
candidate4a_pe_gate_result=fail_timeout_before_candidate_native_then_builtin_gate
candidate4a_native_only_result=not_completed_no_result_env
candidate4a_n_b_maps_d3d11=not_run_no_result_env
candidate4a_n_b_maps_dxgi=not_run_no_result_env
candidate4a_n_b_loads_wined3d=not_run_no_result_env
candidate4b_runner=.local-runners/bottles-soda-9.0-1-wine64-shim
candidate4b_wine_version=wine-experimental.bleeding.edge.9.0.93696.20240429 ( TkG Plain )
candidate4b_native_only_dxvk_hashes_match_source=yes
candidate4b_native_only_probe_exit_code=1
candidate4b_native_only_maps_d3d11=no
candidate4b_native_only_maps_dxgi=no
candidate4b_native_only_loads_wined3d=no
candidate4b_pe_gate_result=fail_timeout_before_candidate_native_then_builtin_result
candidate4b_n_b_maps_d3d11=not_completed_no_result_env
candidate4b_n_b_maps_dxgi=not_completed_no_result_env
candidate4b_n_b_loads_wined3d=not_completed_no_result_env
ableton_launched=no
working_prefix_touched=no
```

Interpretation: The shim-entrypoint fix did not unblock Candidate 4. It made
both shim `wine --version` commands use `wine64` successfully, but Candidate 4A
still timed out before producing a candidate result and Candidate 4B did not
reach a valid `native_then_builtin` gate. Do not treat either runner as passed
for DXVK comparison.

## Recommended next diagnostic

Do not run another Ableton usability test or another runner candidate yet.
Investigate runner PE/builtin resolution behavior before changing the harness or
running another candidate. The PE probe confirms that native-only `n` is not a
useful standalone control, and that Candidate 2's distinguishing failure surface
is `wined3d.dll` involvement under `n,b`.

## Audit summary

```text
DXVK_LOADER_AUDIT:
candidate1_status=blocked_backend_loader
candidate2_status=blocked_backend_loader
source_system32_d3d11_file=PE32+ executable for WINE (DLL), x86-64, 20 sections
source_system32_dxgi_file=PE32+ executable for WINE (DLL), x86-64, 20 sections
candidate2_system32_d3d11_file=PE32+ executable for WINE (DLL), x86-64, 20 sections
candidate2_system32_dxgi_file=PE32+ executable for WINE (DLL), x86-64, 20 sections
source_hashes_match_candidate2=yes
source_registry_dlloverrides=no d3d11/dxgi overrides
candidate2_registry_dlloverrides=no d3d11/dxgi overrides; unrelated runner-added native,builtin overrides present
loader_error_context=Native-only d3d11,dxgi=n fails in both rundll32 and PE LoadLibrary controls for system Wine and Candidate 2; PE n,b succeeds for both, but Candidate 2 loads wined3d.dll while system Wine does not
recommended_next_diagnostic=inspect alternate-runner PE/builtin resolution and wined3d involvement before any further Ableton launch
pe_loader_probe_build_available=yes
pe_loader_probe_result=system Wine n,b succeeds without wined3d; Candidate 2 n,b succeeds but loads wined3d
pe_loader_sequence_result=Candidate 2 maps copied dxgi before wined3d, then loads wined3d during dxgi load/attach; no native-load failure observed before wined3d
ableton_launched=no
working_prefix_touched=no
```

## Runner Candidate Conclusion

```text
RUNNER_CANDIDATE_CONCLUSION:
system_wine_11_staging=only known runner that launches Ableton
candidate1_status=blocked_backend_loader
candidate2_status=abandoned_for_official_comparison
candidate3_status=acquisition_blocked
candidate4a_status=blocked_pe_loader_preflight
candidate4b_status=blocked_pe_loader_preflight
candidate_runner_path_result=no alternate runner is currently eligible for Ableton usability testing
recommended_next_action=return to system Wine baseline and investigate the actual launch/usability failure surfaces
ableton_launched=no
working_prefix_touched=no
```

Loader-audit conclusion: no alternate runner is currently eligible for an
official Ableton usability test. Candidate 1 and Candidate 2 were blocked or
abandoned due DXVK/backend-loader behavior, Candidate 3 could not be acquired
without authenticated artifacts, and Candidate 4A/4B did not pass PE loader
preflight even after the i686 loader and local shim-entrypoint fixes.
