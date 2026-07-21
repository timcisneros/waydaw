# Ableton runner candidate plan

Prepared: 2026-06-19.

Goal: find a genuinely different Wine base where Ableton's failure mode changes.
This is a runner comparison plan only. Do not install, download, extract, launch,
or run a new runner until explicitly approved.

## Current baseline and stopped matrix

Baseline runner:

```text
system_wine_path=/usr/bin/wine
system_wine_version=wine-11.0 (Staging)
```

Local shim matrix status:

```text
A: failed — default WebView2, cursor guard off.
B: failed — WebView2 --disable-gpu, cursor guard off.
C: failed — default WebView2, cursor guard on.
```

Working conclusion: under system Wine `wine-11.0 (Staging)` with copied prefixes
and DXVK active, neither WebView2 `--disable-gpu` nor the X11 cursor guard is a
meaningful usability fix. The failure is deeper than these local shims. Stop the
local shim matrix unless Cell D is explicitly requested for formal closure.

## Rules for all runner candidates

- Use copied prefixes only through `bin/ableton-runner-test`.
- Keep prefix DXVK active.
- Do not force builtin `d3d11`/`dxgi`.
- Do not set `DXVK_LOG_LEVEL=none`.
- Do not use Wine virtual desktop.
- Do not change KWin geometry.
- Do not touch the working prefix.
- Start with prepare-only metadata checks before any Ableton launch.
- Record runner path, `wine --version`, source/download method, checksum,
  reversibility, and whether system packages are required.

Prepare-only metadata gate for any approved runner:

```bash
<runner>/bin/wine --version
./bin/ableton-runner-test \
  --runner <runner-path> \
  --label <candidate-label> \
  --webview2-mode default \
  --cursor-guard off \
  --prepare-only
```

Only after that metadata is reviewed should any `--run` be approved.

## Candidate 1 — recommended first test: Kron4ek Proton Experimental 11.0

Candidate class: Valve Experimental / Proton-style runner.

Source: `https://github.com/Kron4ek/Wine-Builds/releases`, tag
`proton-exp-11.0`.

Status: acquired and prepare-only checked on 2026-06-19. Not launched.

Why first:
- It is explicitly compiled from `ValveSoftware/wine`, so it is meaningfully
  different from the system `wine-11.0 (Staging)` even if the reported major
  version remains 11.0.
- It is distributed as a standalone tarball and does not require replacing the
  system Wine package.
- The release notes state that DXVK is not included, which is good for this
  investigation: the copied prefix's existing DXVK remains the active D3D layer.

Planned artifact:

```text
wine-proton-exp-11.0-amd64-wow64.tar.xz
sha256=0d3bf893abc0ff3bb72564c41a14f9f33bdf0246e080be18205019c81603447b
```

Planned local path:

```text
.local-runners/kron4ek-proton-exp-11.0/
```

Expected reversibility: remove the extracted `.local-runners/` directory and the
copied test prefix. No system packages expected.

Prepare-only metadata to record after approval:

```text
artifact_filename=wine-proton-exp-11.0-amd64-wow64.tar.xz
source_url=https://github.com/Kron4ek/Wine-Builds/releases/download/proton-exp-11.0/wine-proton-exp-11.0-amd64-wow64.tar.xz
local_path=.local-runners/wine-proton-exp-11.0-amd64-wow64.tar.xz
computed_sha256=0d3bf893abc0ff3bb72564c41a14f9f33bdf0246e080be18205019c81603447b
expected_sha256=0d3bf893abc0ff3bb72564c41a14f9f33bdf0246e080be18205019c81603447b
checksum_verified=yes
extracted=yes
extract_path=.local-runners/kron4ek-proton-exp-11.0/
resolved_wine_paths=.local-runners/kron4ek-proton-exp-11.0/bin/wine .local-runners/kron4ek-proton-exp-11.0/lib/wine/x86_64-unix/wine
runner_path=.local-runners/kron4ek-proton-exp-11.0
runner_bin_dir=.local-runners/kron4ek-proton-exp-11.0/bin
wine_version=wine-11.0-gd0c1d0160f9 (Proton)
different_from_system_wine_11_staging=yes_version_string_differs
source_download_method=GitHub release tarball
requires_system_packages=no
prepare_only_label=candidate1-kron4ek-proton-exp-11-prepare
prepare_only_ok=yes
test_prefix=/home/timcis/WinePrefixes/ableton12-candidate1-kron4ek-proton-exp-11-prepare-test
ableton_launched=no
working_prefix_touched=no
ready_for_candidate1_run=yes
expected_reversibility=remove .local-runners/kron4ek-proton-exp-11.0/ and copied test prefix
```

Candidate 1 acquisition audit:

```text
downloaded=yes
checksum_verified=yes
extracted=yes
runner_path=.local-runners/kron4ek-proton-exp-11.0/bin/wine
wine_version=wine-11.0-gd0c1d0160f9 (Proton)
prepare_only_ok=yes
ableton_launched=no
working_prefix_touched=no
ready_for_candidate1_run=yes
requires_system_packages=expected_no
```

Candidate 1 launch audit (2026-06-19): invalid pending backend fix.

```text
official_candidate1_result=invalid_pending_backend_fix
backend_effective=wined3d_builtin_likely
ableton_launched=yes_but_result_invalid
working_prefix_touched=no
```

Reason: the prepare-only prefix preserved the working DXVK DLL hashes, but the
actual Candidate 1 run prefix had `system32/d3d11.dll` and `system32/dxgi.dll`
replaced with Wine builtin DLL files at the runner launch time. The Candidate 1
launch segment had zero DXVK lines. Do not treat this as an official Candidate 1
comparison.

Backend audit file:

```text
logs/ableton-runner-tests/20260619-170001-candidate1-kron4ek-proton-exp-11-default-off/backend-audit.txt
```

Recommended future fix before rerun: add a controlled DXVK-enforcement launch
path for copied-prefix runner comparisons. After the runner prefix-update step,
verify copied-prefix `d3d11.dll`/`dxgi.dll` still match the working-prefix DXVK
hashes; if overwritten, restore the same DXVK DLLs into the copied prefix only,
then launch with `WINEDLLOVERRIDES=d3d11,dxgi=n`. This forces native prefix DXVK
and is distinct from the forbidden builtin override
`WINEDLLOVERRIDES=dxgi,d3d11=b`.

Harness status: `--enforce-dxvk` has been added for the Candidate 1 rerun path.
The original launch remains invalid. Rerun Candidate 1 only with:

```bash
./bin/ableton-runner-test \
  --runner .local-runners/kron4ek-proton-exp-11.0 \
  --label candidate1-kron4ek-proton-exp-11-dxvk-enforced \
  --webview2-mode default \
  --cursor-guard off \
  --enforce-dxvk \
  --run
```

Runner comparisons are invalid unless the copied-prefix DXVK hashes are verified
after runner prefix update.

Candidate 1 status: blocked, not failed.

```text
candidate=Kron4ek Proton Experimental 11.0
status=blocked_backend_loader
official_usability_result=no
reason=without enforcement runner overwrote DXVK with Wine builtin DLLs; with --enforce-dxvk hashes matched source but Ableton failed before launch with d3d11.dll not found / status c0000135
working_prefix_touched=no
```

Candidate 1 DXVK-enforced rerun attempt (2026-06-19):

```text
run_dir=logs/ableton-runner-tests/20260619-171522-candidate1-kron4ek-proton-exp-11-dxvk-enforced
dxvk_enforced=yes
dxvk_restored_after_runner_prefix_update=yes
dxvk_hashes_match_source=yes
launch_winedlloverrides=d3d11,dxgi=n
ableton_launched=no
window_detected=no
backend_effective=invalid_builtin_dll_for_dxvk_comparison
loader_error=d3d11.dll not found / status c0000135
```

This is not an official Candidate 1 usability result. The copied prefix's
system32 DXVK hashes matched source after restoration, but Proton Wine failed to
load `d3d11.dll` with native-only `d3d11,dxgi=n`.

Do not keep debugging Candidate 1 unless explicitly requested.

## Candidate 2 — Kron4ek Wine 11.11 staging-tkg

Candidate class: Wine-TKG style runner, newer non-system build.

Source: `https://github.com/Kron4ek/Wine-Builds/releases`, tag `11.11`.

Status: acquired and prepare-only checked on 2026-06-19. Not launched.

Why:
- This is not the system Wine build. It moves from system `wine-11.0 (Staging)`
  to Kron4ek `11.11` with staging-tkg patches.
- It is a standalone tarball with published SHA256 hashes.
- It keeps DXVK in the prefix because these Wine builds do not need to provide
  the D3D DLLs for this test.

Planned artifact:

```text
wine-11.11-staging-tkg-amd64-wow64.tar.xz
sha256=44f5330be22424c51d2b48ddc60dc4e1fca686628cedd9e76cd2b041a4aeb3d9
```

Planned local path:

```text
.local-runners/kron4ek-wine-11.11-staging-tkg/
```

Expected reversibility: remove the extracted `.local-runners/` directory and the
copied test prefix. No system packages expected.

Prepare-only metadata to record after approval:

```text
artifact_filename=wine-11.11-staging-tkg-amd64-wow64.tar.xz
source_url=https://github.com/Kron4ek/Wine-Builds/releases/download/11.11/wine-11.11-staging-tkg-amd64-wow64.tar.xz
local_path=.local-runners/wine-11.11-staging-tkg-amd64-wow64.tar.xz
computed_sha256=44f5330be22424c51d2b48ddc60dc4e1fca686628cedd9e76cd2b041a4aeb3d9
expected_sha256=44f5330be22424c51d2b48ddc60dc4e1fca686628cedd9e76cd2b041a4aeb3d9
checksum_verified=yes
extracted=yes
extract_path=.local-runners/kron4ek-wine-11.11-staging-tkg/
resolved_wine_paths=.local-runners/kron4ek-wine-11.11-staging-tkg/bin/wine .local-runners/kron4ek-wine-11.11-staging-tkg/lib/wine/x86_64-unix/wine
runner_path=.local-runners/kron4ek-wine-11.11-staging-tkg/bin/wine
runner_bin_dir=.local-runners/kron4ek-wine-11.11-staging-tkg/bin
wine_version=wine-11.11.r0.g4d000a90 ( TkG Staging NTsync )
different_from_system_wine_11_staging=yes
source_download_method=GitHub release tarball
requires_system_packages=no
prepare_only_label=candidate2-kron4ek-wine-11-11-prepare
prepare_only_ok=yes
test_prefix=/home/timcis/WinePrefixes/ableton12-candidate2-kron4ek-wine-11-11-prepare-test
ableton_launched=no
working_prefix_touched=no
ready_for_candidate2_run=yes
expected_reversibility=remove .local-runners/kron4ek-wine-11.11-staging-tkg/ and copied test prefix
```

Candidate 2 metadata audit:

```text
downloaded=yes
checksum_verified=yes
extracted=yes
runner_path=.local-runners/kron4ek-wine-11.11-staging-tkg/bin/wine
wine_version=wine-11.11.r0.g4d000a90 ( TkG Staging NTsync )
different_from_system_wine_11_staging=yes
prepare_only_ok=yes
ableton_launched=no
working_prefix_touched=no
ready_for_candidate2_run=yes
```

Candidate 2 status: blocked, not failed.

```text
candidate=Kron4ek Wine 11.11 staging-tkg
status=blocked_backend_loader
official_usability_result=no
reason=with --enforce-dxvk, copied-prefix DXVK hashes matched source but Ableton failed before launch; backend_effective=invalid_builtin_dll_for_dxvk_comparison; ableton_launched=no; window_detected=no
working_prefix_touched=no
```

Runner acquisition/runs are stopped pending DXVK loader audit. See
`docs/ableton-dxvk-loader-audit.md`.

Candidate 2 DXVK-enforced run attempt (2026-06-19): backend/loader failure, not
a usability result.

```text
run_dir=logs/ableton-runner-tests/20260619-172535-candidate2-kron4ek-wine-11-11-dxvk-enforced
dxvk_enforced=yes
dxvk_restored_after_runner_prefix_update=yes
dxvk_hashes_match_source=yes
launch_winedlloverrides=d3d11,dxgi=n
ableton_launched=no
window_detected=no
backend_effective=invalid_builtin_dll_for_dxvk_comparison
working_prefix_touched=no
```

The copied prefix's system32 DXVK hashes matched source after restoration, but
Ableton did not launch, so no live usability observation was requested.

Candidate 2 final decision (2026-06-19):

```text
Candidate 2 final status=abandoned_for_official_comparison
official_usability_result=no
reason=PE loader sequence shows Candidate 2 maps dxgi.dll, then loads wined3d.dll during DXGI load/attach before d3d11.dll; system Wine does not load wined3d in the same PE n,b control path
working_prefix_touched=no
```

Do not debug Candidate 2 further or run Candidate 2 usability tests unless
explicitly requested.

## Candidate 3 — Frogging-Family Wine-TKG Valve Exp Bleeding Edge

Candidate class: Wine-TKG / Valve Experimental / bleeding-edge runner.

Source: `https://github.com/Frogging-Family/wine-tkg-git`, workflow
`wine-valvexbe.yml`.

Why:
- This is the closest match to the desired Wine-TKG / Valve Experimental /
  Bleeding Edge class.
- It may include patches not present in plain Wine staging, Proton-GE 10-34, or
  the system Wine.

Acquisition status:
- Prebuilt releases were mostly replaced by CI.
- The GitHub Actions workflow page is public, but CI artifacts often require
  GitHub authentication and may expire.
- This candidate should start with an acquisition-only check, not a launch.

Planned local path if acquired:

```text
.local-runners/wine-tkg-valvexbe/
```

Expected reversibility: remove the extracted `.local-runners/` directory and the
copied test prefix. No system packages expected if a compatible prebuilt tarball
is acquired. If building locally is required, that becomes a separate approval
because it may require system build dependencies.

Prepare-only metadata to record after approval:

```text
runner_path=
wine_version=
different_from_system_wine_11_staging=yes/no
source_download_method=GitHub Actions artifact or local build
checksum_verified=yes/no/not_available
requires_system_packages=no_for_prebuilt / yes_for_local_build
```

Candidate 3 acquisition attempt (2026-06-19):

```text
candidate=Frogging-Family Wine-TKG Valve Exp Bleeding Edge
source_workflow=https://github.com/Frogging-Family/wine-tkg-git/actions/workflows/wine-valvexbe.yml
latest_successful_run_id=27850814211
latest_successful_run_number=2868
latest_successful_run_url=https://github.com/Frogging-Family/wine-tkg-git/actions/runs/27850814211
artifact_id=7759513604
artifact_name=wine-tkg-build
artifact_size_bytes=131941393
artifact_expired=false
artifact_created_at=2026-06-19T22:50:52Z
artifact_download_url=https://api.github.com/repos/Frogging-Family/wine-tkg-git/actions/artifacts/7759513604/zip
downloaded=no
download_result=blocked_http_401_auth_required
local_artifact=.local-runners/wine-tkg-valvexbe-27850814211-artifact.zip
local_artifact_created=no
sha256=not_available
checksum_verified=no
extracted=no
runner_path=not_resolved
wine_version=not_available
prepare_only_ok=no_not_run
pe_loader_preflight=not_run
candidate3_pe_gate_result=not_run
ableton_launched=no
working_prefix_touched=no
```

Interpretation: the public workflow metadata and non-expired artifact metadata
are visible, but the artifact archive requires GitHub authentication for
download. Do not switch to local build or another acquisition path without
separate approval.

Candidate 3 final acquisition status:

```text
Candidate 3 status=acquisition_blocked
official_usability_result=no
reason=GitHub Actions artifact metadata visible, but artifact archive download returned HTTP 401 authentication required; no local artifact, no SHA256, no extraction, no prepare-only, no PE gate
ableton_launched=no
working_prefix_touched=no
```

## Candidate 4 — older non-11 staging base: Lutris Wine 7.2-2 or Bottles Soda 9.0-1

Candidate class: older non-11 Wine base / launcher-provided runner.

Sources:
- Lutris Wine releases: `https://github.com/lutris/wine/releases`
- Bottles Wine/Soda releases: `https://github.com/bottlesdevs/wine`

Why:
- Useful only if the first two candidates do not change the failure. This tests
  whether the regression is specific to newer Wine 11 staging behavior.
- Lutris Wine 7.2-2 is based on Wine Staging 7.2. Bottles Soda 9.0-1 is a
  launcher-provided build class, but the exact runner layout and `wine --version`
  must be verified before any launch.

Risks:
- Older Wine bases may fail earlier with WebView2 or Ableton loader behavior.
- This is lower priority than a Valve/Proton/TKG branch because success on an
  old base may be less actionable.

Planned local paths:

```text
.local-runners/lutris-wine-7.2-2/
.local-runners/bottles-soda-9.0-1/
```

Expected reversibility: remove the extracted `.local-runners/` directory and the
copied test prefix. No system packages expected if standalone tarballs are used.
Do not install the Lutris or Bottles application just to test these unless a
standalone runner cannot be acquired and the install is separately approved.

Prepare-only metadata to record after approval:

```text
runner_path=
wine_version=
different_from_system_wine_11_staging=yes
source_download_method=GitHub release tarball or launcher-managed runner
checksum_verified=yes/no/not_available
requires_system_packages=expected_no_for_tarball
```

Candidate 4 acquisition/preflight attempt (2026-06-19):

```text
Candidate 4A status=blocked_pe_loader_preflight
candidate4_selected=Lutris Wine 7.2-2
selected=Lutris Wine 7.2-2
source_url=https://github.com/lutris/wine/releases/download/lutris-wine-7.2-2/wine-lutris-7.2-2-x86_64.tar.xz
artifact_filename=wine-lutris-7.2-2-x86_64.tar.xz
artifact_size_bytes=288951088
local_artifact=.local-runners/wine-lutris-7.2-2-x86_64.tar.xz
sha256=3a1428358f52c055f7b8f4368291746e9fd9d1db85ae63d5145157f9ed1a8a12
checksum_verified=no_expected_checksum_not_published_in_release_metadata
extracted=yes
extract_path=.local-runners/lutris-wine-7.2-2/
resolved_wine_paths=.local-runners/lutris-wine-7.2-2/bin/wine .local-runners/lutris-wine-7.2-2/bin/wine64
runner_default_wine_status=blocked_missing_32bit_loader_/lib/ld-linux.so.2
runner_shim=.local-runners/lutris-wine-7.2-2-wine64-shim
runner_path_for_harness=.local-runners/lutris-wine-7.2-2-wine64-shim
wine_version=wine-7.2-1-g1f8837bdccd (Staging)
different_from_system_wine_11_staging=yes
requires_system_packages=no_for_acquisition; runtime_missing_/lib/ld-linux.so.2_for_this_runner
prepare_only_label=candidate4-lutris-wine-7-2-2-prepare
prepare_only_ok=yes
prepare_only_test_prefix=/home/timcis/WinePrefixes/ableton12-candidate4-lutris-wine-7-2-2-prepare-test
pe_probe_run_root=logs/ableton-dxvk-pe-loader-probes/20260619-220005-candidate4-lutris-wine-7-2-2-*
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
reason=acquired and prepare-only passed, but PE loader gate failed before copied DXVK could map because runner requires /lib/ld-linux.so.2
ableton_launched=no
working_prefix_touched=no
```

Restore/removal commands for this local acquisition:

```bash
rm -rf .local-runners/lutris-wine-7.2-2/ .local-runners/lutris-wine-7.2-2-wine64-shim
rm -f .local-runners/wine-lutris-7.2-2-x86_64.tar.xz
rm -rf "$HOME/WinePrefixes/ableton12-candidate4-lutris-wine-7-2-2-prepare-test"
rm -rf "$HOME/WinePrefixes"/ableton12-pe-loader-probe-candidate4-lutris-wine-7-2-2-*-20260619-220005
```

Interpretation: Candidate 4 Lutris Wine 7.2-2 was acquired and prepare-only
checked, but it fails the required PE loader gate before DXVK can be mapped. Do
not launch Ableton with this runner unless explicitly approved after addressing
the missing 32-bit loader/runtime issue.

Candidate 4B acquisition/preflight attempt (2026-06-19):

```text
candidate4b_selected=Bottles Soda 9.0-1
component_metadata_url=https://raw.githubusercontent.com/bottlesdevs/components/main/runners/wine/soda-9.0-1.yml
component_file_name=soda-9.0-1-x86_64.tar.xz
component_url=https://github.com/bottlesdevs/wine/releases/download/soda-9.0-1/soda-9.0-1-x86_64.tar.xz
component_file_checksum=8806df3e294dd37cf461ed3432d65318
component_file_checksum_type=md5
component_file_size=61960416
local_artifact=.local-runners/soda-9.0-1-x86_64.tar.xz
local_file_size=64564696
local_file_size_matches_component=no
md5=8806df3e294dd37cf461ed3432d65318
md5_verified=yes
sha256=c38fe0ad3c12a49b61ec1fcaea5c5d8da4a3d1afc5991befe2af6b125f014c28
extracted=yes
extract_path=.local-runners/bottles-soda-9.0-1/
resolved_wine_paths=.local-runners/bottles-soda-9.0-1/bin/wine .local-runners/bottles-soda-9.0-1/bin/wine64
runner_default_wine_status=blocked_missing_32bit_loader_/lib/ld-linux.so.2
runner_shim=.local-runners/bottles-soda-9.0-1-wine64-shim
runner_path_for_harness=.local-runners/bottles-soda-9.0-1-wine64-shim
wine_version=wine-experimental.bleeding.edge.9.0.93696.20240429 ( TkG Plain )
different_from_system_wine_11_staging=yes
requires_system_packages=no_for_acquisition; runtime_missing_/lib/ld-linux.so.2_for_this_runner
prepare_only_label=candidate4b-bottles-soda-9-0-1-prepare
prepare_only_ok=yes
prepare_only_test_prefix=/home/timcis/WinePrefixes/ableton12-candidate4b-bottles-soda-9-0-1-prepare-test
pe_probe_run_root=logs/ableton-dxvk-pe-loader-probes/20260619-220917-candidate4b-bottles-soda-9-0-1-*
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

Restore/removal commands for this local acquisition:

```bash
rm -rf .local-runners/bottles-soda-9.0-1/ .local-runners/bottles-soda-9.0-1-wine64-shim
rm -f .local-runners/soda-9.0-1-x86_64.tar.xz
rm -rf "$HOME/WinePrefixes/ableton12-candidate4b-bottles-soda-9-0-1-prepare-test"
rm -rf "$HOME/WinePrefixes"/ableton12-pe-loader-probe-candidate4b-bottles-soda-9-0-1-*-20260619-220917
```

Interpretation: Candidate 4B was acquired and the Bottles component MD5 was
verified, but it fails the same PE loader gate as Candidate 4A before copied
DXVK can be mapped. Do not launch Ableton with this runner unless explicitly
approved after addressing the missing 32-bit loader/runtime issue.

Candidate 4 i686 loader retest (2026-06-19):

```text
ld_linux_so_2_present=yes
glibc_i686_installed=glibc-2.43-6.fc44.i686
candidate4a_default_wine_runs=no_exit_159
candidate4b_default_wine_runs=no_exit_159
candidate4a_after_i686_probe_root=logs/ableton-dxvk-pe-loader-probes/20260619-221914-candidate4a-lutris-wine-7-2-2-after-i686-loader-*
candidate4a_native_only_dxvk_hashes_match_source=yes
candidate4a_native_only_probe_exit_code=1
candidate4a_native_only_maps_d3d11=no
candidate4a_native_only_maps_dxgi=no
candidate4a_native_only_loads_wined3d=no
candidate4a_native_only_error=run_wineboot_boot_event_wait_timed_out_then_c0000135_for_dxgi_and_d3d11
candidate4a_native_then_builtin_result=not_completed_no_result_env
candidate4a_pe_gate_result=fail_no_valid_native_then_builtin_gate_result
candidate4b_after_i686_probe_root=logs/ableton-dxvk-pe-loader-probes/20260619-222841-candidate4b-bottles-soda-9-0-1-after-i686-loader-native_only
candidate4b_native_only_result=not_completed_no_result_env
candidate4b_native_then_builtin_result=not_run_no_result_env
candidate4b_pe_gate_result=fail_no_valid_native_then_builtin_gate_result
ableton_launched=no
working_prefix_touched=no
```

Interpretation: Installing `glibc.i686` made `/lib/ld-linux.so.2` present, but
it did not produce a valid Candidate 4 PE loader gate. Both standalone runners'
default `bin/wine --version` still exits 159. Candidate 4A reached a native-only
probe result with copied DXVK hashes restored, but did not map copied
`d3d11.dll` or `dxgi.dll`; its `n,b` gate did not complete. Candidate 4B did
not produce a candidate result before timeout. Do not launch Ableton with either
Candidate 4 runner until the remaining standalone-runner runtime/prefix-update
failure is understood.

Candidate 4 shim-entrypoint retest (2026-06-22):

```text
shim_wineboot_replaced_with_wine64_wrapper=yes
candidate4a_runner=.local-runners/lutris-wine-7.2-2-wine64-shim
candidate4a_wine_version=wine-7.2-1-g1f8837bdccd (Staging)
candidate4a_pe_probe_root=logs/ableton-dxvk-pe-loader-probes/20260622-220446-candidate4a-lutris-wine-7-2-2-wine64-wrapper-gate-native_only
candidate4a_pe_gate_result=fail_timeout_before_candidate_native_then_builtin_gate
candidate4a_native_only_result=not_completed_no_result_env
candidate4a_n_b_maps_d3d11=not_run_no_result_env
candidate4a_n_b_maps_dxgi=not_run_no_result_env
candidate4a_n_b_loads_wined3d=not_run_no_result_env
candidate4b_runner=.local-runners/bottles-soda-9.0-1-wine64-shim
candidate4b_wine_version=wine-experimental.bleeding.edge.9.0.93696.20240429 ( TkG Plain )
candidate4b_pe_probe_root=logs/ableton-dxvk-pe-loader-probes/20260622-220854-candidate4b-bottles-soda-9-0-1-wine64-wrapper-gate-*
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

Interpretation: The local shim hypothesis was partially valid: the previous
shim `wineboot` entrypoints pointed at the runner `wineboot` scripts, and those
scripts prefer `wine` before `wine64`. Replacing only the local shim `wine` and
`wineboot` entries with explicit `wine64` wrappers made both shim
`wine --version` checks pass. It did not make either Candidate 4 runner pass the PE
loader gate. Candidate 4A still timed out in the candidate gate path before a
result file. Candidate 4B reached a native-only probe result, but failed to map
copied DXVK and timed out before producing a valid `n,b` gate result.

Restore commands for the shim-entrypoint mutation:

```bash
ln -sfn ../lutris-wine-7.2-2/bin/wine64 .local-runners/lutris-wine-7.2-2-wine64-shim/wine
ln -sfn ../lutris-wine-7.2-2/bin/wineboot .local-runners/lutris-wine-7.2-2-wine64-shim/wineboot
ln -sfn ../bottles-soda-9.0-1/bin/wine64 .local-runners/bottles-soda-9.0-1-wine64-shim/wine
ln -sfn ../bottles-soda-9.0-1/bin/wineboot .local-runners/bottles-soda-9.0-1-wine64-shim/wineboot
```

Runner candidate conclusion (2026-06-22):

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

Interpretation: Runner-candidate exploration is closed for now. Keep the
acquired artifacts and copied test prefixes intact, but do not run or acquire
more alternate runners unless explicitly approved. The only currently runnable
Ableton baseline is system Wine 11.0 Staging with existing DXVK.
