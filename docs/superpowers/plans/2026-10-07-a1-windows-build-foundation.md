# A-1: Windows Build Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build upstream bbport 0.3's GPU library, `bb-gpu-capabilities.exe` and the device-less renderer tests with MSYS2 CLANG64 on Windows, run them on this laptop, and have Windows + Linux-compile CI green — without touching the C runtime yet (that is plan A-2/A-3).

**Architecture:** A root `CMakeLists.txt` for Windows wraps the existing `gpu/CMakeLists.txt` (which gains `if(WIN32)` branches: static `libbbgpu.a`, pinned submodules for the three header-only libraries MSYS2 lacks, no X11). Linux-only code in `gpu/` is routed through a tiny platform facade (`gpu/shim/bbport_platform.h`, Windows implementation in `gpu/shim/win32/`), the Linux-only diagnostic modules are replaced by stubs on Windows, and the `sigsetjmp` recovery points become a `BbRecoverBuf`/`BB_RECOVER_SET` abstraction whose Windows implementation arrives in plan A-3. Linux keeps compiling (verified by CI) because every change is behind `#ifdef _WIN32` or is a pure bug fix.

**Tech Stack:** MSYS2 CLANG64 (clang ≥ 20, libc++, lld, ThinLTO optional), CMake ≥ 3.24, Ninja, Python 3.12+, SDL3, Vulkan SDK headers ≥ 1.4.350 (MSYS2 packages), GitHub Actions (`msys2/setup-msys2`, `cachix/install-nix-action`).

Spec: `docs/superpowers/specs/2026-10-07-windows-host-layer-design.md` (sections 5.7, 5.8, 5.9 and 7 are what this plan implements). Plans A-2 (host abstraction), A-3 (Win32 host layer) and A-4 (boot to gameplay) follow.

## Global Constraints

- Toolchain: MSYS2 CLANG64 only — clang (≥ 20; MSYS2 ships 22), libc++, lld; MSVC and MINGW64/UCRT64 GCC are not supported. vulkan-headers ≥ 1.4.350. CMake ≥ 3.24, Ninja.
- Every Windows-specific line lives behind `#ifdef _WIN32` / `if (WIN32)`, preferably in separate files (`gpu/shim/win32/`, `tools/windows/`, `.github/workflows/windows.yml`); Linux behaviour is unchanged except for the three pure bug fixes named in Task 9 (which upstream's own code motivates).
- `gpu/` never includes anything from `src/host/`; the loader↔GPU contract stays the C interface in `gpu/bbgpu.h` plus `extern "C"` declarations in `gpu/shim/*.h`.
- No game files, no NVIDIA/AMD DLLs, no artwork in the repository or in CI artifacts. The game's trademark is not used in project, binary or package names (the fork is `bbport-windows`).
- Borrowed designs (yumlevi PR #6, Supermedo, yaonikaixin, DarkIzuku, shadPS4 — all GPL-2.0-or-later) are credited in the file header of the file that uses them and in `THIRD_PARTY.md`; code is written for this tree, not pasted.
- Builds run inside the CLANG64 environment through `tools/windows/clang64.ps1`; the build directory is `out/win` (Linux's `build.sh` keeps `out/gpu` and `out/`).
- Exit codes and log lines printed by the GPU library stay as upstream prints them.
- Commit after every task with the message given in the task; every commit message ends with:
  `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>` and `Claude-Session: https://claude.ai/code/session_01Dc73uDsGqfXthUPderW4n7`.

---

## File structure

| Path | Responsibility |
|---|---|
| `msys2-packages.txt` | The pacman package list (one per line), shared by the setup script and CI |
| `tools/windows/setup-msys2.ps1` | Installs MSYS2 into `C:\msys64` (or `BB_MSYS2`) and the packages; idempotent |
| `tools/windows/clang64.ps1` | Runs one command line inside the CLANG64 shell from PowerShell, cwd = repo root |
| `tools/windows/build.ps1` | `cmake` configure + `ninja` for `out/win` through `clang64.ps1` |
| `tools/windows/check_toolchain.py` | Verifies compilers, tools and package versions; exit 1 with a table of what is missing |
| `scripts/apply_vendor_patches.py` | Applies `gpu/patches/fsr-vulkan/*.patch` to the submodule idempotently (what `build.sh` lines 37–41 do in bash) |
| `tests/test_apply_vendor_patches.py` | Unit test for the patch script |
| `gpu/third_party/{magic_enum,miniz,xbyak}` | Pinned submodules for the header-only libraries MSYS2 does not package |
| `CMakeLists.txt` (root) | Windows project: adds `gpu/`, builds `bb-gpu-capabilities.exe`, registers CTest tests |
| `gpu/CMakeLists.txt` | `if (WIN32)` branches: dependencies, static library, Windows defines/libs, excluded Linux-only sources, FidelityFX include workarounds |
| `gpu/shim/bbport_platform.h` | Platform facade: thread ids, CPU time, resource usage, address description, thread names, backtraces, safe memory reads; Linux versions inline |
| `gpu/shim/win32/bbport_platform_win32.cpp` | Windows implementation of the facade and of `BbThreads` |
| `gpu/shim/win32/bbport_diag_win32.cpp` | Windows stubs for `BbFreeCheck`, `BbGuestMemory`, `BbGuestHooks`, `BbWaitTrace` (Linux-only diagnostics) |
| `gpu/shim/bbport_threads.h` | `BbThreads::Available/MakeBackground` declared for Windows, inline for Linux |
| `gpu/shim/bbport_toggles.h` | `BbRecoverBuf` + `BB_RECOVER_SET` recovery-point abstraction |
| `tests/test_platform_win32.cpp` | Unit test of the facade (Windows only) |
| `tests/test_gpu_runtime_stubs.cpp` | Renderer-test stubs, Windows variant of the recovery symbols |
| `.github/workflows/windows.yml`, `.github/workflows/linux-compile.yml` | CI |
| `README-Windows.md`, `THIRD_PARTY.md` | Developer setup; attribution |

---

### Task 1: MSYS2 CLANG64 toolchain, shell wrapper and toolchain check

**Files:**
- Create: `msys2-packages.txt`
- Create: `tools/windows/setup-msys2.ps1`
- Create: `tools/windows/clang64.ps1`
- Create: `tools/windows/check_toolchain.py`

**Interfaces:**
- Produces: `tools/windows/clang64.ps1 "<bash command line>"` — runs the command in the CLANG64 environment with the repository root as cwd, returns its exit code. Every later task's build/test commands use it.
- Produces: `python tools/windows/check_toolchain.py` — exit 0 when the toolchain is complete.

- [ ] **Step 1: Write the package list**

`msys2-packages.txt`:
```
# MSYS2 CLANG64 packages for the Windows build (tools/windows/setup-msys2.ps1, .github/workflows/windows.yml)
git
curl
mingw-w64-clang-x86_64-clang
mingw-w64-clang-x86_64-lld
mingw-w64-clang-x86_64-libc++
mingw-w64-clang-x86_64-cmake
mingw-w64-clang-x86_64-ninja
mingw-w64-clang-x86_64-pkgconf
mingw-w64-clang-x86_64-python
mingw-w64-clang-x86_64-sdl3
mingw-w64-clang-x86_64-boost
mingw-w64-clang-x86_64-fmt
mingw-w64-clang-x86_64-glslang
mingw-w64-clang-x86_64-spirv-cross
mingw-w64-clang-x86_64-spirv-headers
mingw-w64-clang-x86_64-vulkan-headers
mingw-w64-clang-x86_64-vulkan-loader
mingw-w64-clang-x86_64-vulkan-memory-allocator
mingw-w64-clang-x86_64-xxhash
mingw-w64-clang-x86_64-zydis
mingw-w64-clang-x86_64-robin-map
mingw-w64-clang-x86_64-ffmpeg
```

- [ ] **Step 2: Write the shell wrapper**

`tools/windows/clang64.ps1`:
```powershell
# Runs one command line inside the MSYS2 CLANG64 environment with the repository root as the
# working directory, e.g.  tools\windows\clang64.ps1 "cmake --version && ninja --version".
param([Parameter(Mandatory = $true, ValueFromRemainingArguments = $true)][string[]]$Command)
$root = if ($env:BB_MSYS2) { $env:BB_MSYS2 } else { 'C:\msys64' }
$bash = Join-Path $root 'usr\bin\bash.exe'
if (-not (Test-Path $bash)) {
    Write-Error "MSYS2 not found at $root (run tools\windows\setup-msys2.ps1 or set BB_MSYS2)"
    exit 1
}
Set-Location (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))
$env:MSYSTEM = 'CLANG64'
$env:CHERE_INVOKING = '1'
$env:MSYS2_PATH_TYPE = 'minimal'
& $bash -lc ($Command -join ' ')
exit $LASTEXITCODE
```

- [ ] **Step 3: Write the toolchain check (the test for this task)**

`tools/windows/check_toolchain.py`:
```python
"""Checks the MSYS2 CLANG64 toolchain the Windows build needs. Run inside CLANG64:
    tools\\windows\\clang64.ps1 "python tools/windows/check_toolchain.py"
Exit 0 when everything is present, 1 with a table of what is missing or too old."""
import re
import shutil
import subprocess
import sys

MIN_CLANG = 20
MIN_CMAKE = (3, 24)
MIN_VULKAN_HEADER = 350  # VK_HEADER_VERSION of vulkan-headers 1.4.350


def run(args):
    try:
        return subprocess.run(args, capture_output=True, text=True, check=False).stdout
    except OSError:
        return ''


def version_tuple(text):
    match = re.search(r'(\d+)\.(\d+)(?:\.(\d+))?', text)
    return tuple(int(x or 0) for x in match.groups()) if match else ()


def vulkan_header_version():
    for prefix in ('/clang64/include', '/mingw64/include', '/usr/include'):
        try:
            with open(f'{prefix}/vulkan/vulkan_core.h', encoding='utf-8') as f:
                for line in f:
                    m = re.match(r'#define VK_HEADER_VERSION (\d+)', line)
                    if m:
                        return int(m.group(1))
        except OSError:
            continue
    return 0


def main():
    rows = []
    ok = True

    def check(name, present, detail):
        nonlocal ok
        rows.append((name, 'ok' if present else 'MISSING', detail))
        ok &= present

    clang = version_tuple(run(['clang', '--version']))
    check('clang', bool(clang) and clang[0] >= MIN_CLANG, f'{clang or "not found"} (need >= {MIN_CLANG})')
    check('clang++ uses libc++', 'libc++' in run(['clang++', '-print-resource-dir']) or
          shutil.which('clang++') is not None and 'clang64' in (shutil.which('clang++') or ''),
          shutil.which('clang++') or 'not found')
    check('lld', shutil.which('ld.lld') is not None, shutil.which('ld.lld') or 'not found')
    cmake = version_tuple(run(['cmake', '--version']))
    check('cmake', bool(cmake) and cmake[:2] >= MIN_CMAKE, f'{cmake or "not found"} (need >= {MIN_CMAKE})')
    check('ninja', shutil.which('ninja') is not None, run(['ninja', '--version']).strip() or 'not found')
    check('pkg-config', shutil.which('pkg-config') is not None, shutil.which('pkg-config') or 'not found')
    for module in ('sdl3', 'vulkan', 'libxxhash', 'libavformat', 'libavcodec', 'libavutil', 'libswscale', 'libswresample'):
        version = run(['pkg-config', '--modversion', module]).strip()
        check(f'pkg-config {module}', bool(version), version or 'not found')
    glslang = shutil.which('glslang') or shutil.which('glslangValidator')
    check('glslang', glslang is not None, glslang or 'not found')
    header = vulkan_header_version()
    check('vulkan-headers', header >= MIN_VULKAN_HEADER, f'VK_HEADER_VERSION {header} (need >= {MIN_VULKAN_HEADER})')
    for header_file, name in (('/clang64/include/boost/version.hpp', 'boost'),
                              ('/clang64/include/fmt/format.h', 'fmt'),
                              ('/clang64/include/tsl/robin_map.h', 'robin-map'),
                              ('/clang64/include/Zydis/Zydis.h', 'zydis'),
                              ('/clang64/include/vk_mem_alloc.h', 'vulkan-memory-allocator'),
                              ('/clang64/include/spirv-headers/spirv/unified1/spirv.h', 'spirv-headers'),
                              ('/clang64/include/spirv_cross/spirv_cross.hpp', 'spirv-cross')):
        try:
            open(header_file, encoding='utf-8').close()
            present = True
        except OSError:
            present = False
        check(name, present, header_file)
    python = version_tuple(sys.version)
    check('python', python >= (3, 12), f'{python}')
    check('git', shutil.which('git') is not None, shutil.which('git') or 'not found')

    width = max(len(r[0]) for r in rows)
    for name, status, detail in rows:
        print(f'{name:<{width}}  {status:<8}  {detail}')
    print('toolchain complete' if ok else 'toolchain incomplete')
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
```

- [ ] **Step 4: Run the check to see it fail (MSYS2 is not installed on this laptop)**

Run: `powershell -File tools\windows\clang64.ps1 "python tools/windows/check_toolchain.py"`
Expected: `MSYS2 not found at C:\msys64 ...` and exit code 1.

- [ ] **Step 5: Write the setup script**

`tools/windows/setup-msys2.ps1`:
```powershell
# Installs MSYS2 (when missing) and the CLANG64 packages of msys2-packages.txt. Idempotent:
# re-running updates the packages. Needs ~6 GB of disk and an internet connection.
param([string]$Root = $(if ($env:BB_MSYS2) { $env:BB_MSYS2 } else { 'C:\msys64' }))
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$bash = Join-Path $Root 'usr\bin\bash.exe'
if (-not (Test-Path $bash)) {
    $installer = Join-Path $env:TEMP 'msys2-x86_64-latest.exe'
    Write-Host "Downloading the MSYS2 installer to $installer"
    Invoke-WebRequest -Uri 'https://github.com/msys2/msys2-installer/releases/latest/download/msys2-x86_64-latest.exe' -OutFile $installer
    Write-Host "Installing MSYS2 into $Root"
    & $installer in --confirm-command --accept-messages --root ($Root -replace '\\', '/')
    if ($LASTEXITCODE -ne 0) { throw "MSYS2 installer exited with $LASTEXITCODE" }
}
$env:MSYSTEM = 'CLANG64'
$env:CHERE_INVOKING = '1'
$env:MSYS2_PATH_TYPE = 'minimal'
# The first core update may close the shell to replace the runtime; the second pass finishes it.
& $bash -lc 'pacman -Syuu --noconfirm' | Out-Host
& $bash -lc 'pacman -Syuu --noconfirm' | Out-Host
if ($LASTEXITCODE -ne 0) { throw "pacman -Syuu exited with $LASTEXITCODE" }
$packages = (Get-Content (Join-Path $repo 'msys2-packages.txt') |
    Where-Object { $_.Trim() -and -not $_.Trim().StartsWith('#') }) -join ' '
& $bash -lc "pacman -S --needed --noconfirm $packages" | Out-Host
if ($LASTEXITCODE -ne 0) { throw "pacman -S exited with $LASTEXITCODE" }
Write-Host "MSYS2 CLANG64 ready in $Root"
```

- [ ] **Step 6: Run the setup (10–20 minutes; needs the network)**

Run: `powershell -ExecutionPolicy Bypass -File tools\windows\setup-msys2.ps1`
Expected: ends with `MSYS2 CLANG64 ready in C:\msys64`. If the installer is denied by the permission system, say so and stop — do not try other install channels.

- [ ] **Step 7: Run the check to see it pass**

Run: `powershell -File tools\windows\clang64.ps1 "python tools/windows/check_toolchain.py"`
Expected: every row `ok`, last line `toolchain complete`, exit 0. Record the printed clang, cmake and VK_HEADER_VERSION values in the commit message body.

- [ ] **Step 8: Commit**

```bash
git add msys2-packages.txt tools/windows/setup-msys2.ps1 tools/windows/clang64.ps1 tools/windows/check_toolchain.py
git commit -m "build(windows): MSYS2 CLANG64 toolchain setup, shell wrapper and toolchain check"
```

---

### Task 2: Pinned submodules and the vendor patch script

**Files:**
- Modify: `.gitmodules`
- Create: `gpu/third_party/magic_enum`, `gpu/third_party/miniz`, `gpu/third_party/xbyak` (submodules)
- Create: `scripts/apply_vendor_patches.py`
- Create: `tests/test_apply_vendor_patches.py`

**Interfaces:**
- Produces: CMake targets `magic_enum::magic_enum`, `miniz::miniz`, `xbyak::xbyak` via `add_subdirectory` (Task 5).
- Produces: `python scripts/apply_vendor_patches.py` — applies every `gpu/patches/fsr-vulkan/*.patch` not yet applied; exit 0 when the tree is patched. Function `apply_patches(submodule: Path, patch_dir: Path) -> int` returns the number of patches applied this run.

- [ ] **Step 1: Write the failing test for the patch script**

`tests/test_apply_vendor_patches.py`:
```python
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'scripts'))
from apply_vendor_patches import apply_patches  # noqa: E402


def git(repo, *args):
    return subprocess.run(['git', '-C', str(repo), *args], check=True, capture_output=True, text=True).stdout


class ApplyVendorPatchesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name) / 'sub'
        self.repo.mkdir()
        git(self.repo, 'init', '-q')
        git(self.repo, 'config', 'user.email', 'test@example.com')
        git(self.repo, 'config', 'user.name', 'test')
        (self.repo / 'a.txt').write_text('one\n')
        git(self.repo, 'add', 'a.txt')
        git(self.repo, 'commit', '-q', '-m', 'base')
        (self.repo / 'a.txt').write_text('one\ntwo\n')
        patch = git(self.repo, 'diff')
        git(self.repo, 'checkout', '--', 'a.txt')
        self.patches = Path(self.tmp.name) / 'patches'
        self.patches.mkdir()
        (self.patches / '0001-add-two.patch').write_text(patch)

    def tearDown(self):
        self.tmp.cleanup()

    def test_applies_once_then_is_idempotent(self):
        self.assertEqual(apply_patches(self.repo, self.patches), 1)
        self.assertEqual((self.repo / 'a.txt').read_text(), 'one\ntwo\n')
        self.assertEqual(apply_patches(self.repo, self.patches), 0)
        self.assertEqual((self.repo / 'a.txt').read_text(), 'one\ntwo\n')

    def test_no_patches_is_a_noop(self):
        empty = Path(self.tmp.name) / 'none'
        empty.mkdir()
        self.assertEqual(apply_patches(self.repo, empty), 0)


if __name__ == '__main__':
    unittest.main()
```

- [ ] **Step 2: Run the test to see it fail**

Run: `python -m unittest tests.test_apply_vendor_patches -v`
Expected: `ModuleNotFoundError: No module named 'apply_vendor_patches'`.

- [ ] **Step 3: Write the patch script**

`scripts/apply_vendor_patches.py`:
```python
"""Applies this port's patches to the FSR-Vulkan submodule's working tree once (what build.sh does
on Linux): a patch that already applies in reverse is skipped. Usage: python scripts/apply_vendor_patches.py"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _git(repo, *args):
    return subprocess.run(['git', '-C', str(repo), *args], capture_output=True, text=True, check=False)


def apply_patches(submodule, patch_dir):
    """Returns the number of patches applied this run; raises RuntimeError when one does not apply."""
    applied = 0
    for patch in sorted(Path(patch_dir).glob('*.patch')):
        path = str(Path(patch).resolve())
        if _git(submodule, 'apply', '--reverse', '--check', path).returncode == 0:
            continue
        result = _git(submodule, 'apply', path)
        if result.returncode != 0:
            raise RuntimeError(f'{patch.name} does not apply to {submodule}:\n{result.stderr}')
        applied += 1
    return applied


def main():
    submodule = ROOT / 'gpu' / 'third_party' / 'fsr-vulkan'
    if not (submodule / 'CMakeLists.txt').exists():
        print('gpu/third_party/fsr-vulkan is empty: run git submodule update --init --recursive', file=sys.stderr)
        return 1
    n = apply_patches(submodule, ROOT / 'gpu' / 'patches' / 'fsr-vulkan')
    print(f'FSR-Vulkan patches: {n} applied, tree up to date')
    return 0


if __name__ == '__main__':
    sys.exit(main())
```

- [ ] **Step 4: Run the test to see it pass**

Run: `python -m unittest tests.test_apply_vendor_patches -v`
Expected: `test_applies_once_then_is_idempotent ... ok`, `test_no_patches_is_a_noop ... ok`.

- [ ] **Step 5: Add the three submodules at pinned tags**

```bash
git submodule add https://github.com/Neargye/magic_enum.git gpu/third_party/magic_enum
git -C gpu/third_party/magic_enum checkout v0.9.7
git submodule add https://github.com/richgel999/miniz.git gpu/third_party/miniz
git -C gpu/third_party/miniz checkout 3.1.0
git submodule add https://github.com/herumi/xbyak.git gpu/third_party/xbyak
git -C gpu/third_party/xbyak checkout v7.24.2
git add .gitmodules gpu/third_party/magic_enum gpu/third_party/miniz gpu/third_party/xbyak
```
Expected: `git submodule status` lists the three paths with the tag names in parentheses.

- [ ] **Step 6: Apply the FSR-Vulkan patch and verify idempotence on the real tree**

Run: `python scripts/apply_vendor_patches.py` twice.
Expected: first run `FSR-Vulkan patches: 1 applied, tree up to date`, second run `FSR-Vulkan patches: 0 applied, tree up to date`. (`git status` inside the submodule shows the patched files modified; that is expected and is how `build.sh` leaves it on Linux.)

- [ ] **Step 7: Commit**

```bash
git add .gitmodules gpu/third_party/magic_enum gpu/third_party/miniz gpu/third_party/xbyak scripts/apply_vendor_patches.py tests/test_apply_vendor_patches.py
git commit -m "build(windows): pinned magic_enum/miniz/xbyak submodules and an idempotent vendor patch script"
```

---

### Task 3: Root CMake project and the first Windows executable (`bb-gpu-capabilities.exe`)

**Files:**
- Create: `CMakeLists.txt` (repository root)
- Create: `tools/windows/build.ps1`
- Test: CTest `gpu-capabilities-gamepads`

**Interfaces:**
- Produces: `tools/windows/build.ps1 [-Target <ninja target>] [-Lto]` — configures `out/win` and builds the target (default `all`).
- Produces: root CMake variables for later tasks: `enable_testing()`, `BB_LTO` option passed down to `gpu/`.

- [ ] **Step 1: Write the root CMakeLists.txt (gpu/ is added in Task 5; here only the tool builds)**

`CMakeLists.txt`:
```cmake
# bbport-windows: the Windows build (MSYS2 CLANG64). Linux keeps build.sh.
cmake_minimum_required(VERSION 3.24)
project(bbport-windows LANGUAGES C CXX)
if (NOT WIN32)
    message(FATAL_ERROR "This CMake project is the Windows build; on Linux run build.sh")
endif()
set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)
set(CMAKE_CXX_STANDARD 23)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
if (NOT CMAKE_BUILD_TYPE)
    set(CMAKE_BUILD_TYPE RelWithDebInfo)
endif()
option(BB_LTO "Link-time optimization of the GPU library" OFF)
enable_testing()

find_package(PkgConfig REQUIRED)
pkg_check_modules(SDL3 REQUIRED IMPORTED_TARGET sdl3)
find_package(Vulkan REQUIRED)

# GPU check for run.py (live_resolution=auto), the launcher's gamepad list (--gamepads) and the
# controller mapping capture (--read-input). Plain C, SDL3 + the Vulkan loader.
add_executable(bb-gpu-capabilities tools/gpu_capabilities.c)
target_compile_options(bb-gpu-capabilities PRIVATE -O2 -Wall -Wextra -Werror)
target_link_libraries(bb-gpu-capabilities PRIVATE PkgConfig::SDL3 Vulkan::Vulkan)
# SDL3's pkg-config adds -mwindows (GUI subsystem); the tools keep their console output.
target_link_options(bb-gpu-capabilities PRIVATE -mconsole)
add_test(NAME gpu-capabilities-gamepads COMMAND bb-gpu-capabilities --gamepads)
```

- [ ] **Step 2: Write the build wrapper**

`tools/windows/build.ps1`:
```powershell
# Configures out/win (once) and builds a target inside the CLANG64 environment.
#   tools\windows\build.ps1                      # everything
#   tools\windows\build.ps1 -Target bbgpu        # one target
#   tools\windows\build.ps1 -Lto                 # ThinLTO on (slow link; release builds)
param([string]$Target = 'all', [string]$Config = 'RelWithDebInfo', [switch]$Lto)
$lto = if ($Lto) { 'ON' } else { 'OFF' }
& "$PSScriptRoot\clang64.ps1" "cmake -S . -B out/win -G Ninja -DCMAKE_BUILD_TYPE=$Config -DBB_LTO=$lto && ninja -C out/win $Target"
exit $LASTEXITCODE
```

- [ ] **Step 3: Configure and build**

Run: `powershell -File tools\windows\build.ps1 -Target bb-gpu-capabilities`
Expected: CMake configures with `-- The C compiler identification is Clang 2x`, Ninja links `out/win/bb-gpu-capabilities.exe`.

- [ ] **Step 4: Verify the subsystem and run the CTest smoke test**

Run: `powershell -File tools\windows\clang64.ps1 "llvm-readobj --file-headers out/win/bb-gpu-capabilities.exe | grep Subsystem && ctest --test-dir out/win --output-on-failure"`
Expected: `Subsystem: IMAGE_SUBSYSTEM_WINDOWS_CUI (0x3)` and `100% tests passed, 0 tests failed out of 1`. Also run `out/win/bb-gpu-capabilities.exe` with no arguments: expected stderr `GPU scene scaling: NVIDIA GeForce RTX 3070 Ti Laptop GPU supports live presets`, exit 0.

- [ ] **Step 5: Add `out/` build outputs to .gitignore if not already ignored, then commit**

Check: `git check-ignore out/win` prints `out/win` (upstream ignores `out/`). If it does not, append `/out/` to `.gitignore`.
```bash
git add CMakeLists.txt tools/windows/build.ps1 .gitignore
git commit -m "build(windows): root CMake project; bb-gpu-capabilities.exe builds and passes its smoke test"
```

---

### Task 4: Platform facade (`BbPlatform`) and `BbThreads` for Windows, with unit tests

**Files:**
- Create: `gpu/shim/bbport_platform.h`
- Create: `gpu/shim/win32/bbport_platform_win32.cpp`
- Modify: `gpu/shim/bbport_threads.h` (whole file)
- Create: `tests/test_platform_win32.cpp`
- Modify: `CMakeLists.txt` (root; add the test target)

**Interfaces:**
- Produces (namespace `BbPlatform`, header `bbport_platform.h`, usable on both platforms):
  - `struct Usage { std::uint64_t user_us, sys_us, invol_switches, vol_switches, minor_faults; }`
  - `bool GetUsage(bool thread, Usage& out)`
  - `std::uint32_t CurrentThreadId()`
  - `int ThreadCpuClock()` — a token for `ReadThreadCpuClockNs`, -1 when unavailable
  - `std::uint64_t ReadThreadCpuClockNs(int clock)`
  - `void DescribeAddress(const void* address, char* out, std::size_t size)` — `"<module>+0x<offset>"` or `"%p"`
  - `void ThreadName(std::uint32_t tid, char* out, std::size_t size)` — `"?"` when unknown
  - `int CaptureBacktrace(void** frames, int max)` — number of frames written
  - `bool ReadMemorySafe(const void* src, void* dst, std::size_t size)` — false instead of faulting
- Produces (namespace `BbThreads`): `unsigned Available()`, `void MakeBackground()` — unchanged signatures, now declared for Windows.

- [ ] **Step 1: Write the failing test**

`tests/test_platform_win32.cpp`:
```cpp
// SPDX-License-Identifier: GPL-2.0-or-later
// bbport-windows: BbPlatform / BbThreads on Windows. Plain asserts, no framework (as tests/*.c).
#include <cassert>
#include <chrono>
#include <cstdio>
#include <cstring>
#include <string>
#include <thread>
#include <windows.h>
#include "bbport_platform.h"
#include "bbport_threads.h"

static void spin_for_ms(int ms) {
    const auto end = std::chrono::steady_clock::now() + std::chrono::milliseconds(ms);
    volatile unsigned long long x = 0;
    while (std::chrono::steady_clock::now() < end) {
        x += 1;
    }
}

int main() {
    // Thread ids: the OS id of this thread, different on another thread.
    assert(BbPlatform::CurrentThreadId() == GetCurrentThreadId());
    std::uint32_t other = 0;
    std::thread([&] { other = BbPlatform::CurrentThreadId(); }).join();
    assert(other != 0 && other != BbPlatform::CurrentThreadId());

    // Resource usage: process and thread both answer; thread CPU time grows while spinning.
    BbPlatform::Usage before{}, after{};
    assert(BbPlatform::GetUsage(false, before));
    assert(BbPlatform::GetUsage(true, before));
    spin_for_ms(120);
    assert(BbPlatform::GetUsage(true, after));
    assert(after.user_us + after.sys_us >= before.user_us + before.sys_us + 50000);

    // A thread CPU clock readable from any thread.
    const int clock = BbPlatform::ThreadCpuClock();
    assert(clock != -1);
    const std::uint64_t t0 = BbPlatform::ReadThreadCpuClockNs(clock);
    spin_for_ms(120);
    std::uint64_t t1 = 0;
    std::thread([&] { t1 = BbPlatform::ReadThreadCpuClockNs(clock); }).join();
    assert(t1 >= t0 + 50000000ull);

    // Addresses are described as module+offset.
    char where[512];
    BbPlatform::DescribeAddress(reinterpret_cast<const void*>(&main), where, sizeof(where));
    assert(std::strstr(where, ".exe+0x") != nullptr);

    // Thread names round-trip through the OS.
    SetThreadDescription(GetCurrentThread(), L"bb:test");
    char name[64];
    BbPlatform::ThreadName(BbPlatform::CurrentThreadId(), name, sizeof(name));
    assert(std::string(name) == "bb:test");
    BbPlatform::ThreadName(0xFFFFFFFFu, name, sizeof(name));
    assert(std::string(name) == "?");

    // Backtraces have at least this frame.
    void* frames[16];
    assert(BbPlatform::CaptureBacktrace(frames, 16) >= 1 && frames[0] != nullptr);

    // Safe reads: a local buffer copies, an unmapped address returns false without faulting.
    const char src[8] = "bbport";
    char dst[8] = {};
    assert(BbPlatform::ReadMemorySafe(src, dst, sizeof(src)) && std::memcmp(src, dst, sizeof(src)) == 0);
    assert(!BbPlatform::ReadMemorySafe(reinterpret_cast<const void*>(0x10), dst, 8));

    // Helper thread sizing and background priority.
    assert(BbThreads::Available() >= 1 && BbThreads::Available() <= std::thread::hardware_concurrency());
    std::thread([] {
        BbThreads::MakeBackground();
        assert(GetThreadPriority(GetCurrentThread()) == THREAD_PRIORITY_IDLE);
    }).join();

    std::puts("platform-win32-test: ok");
    return 0;
}
```

- [ ] **Step 2: Add the test target to the root CMakeLists.txt and see it fail to build**

Append to `CMakeLists.txt`:
```cmake
# Unit test of the GPU library's platform facade (no Vulkan device, no game).
add_executable(platform-win32-test tests/test_platform_win32.cpp gpu/shim/win32/bbport_platform_win32.cpp)
target_compile_options(platform-win32-test PRIVATE -UNDEBUG -Wall -Wextra -Werror)
target_compile_definitions(platform-win32-test PRIVATE NOMINMAX WIN32_LEAN_AND_MEAN _WIN32_WINNT=0x0A00)
target_include_directories(platform-win32-test PRIVATE gpu/shim gpu/shadps4)
target_link_libraries(platform-win32-test PRIVATE psapi)
target_link_options(platform-win32-test PRIVATE -mconsole)
add_test(NAME platform-win32 COMMAND platform-win32-test)
```
Run: `powershell -File tools\windows\build.ps1 -Target platform-win32-test`
Expected: FAIL — `gpu/shim/win32/bbport_platform_win32.cpp` does not exist / `bbport_platform.h` not found.

- [ ] **Step 3: Write the facade header**

`gpu/shim/bbport_platform.h`:
```cpp
// SPDX-License-Identifier: GPL-2.0-or-later
// bbport: the OS facilities the renderer's statistics and diagnostics use — thread ids, CPU
// time, resource usage, address description, thread names, backtraces and faultless memory
// reads — for Linux (inline, below) and Windows (gpu/shim/win32/bbport_platform_win32.cpp, so
// that <windows.h> and its macros stay out of the renderer's headers). Design after yumlevi's
// bbport_platform.h (PR #6, GPL-2.0-or-later); written for this tree.
#pragma once

#include <cstddef>
#include <cstdint>
#ifndef _WIN32
#include <dlfcn.h>
#include <execinfo.h>
#include <pthread.h>
#include <sys/resource.h>
#include <sys/uio.h>
#include <time.h>
#include <unistd.h>
#include <cstdio>
#include <cstring>
#endif

namespace BbPlatform {

struct Usage {
    std::uint64_t user_us = 0, sys_us = 0, invol_switches = 0, vol_switches = 0, minor_faults = 0;
};

#ifdef _WIN32
/// CPU time and counters of the calling thread (thread = true) or the process. Windows keeps no
/// per-thread context-switch or fault counters: those stay 0 for threads.
bool GetUsage(bool thread, Usage& out);
/// OS id of the calling thread.
std::uint32_t CurrentThreadId();
/// A CPU clock of the calling thread that other threads may read (-1: unavailable).
int ThreadCpuClock();
/// CPU time in nanoseconds of the thread behind a ThreadCpuClock() value.
std::uint64_t ReadThreadCpuClockNs(int clock);
/// "module+0xoffset" for a code address, "%p" when no module holds it.
void DescribeAddress(const void* address, char* out, std::size_t size);
/// Name of a thread of this process by OS id, "?" when unknown.
void ThreadName(std::uint32_t tid, char* out, std::size_t size);
/// Return addresses of the calling thread, innermost first; the number written.
int CaptureBacktrace(void** frames, int max);
/// Copies size bytes from src without faulting; false when any byte is unreadable.
bool ReadMemorySafe(const void* src, void* dst, std::size_t size);
#else
inline bool GetUsage(bool thread, Usage& out) {
    rusage usage{};
    if (getrusage(thread ? RUSAGE_THREAD : RUSAGE_SELF, &usage) != 0) {
        return false;
    }
    out.user_us = std::uint64_t(usage.ru_utime.tv_sec) * 1000000 + usage.ru_utime.tv_usec;
    out.sys_us = std::uint64_t(usage.ru_stime.tv_sec) * 1000000 + usage.ru_stime.tv_usec;
    out.invol_switches = usage.ru_nivcsw;
    out.vol_switches = usage.ru_nvcsw;
    out.minor_faults = usage.ru_minflt;
    return true;
}
inline std::uint32_t CurrentThreadId() {
    return static_cast<std::uint32_t>(gettid());
}
inline int ThreadCpuClock() {
    if (clockid_t clock; pthread_getcpuclockid(pthread_self(), &clock) == 0) {
        return static_cast<int>(clock);
    }
    return -1;
}
inline std::uint64_t ReadThreadCpuClockNs(int clock) {
    timespec ts{};
    clock_gettime(static_cast<clockid_t>(clock), &ts);
    return std::uint64_t(ts.tv_sec) * 1000000000ull + std::uint64_t(ts.tv_nsec);
}
inline void DescribeAddress(const void* address, char* out, std::size_t size) {
    Dl_info info{};
    if (dladdr(const_cast<void*>(address), &info) && info.dli_fname) {
        std::snprintf(out, size, "%s+0x%llx", info.dli_fname,
                      static_cast<unsigned long long>(reinterpret_cast<std::uintptr_t>(address) -
                                                      reinterpret_cast<std::uintptr_t>(info.dli_fbase)));
        return;
    }
    std::snprintf(out, size, "%p", address);
}
inline void ThreadName(std::uint32_t tid, char* out, std::size_t size) {
    char path[64];
    std::snprintf(path, sizeof(path), "/proc/self/task/%u/comm", tid);
    std::snprintf(out, size, "?");
    if (FILE* file = std::fopen(path, "r")) {
        char buffer[32]{};
        if (std::fgets(buffer, sizeof(buffer), file)) {
            buffer[std::strcspn(buffer, "\n")] = 0;
            std::snprintf(out, size, "%s", buffer);
        }
        std::fclose(file);
    }
}
inline int CaptureBacktrace(void** frames, int max) {
    return backtrace(frames, max);
}
inline bool ReadMemorySafe(const void* src, void* dst, std::size_t size) {
    iovec local{dst, size}, remote{const_cast<void*>(src), size};
    return process_vm_readv(getpid(), &local, 1, &remote, 1, 0) == static_cast<ssize_t>(size);
}
#endif

} // namespace BbPlatform
```

- [ ] **Step 4: Write the Windows implementation**

`gpu/shim/win32/bbport_platform_win32.cpp`:
```cpp
// SPDX-License-Identifier: GPL-2.0-or-later
// bbport-windows: Windows implementation of bbport_platform.h and bbport_threads.h.
#ifdef _WIN32
#include <algorithm>
#include <bit>
#include <cstdio>
#include <cstring>
#include <thread>
#include <windows.h>
#include <psapi.h>
#include "bbport_platform.h"
#include "bbport_threads.h"

namespace BbPlatform {

static std::uint64_t FileTimeUs(const FILETIME& t) {
    return ((std::uint64_t(t.dwHighDateTime) << 32) | t.dwLowDateTime) / 10;
}

bool GetUsage(bool thread, Usage& out) {
    FILETIME creation, exit, kernel, user;
    const BOOL ok = thread ? GetThreadTimes(GetCurrentThread(), &creation, &exit, &kernel, &user)
                           : GetProcessTimes(GetCurrentProcess(), &creation, &exit, &kernel, &user);
    if (!ok) {
        return false;
    }
    out = {};
    out.user_us = FileTimeUs(user);
    out.sys_us = FileTimeUs(kernel);
    if (!thread) {
        PROCESS_MEMORY_COUNTERS counters{};
        if (GetProcessMemoryInfo(GetCurrentProcess(), &counters, sizeof(counters))) {
            out.minor_faults = counters.PageFaultCount;
        }
    }
    return true;
}

std::uint32_t CurrentThreadId() {
    return static_cast<std::uint32_t>(GetCurrentThreadId());
}

int ThreadCpuClock() {
    // A duplicated thread handle: other threads read it with GetThreadTimes. Never closed (one
    // per long-lived thread, the GPU command processor).
    HANDLE handle = nullptr;
    if (!DuplicateHandle(GetCurrentProcess(), GetCurrentThread(), GetCurrentProcess(), &handle,
                         THREAD_QUERY_LIMITED_INFORMATION, FALSE, 0)) {
        return -1;
    }
    return static_cast<int>(reinterpret_cast<std::intptr_t>(handle));
}

std::uint64_t ReadThreadCpuClockNs(int clock) {
    FILETIME creation, exit, kernel, user;
    const HANDLE handle = reinterpret_cast<HANDLE>(static_cast<std::intptr_t>(clock));
    if (!GetThreadTimes(handle, &creation, &exit, &kernel, &user)) {
        return 0;
    }
    return (FileTimeUs(kernel) + FileTimeUs(user)) * 1000;
}

void DescribeAddress(const void* address, char* out, std::size_t size) {
    HMODULE module = nullptr;
    char name[MAX_PATH];
    if (GetModuleHandleExA(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
                           static_cast<LPCSTR>(address), &module) &&
        GetModuleFileNameA(module, name, sizeof(name))) {
        const char* base = std::strrchr(name, '\\');
        std::snprintf(out, size, "%s+0x%llx", base ? base + 1 : name,
                      static_cast<unsigned long long>(reinterpret_cast<std::uintptr_t>(address) -
                                                      reinterpret_cast<std::uintptr_t>(module)));
        return;
    }
    std::snprintf(out, size, "%p", address);
}

void ThreadName(std::uint32_t tid, char* out, std::size_t size) {
    std::snprintf(out, size, "?");
    HANDLE thread = OpenThread(THREAD_QUERY_LIMITED_INFORMATION, FALSE, tid);
    if (!thread) {
        return;
    }
    PWSTR description = nullptr;
    if (SUCCEEDED(GetThreadDescription(thread, &description)) && description) {
        if (description[0]) {
            WideCharToMultiByte(CP_UTF8, 0, description, -1, out, static_cast<int>(size), nullptr, nullptr);
            out[size - 1] = 0;
        }
        LocalFree(description);
    }
    CloseHandle(thread);
}

int CaptureBacktrace(void** frames, int max) {
    return static_cast<int>(RtlCaptureStackBackTrace(0, static_cast<DWORD>(max), frames, nullptr));
}

bool ReadMemorySafe(const void* src, void* dst, std::size_t size) {
    SIZE_T read = 0;
    return ReadProcessMemory(GetCurrentProcess(), src, dst, size, &read) && read == size;
}

} // namespace BbPlatform

namespace BbThreads {

unsigned Available() {
    DWORD_PTR process = 0, system = 0;
    if (GetProcessAffinityMask(GetCurrentProcess(), &process, &system) && process) {
        return std::max(1, std::popcount(static_cast<unsigned long long>(process)));
    }
    return std::max(1u, std::thread::hardware_concurrency());
}

void MakeBackground() {
    SetThreadPriority(GetCurrentThread(), THREAD_PRIORITY_IDLE);
}

} // namespace BbThreads
#endif
```

- [ ] **Step 5: Rewrite `gpu/shim/bbport_threads.h` with a Windows declaration branch**

```cpp
// SPDX-License-Identifier: GPL-2.0-or-later
// bbport: helper thread sizing. Counts follow the hardware threads this process may run on
// (the affinity mask, so `taskset` can emulate a Steam Deck), and speculative helpers run as
// SCHED_IDLE: they use cores the game leaves idle and never take time from its threads.
// Windows (bbport-windows): the process affinity mask and THREAD_PRIORITY_IDLE, implemented in
// gpu/shim/win32/bbport_platform_win32.cpp.

#pragma once

#include <algorithm>
#include <thread>
#ifndef _WIN32
#include <sched.h>
#include <sys/resource.h>
#include <unistd.h>
#endif

namespace BbThreads {

#ifdef _WIN32
/// Hardware threads available to the process.
unsigned Available();
/// The calling thread only runs on otherwise idle cores.
void MakeBackground();
#else
/// Hardware threads available to the process.
inline unsigned Available() {
    cpu_set_t set;
    CPU_ZERO(&set);
    if (sched_getaffinity(0, sizeof(set), &set) == 0) {
        return std::max(1, CPU_COUNT(&set));
    }
    return std::max(1u, std::thread::hardware_concurrency());
}

/// The calling thread only runs on otherwise idle cores (falls back to the lowest nice level).
inline void MakeBackground() {
    sched_param param{};
    if (sched_setscheduler(0, SCHED_IDLE, &param) != 0) {
        setpriority(PRIO_PROCESS, static_cast<id_t>(gettid()), 19);
    }
}
#endif

} // namespace BbThreads
```

- [ ] **Step 6: Build and run the test**

Run: `powershell -File tools\windows\build.ps1 -Target platform-win32-test` then `powershell -File tools\windows\clang64.ps1 "ctest --test-dir out/win -R platform-win32 --output-on-failure"`
Expected: `platform-win32-test: ok`, `100% tests passed`.

- [ ] **Step 7: Commit**

```bash
git add gpu/shim/bbport_platform.h gpu/shim/win32/bbport_platform_win32.cpp gpu/shim/bbport_threads.h tests/test_platform_win32.cpp CMakeLists.txt
git commit -m "gpu(windows): BbPlatform facade (thread ids, CPU time, usage, addresses, backtraces, safe reads) with unit test"
```

---

### Task 5: `gpu/CMakeLists.txt` Windows branch — configure succeeds, the library starts compiling

**Files:**
- Modify: `gpu/CMakeLists.txt:43-55` (dependencies), `gpu/CMakeLists.txt:118-145` (library definition)
- Modify: `CMakeLists.txt` (root: `add_subdirectory(gpu)`)

**Interfaces:**
- Produces: CMake target `bbgpu` (STATIC on Windows) with PUBLIC link to every dependency and the Windows system libraries, so later executables only `target_link_libraries(... bbgpu)`.
- Consumes: submodule targets from Task 2.

- [ ] **Step 1: Replace the dependency block (lines 43–55)**

Replace from `find_package(Vulkan REQUIRED)` through `find_program(GLSLANG_COMPILER ...)` with:
```cmake
find_package(Vulkan REQUIRED)
find_package(fmt REQUIRED)
find_package(Boost REQUIRED)
find_package(tsl-robin-map REQUIRED)
find_package(PkgConfig REQUIRED)
pkg_check_modules(XXHASH REQUIRED IMPORTED_TARGET libxxhash)
pkg_check_modules(SDL3 REQUIRED IMPORTED_TARGET sdl3)
find_package(Zydis REQUIRED)
if (WIN32)
    # bbport-windows (MSYS2 CLANG64): the header-only libraries MSYS2 does not package come
    # from pinned submodules; VMA's CMake config may be absent, its header is enough.
    add_subdirectory(third_party/magic_enum EXCLUDE_FROM_ALL)
    set(BUILD_EXAMPLES OFF CACHE BOOL "" FORCE)
    set(BUILD_TESTS OFF CACHE BOOL "" FORCE)
    set(BUILD_FUZZERS OFF CACHE BOOL "" FORCE)
    set(BUILD_NO_STDIO OFF CACHE BOOL "" FORCE)
    add_subdirectory(third_party/miniz EXCLUDE_FROM_ALL)
    if (NOT TARGET miniz::miniz)
        add_library(miniz::miniz ALIAS miniz)
    endif()
    add_subdirectory(third_party/xbyak EXCLUDE_FROM_ALL)
    find_package(VulkanMemoryAllocator CONFIG QUIET)
    if (NOT TARGET GPUOpen::VulkanMemoryAllocator)
        find_path(VMA_INCLUDE_DIR vk_mem_alloc.h PATH_SUFFIXES vma REQUIRED)
        add_library(GPUOpen::VulkanMemoryAllocator INTERFACE IMPORTED)
        set_target_properties(GPUOpen::VulkanMemoryAllocator PROPERTIES
            INTERFACE_INCLUDE_DIRECTORIES "${VMA_INCLUDE_DIR}")
    endif()
else()
    find_package(magic_enum REQUIRED)
    find_package(VulkanMemoryAllocator CONFIG REQUIRED)
    pkg_check_modules(X11 REQUIRED IMPORTED_TARGET x11)
    find_package(miniz REQUIRED)
endif()
find_program(GLSLANG_COMPILER NAMES glslang glslangValidator REQUIRED)
```

- [ ] **Step 2: Replace the library block (lines 118–145)**

Replace from `file(GLOB SHIM_SOURCES ...)` through the `target_link_libraries(bbgpu PUBLIC ...)` line with:
```cmake
file(GLOB SHIM_SOURCES CONFIGURE_DEPENDS shim/*.cpp shim/*/*.cpp)
if (WIN32)
    # bbport-windows: a static library (a DLL could not leave the runtime_* symbols to the
    # executable); the Linux-only diagnostics (userfaultfd, SIGTRAP hooks, dma-buf chunks,
    # backtrace wait traces) are stubbed in shim/win32/bbport_diag_win32.cpp.
    list(FILTER SHIM_SOURCES EXCLUDE REGEX "shim/bbport_(free_check|guest_hooks|guest_memory|wait_trace)\\.cpp$")
    set(BBGPU_LIBRARY_TYPE STATIC)
else()
    list(FILTER SHIM_SOURCES EXCLUDE REGEX "shim/win32/")
    set(BBGPU_LIBRARY_TYPE SHARED)
endif()
add_library(bbgpu ${BBGPU_LIBRARY_TYPE} ${VIDEO_CORE} ${RECOMPILER} ${COMMON} ${SHIM_SOURCES}
    shadps4/core/libraries/gnmdriver/gnmdriver.cpp
    shadps4/core/libraries/videoout/driver.cpp shadps4/core/libraries/videoout/video_out.cpp
    shadps4/core/libraries/kernel/equeue.cpp ${AVPLAYER}
    shadps4/core/libraries/videodec/video_utils.cpp)
add_dependencies(bbgpu host_shaders)
# In-game settings menu: Dear ImGui (third_party/imgui, MIT) with its Vulkan backend, and an
# embedded Cyrillic font (third_party/fonts).
target_sources(bbgpu PRIVATE third_party/imgui/imgui.cpp third_party/imgui/imgui_draw.cpp
    third_party/imgui/imgui_tables.cpp third_party/imgui/imgui_widgets.cpp
    third_party/imgui/backends/imgui_impl_vulkan.cpp)
target_include_directories(bbgpu PRIVATE third_party/imgui third_party/imgui/backends)
target_compile_definitions(bbgpu PRIVATE IMGUI_IMPL_VULKAN_NO_PROTOTYPES
    BB_FONT_PATH="${CMAKE_CURRENT_SOURCE_DIR}/third_party/fonts/DejaVuSans.ttf")
set_source_files_properties(shim/bbport_overlay.cpp PROPERTIES
    OBJECT_DEPENDS ${CMAKE_CURRENT_SOURCE_DIR}/third_party/fonts/DejaVuSans.ttf)
target_include_directories(bbgpu PRIVATE shim shadps4 ${SHADER_INCLUDE} third_party/gcn/include third_party/half/include)
target_compile_definitions(bbgpu PRIVATE BOOST_ASIO_STANDALONE NDEBUG)
target_compile_options(bbgpu PRIVATE -Wno-deprecated-declarations -Wno-missing-field-initializers)
# Loaded with bb-probe at startup (DT_NEEDED, never dlopen): thread_local access without a
# TLS descriptor call (_dl_tlsdesc_return was ~2% of the draw recording thread).
target_compile_options(bbgpu PRIVATE -ftls-model=initial-exec)
target_link_libraries(bbgpu PRIVATE ffx-vulkan::portable ffx-vulkan::fsr4-v07-vulkan)
target_link_libraries(bbgpu PUBLIC Vulkan::Headers fmt::fmt Boost::headers magic_enum::magic_enum
    tsl::robin_map GPUOpen::VulkanMemoryAllocator PkgConfig::XXHASH PkgConfig::SDL3 PkgConfig::FFMPEG miniz::miniz Zydis::Zydis sirit)
if (WIN32)
    # Windows headers without min/max macros or winsock 1; Windows 10 APIs (SetThreadDescription).
    target_compile_definitions(bbgpu PUBLIC NOMINMAX WIN32_LEAN_AND_MEAN _WIN32_WINNT=0x0A00)
    # The system libraries the vendored code and the shims call; onecore last (the Windows 10
    # memory APIs plan A-3 uses, which kernel32's import library lacks).
    target_link_libraries(bbgpu PUBLIC xbyak::xbyak winmm ws2_32 bcrypt ole32 shell32 user32 psapi onecore)
    # AMD's FidelityFX sources rely on MSVC's transitive includes on _WIN32 (memset, floor,
    # placement new, swprintf_s, std::mutex).
    foreach(ffx_target IN ITEMS ffx_vulkan_portable ffx_vulkan_fsr3_vk_backend_1_1_4
            ffx_vulkan_fsr3_host_1_1_4 ffx_vulkan_fsr4_v07_vulkan ffx_vulkan_fsr4_v07_assets)
        if (TARGET ${ffx_target})
            target_compile_options(${ffx_target} PRIVATE
                "$<$<COMPILE_LANGUAGE:CXX>:SHELL:-include cstdio>" "$<$<COMPILE_LANGUAGE:CXX>:SHELL:-include cwchar>"
                "$<$<COMPILE_LANGUAGE:CXX>:SHELL:-include cstring>" "$<$<COMPILE_LANGUAGE:CXX>:SHELL:-include cmath>"
                "$<$<COMPILE_LANGUAGE:CXX>:SHELL:-include new>" "$<$<COMPILE_LANGUAGE:CXX>:SHELL:-include mutex>")
        endif()
    endforeach()
else()
    # Runtime symbols (runtime_memory_*, runtime_process_*) resolve against bb-probe.
    target_link_options(bbgpu PRIVATE -Wl,--allow-shlib-undefined)
    target_link_libraries(bbgpu PUBLIC PkgConfig::X11)
endif()
```
If `ninja` later reports that an `ffx_*` target name does not exist, list the real names with `cmake --build out/win --target help | grep ffx` and correct the `foreach` list; the `-include` set stays.

- [ ] **Step 3: Add `gpu/` to the root project**

In the root `CMakeLists.txt`, after `find_package(Vulkan REQUIRED)` insert:
```cmake
# The GPU library (vendored shadPS4 video core + bbport shims); BB_LTO is read by gpu/CMakeLists.txt.
add_subdirectory(gpu)
```

- [ ] **Step 4: Configure, then build the library to find the first errors**

Run: `powershell -File tools\windows\clang64.ps1 "python scripts/apply_vendor_patches.py && cmake -S . -B out/win -G Ninja -DCMAKE_BUILD_TYPE=RelWithDebInfo -DBB_LTO=OFF"`
Expected: configure succeeds (`-- Build files have been written to: .../out/win`). If `find_package(Zydis)` or `find_package(tsl-robin-map)` fails, run `powershell -File tools\windows\clang64.ps1 "ls /clang64/lib/cmake"` and pass the config directory with `-DZydis_DIR=/clang64/lib/cmake/zydis` (resp. `-Dtsl-robin-map_DIR=...`) in `tools/windows/build.ps1`; record the exact option in `README-Windows.md` (Task 12).

Run: `powershell -File tools\windows\build.ps1 -Target bbgpu 2>&1 | Select-Object -First 60`
Expected: compile errors — the first ones in `gpu/shim/bbport_toggles.h` (`sigjmp_buf`), `page_manager.cpp` (`sys/uio.h`), `liverpool.cpp` (`pthread.h`). Tasks 6–10 remove them file by file; the library is expected to link at the end of Task 10, not before.

- [ ] **Step 5: Commit**

```bash
git add gpu/CMakeLists.txt CMakeLists.txt
git commit -m "build(windows): gpu/CMakeLists.txt Windows branch (static bbgpu, submodule deps, no X11, FidelityFX include workarounds)"
```

---

### Task 6: Recovery-point abstraction (`BbRecoverBuf` / `BB_RECOVER_SET`)

**Files:**
- Modify: `gpu/shim/bbport_toggles.h:6,13`
- Modify: `gpu/shadps4/video_core/renderer_vulkan/vk_pipeline_cache.cpp:850-858`
- Modify: `gpu/shadps4/video_core/renderer_vulkan/vk_rasterizer.cpp:1067-1074`
- Modify: `tests/test_gpu_runtime_stubs.cpp`

**Interfaces:**
- Produces (Windows): `struct BbRecoverBuf { alignas(16) unsigned char bytes[256]; }`, `extern "C" __thread BbRecoverBuf* runtime_fault_recover`, `extern "C" int host_setjmp(BbRecoverBuf*)` (defined by plan A-3's `src/host/win32/host_setjmp.S` with exactly this 256-byte layout; `tests/test_gpu_runtime_stubs.cpp` stubs it until then), macro `BB_RECOVER_SET(buf)`.
- Linux keeps `sigjmp_buf` and `sigsetjmp(buf, 0)` under the same names.

- [ ] **Step 1: Edit `gpu/shim/bbport_toggles.h`**

Replace line 6 `#include <csetjmp>` and line 13 `extern "C" __thread sigjmp_buf* runtime_fault_recover;` so the header starts:
```cpp
// bbport: optimizations that can be switched off while the game runs (BB_TOGGLE_FILE,
// see runtime_memory.c), to find which one changes rendering without restarting.
#pragma once
#include <array>
#include <atomic>
#include <chrono>
#include <cstdint>
#include <cstdlib>
#ifndef _WIN32
#include <csetjmp>
#endif

extern "C" std::uint64_t runtime_disabled_optimizations;
/// Recovery point for speculative guest memory reads on this thread (runtime_memory.c).
/// BB_RECOVER_SET(buf) is 0 when the point is set and nonzero when the loader's fault handler
/// jumped back to it.
#ifdef _WIN32
// bbport-windows: no unwinding on Windows (guest frames between the fault and the recovery point
// have no unwind data). host_setjmp/host_longjmp (plan A-3, src/host/win32/host_setjmp.S) save
// and restore every callee-saved register into this 256-byte buffer.
struct alignas(16) BbRecoverBuf {
    unsigned char bytes[256];
};
extern "C" __thread BbRecoverBuf* runtime_fault_recover;
extern "C" int host_setjmp(BbRecoverBuf* buf) __attribute__((returns_twice));
#define BB_RECOVER_SET(buf) host_setjmp(&(buf))
#else
typedef sigjmp_buf BbRecoverBuf;
extern "C" __thread BbRecoverBuf* runtime_fault_recover;
#define BB_RECOVER_SET(buf) sigsetjmp(buf, 0)
#endif
```

- [ ] **Step 2: Edit the two recovery sites**

`vk_pipeline_cache.cpp` lines 850–851: replace
```cpp
        sigjmp_buf recover;
        if (sigsetjmp(recover, 0)) {
```
with
```cpp
        BbRecoverBuf recover;
        if (BB_RECOVER_SET(recover)) {
```
`vk_rasterizer.cpp` lines 1067–1068: replace
```cpp
            sigjmp_buf recover;
            if (sigsetjmp(recover, 0)) {
```
with
```cpp
            BbRecoverBuf recover;
            if (BB_RECOVER_SET(recover)) {
```
Both files already include `bbport_toggles.h` (they reference `runtime_fault_recover`); if the compiler says otherwise, add `#include "bbport_toggles.h"` after the file's other includes.

- [ ] **Step 3: Rewrite `tests/test_gpu_runtime_stubs.cpp`**

```cpp
// SPDX-License-Identifier: GPL-2.0-or-later
#include <cstdlib>
#include <chrono>
#include <cstdint>
#include <cstddef>
#include "bbport_toggles.h"
// Renderer tests have no guest process. Clock/host-thread services work; guest accesses abort.
extern "C" {
__thread BbRecoverBuf* runtime_fault_recover = nullptr;
#ifdef _WIN32
int host_setjmp(BbRecoverBuf*) { return 0; }
#endif
uint32_t runtime_disabled_optimizations = 0;
uint64_t runtime_tsc_frequency() { return 1000000000; }
int runtime_file_translate(const char*, char*, size_t) { std::abort(); }
uint64_t runtime_memory_clamp(uintptr_t, uint64_t) { std::abort(); }
uint64_t runtime_process_time_us() { return std::chrono::duration_cast<std::chrono::microseconds>(std::chrono::steady_clock::now().time_since_epoch()).count(); }
int runtime_memory_region(uintptr_t, uintptr_t*, uintptr_t*, int*) { std::abort(); }
void runtime_memory_set_gpu_hooks(void (*)(uintptr_t, uint64_t),
    void (*)(uintptr_t, uint64_t), void (*)(uintptr_t, uint64_t)) { std::abort(); }
void runtime_thread_attach_host(const char*) {}
void runtime_memory_gpu_protect(uintptr_t, uint64_t, int, int) { std::abort(); }
void runtime_restart() { std::abort(); }
uint64_t runtime_process_time_counter() { return runtime_process_time_us() * 1000; }
int32_t* runtime_errno() { std::abort(); }
int runtime_memory_write_backing(uintptr_t, const void*, uint64_t) { std::abort(); }
}
```
Note `runtime_disabled_optimizations` is declared `std::uint64_t` in the header but defined `uint32_t` here by upstream; keep upstream's definition as is (Linux parity) unless the Windows linker rejects it — then change the definition to `uint64_t` and note it in the commit.

- [ ] **Step 4: Compile the three translation units**

Run: `powershell -File tools\windows\clang64.ps1 "ninja -C out/win gpu/CMakeFiles/bbgpu.dir/shadps4/video_core/renderer_vulkan/vk_pipeline_cache.cpp.obj gpu/CMakeFiles/bbgpu.dir/shadps4/video_core/renderer_vulkan/vk_rasterizer.cpp.obj"`
Expected: both objects compile (other errors in these files, if any, come from Tasks 7–10 includes — `vk_rasterizer.cpp` includes `bbport_guest_memory.h` which is fine, it is header-only). If the object paths differ, find them with `ninja -C out/win -t targets all | grep vk_pipeline_cache`.

- [ ] **Step 5: Commit**

```bash
git add gpu/shim/bbport_toggles.h gpu/shadps4/video_core/renderer_vulkan/vk_pipeline_cache.cpp gpu/shadps4/video_core/renderer_vulkan/vk_rasterizer.cpp tests/test_gpu_runtime_stubs.cpp
git commit -m "gpu: BbRecoverBuf/BB_RECOVER_SET recovery points (sigsetjmp on Linux, host_setjmp on Windows)"
```

---

### Task 7: Linux-only diagnostics stubbed on Windows; write log and fault hook

**Files:**
- Create: `gpu/shim/win32/bbport_diag_win32.cpp`
- Modify: `gpu/shim/bbport_write_log.cpp:10-11` and `:106-121` and the `near` locals near line 143
- Modify: `gpu/shim/bbgpu.cpp:6,254`

**Interfaces:**
- Produces: Windows definitions of every function declared in `bbport_free_check.h`, `bbport_guest_memory.h`, `bbport_guest_hooks.h`, `bbport_wait_trace.h` (all inert: `Enabled()` false, `Usable()` false, `Find()` null, `Scope` empty).
- `bbgpu_dump_guest_writes(void*)` accepts an `EXCEPTION_POINTERS*` on Windows (a `ucontext_t*` on Linux); plan A-3's handler passes exactly that.

- [ ] **Step 1: Write the stub file**

`gpu/shim/win32/bbport_diag_win32.cpp`:
```cpp
// SPDX-License-Identifier: GPL-2.0-or-later
// bbport-windows: the Linux-only diagnostics are not built on Windows (userfaultfd, SIGTRAP
// hooks, dma-buf guest memory, backtrace()-based wait traces); these definitions keep their
// callers unchanged and inert. BB_FREE_CHECK, BB_LABEL_TRAP, BB_GUEST_IN_PLACE and
// BB_WAIT_TRACE have no effect on Windows.
#ifdef _WIN32
#include <cstdint>
#include "bbport_free_check.h"
#include "bbport_guest_hooks.h"
#include "bbport_guest_memory.h"
#include "bbport_wait_trace.h"

namespace BbFreeCheck {
bool Enabled() { return false; }
void Check(std::uint64_t, std::uint64_t, const void*, Source, std::uint64_t) {}
std::uint64_t NextFenceSeq() { return 0; }
void NoteFenceDecoded(std::uint64_t, std::uint64_t, const void*, const void*, std::uint64_t) {}
void NoteFenceWriting(std::uint64_t) {}
void NoteFenceWritten(std::uint64_t, std::uint64_t) {}
bool OnTrapFault(void*, std::uint64_t) { return false; }
bool OnStaleTrapFault(std::uint64_t) { return false; }
void NoteSubmit(std::uint64_t, const void*, std::uint64_t) {}
void DumpAtFault(std::uint64_t, std::uint64_t) {}
} // namespace BbFreeCheck

namespace BbGuestMemory {
bool Usable(const Vulkan::Instance&) { return false; }
void Install(const Vulkan::Instance&) {}
const Chunk* Find(std::uint64_t) { return nullptr; }
} // namespace BbGuestMemory

namespace BbGuestHooks {
void Install(RangeCallback) {}
} // namespace BbGuestHooks

namespace BbWaitTrace {
bool Enabled() { return false; }
Scope::Scope() : frames{}, depth{0}, start{} {}
Scope::~Scope() {}
void Report(double) {}
} // namespace BbWaitTrace
#endif
```

- [ ] **Step 2: Edit `gpu/shim/bbport_write_log.cpp`**

Replace lines 10–11 (`#include <ucontext.h>`, `#include <unistd.h>`) with:
```cpp
#include "bbport_platform.h"
#ifdef _WIN32
#include <windows.h>
#else
#include <ucontext.h>
#endif
```
In `Record()`, replace `static thread_local const std::uint32_t tid = static_cast<std::uint32_t>(gettid());` with `static thread_local const std::uint32_t tid = BbPlatform::CurrentThreadId();`.
Replace lines 106–117 (the start of `bbgpu_dump_guest_writes` through the `regs[]` array) with:
```cpp
// Linux: the ucontext_t of the SIGSEGV handler; Windows: the vectored handler's EXCEPTION_POINTERS.
extern "C" void bbgpu_dump_guest_writes(void* ucontext) {
    using namespace BbWriteLog;
#ifdef _WIN32
    const CONTEXT* c = static_cast<const EXCEPTION_POINTERS*>(ucontext)->ContextRecord;
    const std::uint64_t regs[] = {c->Rax, c->Rbx, c->Rcx, c->Rdx, c->Rsi, c->Rdi, c->R14, c->R15};
#else
    const auto* uc = static_cast<const ucontext_t*>(ucontext);
    const auto* g = uc->uc_mcontext.gregs;
    const std::uint64_t regs[] = {std::uint64_t(g[REG_RAX]), std::uint64_t(g[REG_RBX]),
                                  std::uint64_t(g[REG_RCX]), std::uint64_t(g[REG_RDX]),
                                  std::uint64_t(g[REG_RSI]), std::uint64_t(g[REG_RDI]),
                                  std::uint64_t(g[REG_R14]), std::uint64_t(g[REG_R15])};
#endif
    BbFreeCheck::DumpAtFault(regs[0], regs[6]);
    if (Mode() == 0) {
        return;
    }
```
(The original called `DumpAtFault(rax, r14)` before the `Mode()` check — the order is kept: `regs[0]` is rax, `regs[6]` is r14.) Then rename the local `bool near` (and its two uses) further down to `nearby`: `near` is a macro in the Windows headers.

- [ ] **Step 3: Edit `gpu/shim/bbgpu.cpp`**

Line 6: replace `#include <sys/resource.h>` with
```cpp
#ifndef _WIN32
#include <sys/resource.h>
#endif
```
Line 254: replace `if (config->user_dir) setenv("BB_GPU_USER_DIR", config->user_dir, 0);` with
```cpp
#ifdef _WIN32
    if (config->user_dir && !std::getenv("BB_GPU_USER_DIR")) _putenv_s("BB_GPU_USER_DIR", config->user_dir);
#else
    if (config->user_dir) setenv("BB_GPU_USER_DIR", config->user_dir, 0);
#endif
```

- [ ] **Step 4: Compile the shim objects**

Run: `powershell -File tools\windows\clang64.ps1 "ninja -C out/win gpu/CMakeFiles/bbgpu.dir/shim/win32/bbport_diag_win32.cpp.obj gpu/CMakeFiles/bbgpu.dir/shim/bbport_write_log.cpp.obj gpu/CMakeFiles/bbgpu.dir/shim/bbgpu.cpp.obj"`
Expected: the three objects compile. (`bbgpu.cpp` pulls many headers; an error there that names a file handled by a later task is expected — note it and continue; re-check at the end of Task 10.)

- [ ] **Step 5: Commit**

```bash
git add gpu/shim/win32/bbport_diag_win32.cpp gpu/shim/bbport_write_log.cpp gpu/shim/bbgpu.cpp
git commit -m "gpu(windows): inert stubs for the Linux-only diagnostics; write log reads the exception CONTEXT"
```

---

### Task 8: Platform calls in the video core (page manager, Liverpool, VideoOut driver, scheduler, draw pipe, breadcrumbs, buffer cache)

**Files:**
- Modify: `gpu/shadps4/video_core/page_manager.cpp:19-24,82-89,103-130`
- Modify: `gpu/shadps4/video_core/buffer_cache/region_manager.h:16`
- Modify: `gpu/shadps4/video_core/amdgpu/liverpool.cpp:6-9,121-127,2134-2149,2190-2192` and the `getrusage(RUSAGE_THREAD` block in `ProcessGraphics`
- Modify: `gpu/shadps4/video_core/amdgpu/liverpool.h:197,323`
- Modify: `gpu/shadps4/core/libraries/videoout/driver.cpp:10-13,304-341,414-416,426-430`
- Modify: `gpu/shadps4/video_core/renderer_vulkan/vk_scheduler.cpp:11-13,38-67,72,285-291,404`
- Modify: `gpu/shadps4/video_core/renderer_vulkan/vk_draw_pipe.h:15,201`
- Modify: `gpu/shadps4/video_core/renderer_vulkan/vk_breadcrumbs.cpp:11-12`
- Modify: `gpu/shadps4/video_core/buffer_cache/buffer_cache.cpp:32,579`

**Interfaces:**
- Consumes: `BbPlatform::*` from Task 4.
- Produces: `Liverpool::GetGpuCommandProcessorThreadId()` available on Windows too.

- [ ] **Step 1: `page_manager.cpp`**

Lines 19–24: replace
```cpp
#include <sys/uio.h>
#include <dlfcn.h>
#include <string>
#include <fmt/format.h>
#include <ucontext.h>
#include <unistd.h>
```
with
```cpp
#include <string>
#include <fmt/format.h>
#include "bbport_platform.h"
#ifndef _WIN32
#include <ucontext.h>
#endif
```
Lines 82–89 (`SiteName`, the host-address branch): replace the `Dl_info` block with
```cpp
    const u64 address = key & ~HostSite;
    char where[512];
    BbPlatform::DescribeAddress(reinterpret_cast<const void*>(address), where, sizeof(where));
    return fmt::format("{}host:{}", access, where);
```
(the three `return fmt::format(...)` lines that followed are removed; `address` is declared once as shown).
Lines 103–130 (`NoteFaultSite`): replace the body up to and including the host-code `else` block with
```cpp
void NoteFaultSite(void* context, VAddr address) {
#ifdef _WIN32
    const CONTEXT* c = static_cast<const EXCEPTION_POINTERS*>(context)->ContextRecord;
    const u64 rip = c->Rip, rbp = c->Rbp, rsp = c->Rsp;
#else
    const auto* g = static_cast<const ucontext_t*>(context)->uc_mcontext.gregs;
    const u64 rip = u64(g[REG_RIP]), rbp = u64(g[REG_RBP]), rsp = u64(g[REG_RSP]);
#endif
    current_fault_rip = 0;
    const bool guest_code = rip >= GuestImage && rip < GuestImageEnd;
    u64 caller = 0;
    if (guest_code) {
        // The caller: [rbp + 8] when the guest code keeps frames (its memcpy-like leaves do not).
        u64 saved[2] = {};
        if (BbPlatform::ReadMemorySafe(reinterpret_cast<const void*>(rbp), saved, sizeof(saved)) &&
            saved[1] >= GuestImage && saved[1] < GuestImageEnd) {
            caller = saved[1];
        }
    } else {
        // Host code (a libc import the port runs natively, the runtime): the first guest return
        // address on the stack is its guest caller.
        std::array<u64, 64> stack{};
        if (BbPlatform::ReadMemorySafe(reinterpret_cast<const void*>(rsp), stack.data(), sizeof(stack))) {
            for (const u64 word : stack) {
                if (word >= GuestImage && word < GuestImageEnd) {
                    caller = word;
                    break;
                }
            }
        }
    }
```
The rest of the function (`const u64 key = ...` onward) stays; `Common::IsWriteError(context)` already has a Windows branch in `common/signal_context.cpp`. `<windows.h>` is included at line 33 under `#ifdef _WIN64` (keep).

- [ ] **Step 2: `region_manager.h:16`**

Replace `#include "common/adaptive_mutex.h"` with
```cpp
#ifndef _WIN32
#include "common/adaptive_mutex.h"
#endif
```
(`PTHREAD_ADAPTIVE_MUTEX_INITIALIZER_NP` is undefined on Windows, so the existing `#ifdef` at line 27 selects `Common::SpinLock`; the same pattern at `page_manager.cpp:448` already works.)

- [ ] **Step 3: `liverpool.cpp` / `liverpool.h`**

`liverpool.cpp` lines 6–9: replace `#include <pthread.h>`, `#include <sys/resource.h>`, `#include <sys/uio.h>`, `#include <unistd.h>` with `#include "bbport_platform.h"`.
Lines 121–127: replace
```cpp
    if (clockid_t clock; pthread_getcpuclockid(pthread_self(), &clock) == 0) {
        BbStats::gpu_thread_clock.store(static_cast<int>(clock));
    }
    gpu_id = std::this_thread::get_id();
#ifdef __linux__
    gpu_tid = gettid();
#endif
```
with
```cpp
    if (const int clock = BbPlatform::ThreadCpuClock(); clock != -1) {
        BbStats::gpu_thread_clock.store(clock);
    }
    gpu_id = std::this_thread::get_id();
    gpu_tid = BbPlatform::CurrentThreadId();
```
In `ProcessGraphics`, find the block starting `if (rusage usage{}; getrusage(RUSAGE_THREAD, &usage) == 0) {` (after `BbStats::submissions.fetch_add(1, ...)`) and replace the whole `if` with
```cpp
        if (BbPlatform::Usage usage; BbPlatform::GetUsage(true, usage)) {
            BbStats::gpu_user_us.store(usage.user_us, std::memory_order_relaxed);
            BbStats::gpu_sys_us.store(usage.sys_us, std::memory_order_relaxed);
            BbStats::gpu_invol_switches.store(usage.invol_switches, std::memory_order_relaxed);
            BbStats::gpu_vol_switches.store(usage.vol_switches, std::memory_order_relaxed);
            BbStats::gpu_minor_faults.store(usage.minor_faults, std::memory_order_relaxed);
        }
```
`CheckSubmittedCopy`, lines 2138–2139: replace
```cpp
            iovec local{buf.data(), n * 4}, remote{const_cast<u32*>(guest + at), n * 4};
            if (process_vm_readv(getpid(), &local, 1, &remote, 1, 0) != ssize_t(n * 4)) {
```
with
```cpp
            if (!BbPlatform::ReadMemorySafe(guest + at, buf.data(), n * 4)) {
```
Lines 2191–2192: replace
```cpp
    iovec local{now.data(), (to - from) * 4}, remote{const_cast<u32*>(guest + from), (to - from) * 4};
    const bool readable = process_vm_readv(getpid(), &local, 1, &remote, 1, 0) == ssize_t((to - from) * 4);
```
with
```cpp
    const bool readable = BbPlatform::ReadMemorySafe(guest + from, now.data(), (to - from) * 4);
```
`liverpool.h` lines 197 and 323: replace both `#ifdef __linux__` with `#if defined(__linux__) || defined(_WIN32)` (the `#endif`s stay).

- [ ] **Step 4: `driver.cpp`**

Lines 10–13: replace `#include <sys/resource.h>`, `#include <cstring>`, `#include <dirent.h>`, `#include <unistd.h>` with
```cpp
#include <cstring>
#include "bbport_platform.h"
#ifndef _WIN32
#include <dirent.h>
#include <unistd.h>
#endif
```
`PrintMemory()` lines 304–341: wrap the DRM/statm part so the function begins
```cpp
static void PrintMemory() {
    u64 vram_kib = 0, gtt_kib = 0, rss = 0;
#ifdef _WIN32
    // bbport-windows: no DRM client accounting; RSS is the working set.
    if (BbPlatform::Usage usage; BbPlatform::GetUsage(false, usage)) {
        (void)usage;
    }
    rss = BbPlatform::WorkingSetBytes();
#else
    std::vector<u64> clients;
    if (DIR* dir = opendir("/proc/self/fdinfo")) {
        ... (lines 308–333 unchanged) ...
    }
    unsigned long long size_pages = 0, rss_pages = 0;
    if (FILE* statm = std::fopen("/proc/self/statm", "r")) {
        ... (lines 336–340 unchanged) ...
    }
    rss = u64(rss_pages) * u64(sysconf(_SC_PAGESIZE));
#endif
    const u64 device = BbStats::device_alloc_bytes.load() - BbStats::device_free_bytes.load();
```
and the rest of the function (from `u64 vma_blocks = 0, vma_used = 0;`) stays. Remove the now-unused `(void)usage` block by adding `WorkingSetBytes` to the facade instead: in `bbport_platform.h` add `std::uint64_t WorkingSetBytes();` (Windows declaration) with the Linux inline
```cpp
inline std::uint64_t WorkingSetBytes() {
    unsigned long long size_pages = 0, rss_pages = 0;
    if (FILE* statm = std::fopen("/proc/self/statm", "r")) {
        if (std::fscanf(statm, "%llu %llu", &size_pages, &rss_pages) != 2) {
            rss_pages = 0;
        }
        std::fclose(statm);
    }
    return std::uint64_t(rss_pages) * std::uint64_t(sysconf(_SC_PAGESIZE));
}
```
and in `bbport_platform_win32.cpp`
```cpp
std::uint64_t WorkingSetBytes() {
    PROCESS_MEMORY_COUNTERS counters{};
    if (GetProcessMemoryInfo(GetCurrentProcess(), &counters, sizeof(counters))) {
        return counters.WorkingSetSize;
    }
    return 0;
}
```
so the Windows branch of `PrintMemory` is just `rss = BbPlatform::WorkingSetBytes();` (drop the `GetUsage` lines). Add an assert to `tests/test_platform_win32.cpp`: `assert(BbPlatform::WorkingSetBytes() > 1024 * 1024);`.
Lines 414–416: replace
```cpp
        if (rusage usage{}; getrusage(RUSAGE_SELF, &usage) == 0) {
            proc_flt = usage.ru_minflt;
        }
```
with
```cpp
        if (BbPlatform::Usage usage; BbPlatform::GetUsage(false, usage)) {
            proc_flt = usage.minor_faults;
        }
```
Lines 426–430: replace
```cpp
        if (const int clock = BbStats::gpu_thread_clock.load(); clock != -1) {
            timespec ts{};
            clock_gettime(static_cast<clockid_t>(clock), &ts);
            gpu_ns = u64(ts.tv_sec) * 1000000000ull + u64(ts.tv_nsec);
        }
```
with
```cpp
        if (const int clock = BbStats::gpu_thread_clock.load(); clock != -1) {
            gpu_ns = BbPlatform::ReadThreadCpuClockNs(clock);
        }
```

- [ ] **Step 5: `vk_scheduler.cpp`**

Lines 11–13: replace `#include <dlfcn.h>`, `#include <execinfo.h>`, `#include <unistd.h>` with `#include "bbport_platform.h"`.
Lines 38–53 (`ThreadName`): replace the function with
```cpp
std::string ThreadName(u32 tid) {
    char name[64];
    BbPlatform::ThreadName(tid, name, sizeof(name));
    return name;
}
```
Line 59: `const u32 self = u32(gettid());` → `const u32 self = BbPlatform::CurrentThreadId();`
Lines 64–66: replace
```cpp
    void* frames[24];
    const int depth = backtrace(frames, 24);
    backtrace_symbols_fd(frames, depth, 2);
```
with
```cpp
    void* frames[24];
    const int depth = BbPlatform::CaptureBacktrace(frames, 24);
    for (int i = 0; i < depth; ++i) {
        char where[512];
        BbPlatform::DescribeAddress(frames[i], where, sizeof(where));
        std::fprintf(stderr, "  #%d %s\n", i, where);
    }
```
Line 72: `static thread_local const u32 tid = u32(gettid());` → `static thread_local const u32 tid = BbPlatform::CurrentThreadId();`
Lines 285–291: replace the `Dl_info` block with
```cpp
        char where[512];
        BbPlatform::DescribeAddress(top[i].second, where, sizeof(where));
        std::printf("Recorder sync caller: %llu x %s\n", static_cast<unsigned long long>(top[i].first), where);
```
Line 404: `u32(gettid())` → `BbPlatform::CurrentThreadId()`.

- [ ] **Step 6: `vk_draw_pipe.h`, `vk_breadcrumbs.cpp`, `buffer_cache.cpp`**

`vk_draw_pipe.h` line 15: after `#include "bbport_threads.h"` add `#include "bbport_platform.h"`; line 201: `stage_b_tid.store(static_cast<u32>(gettid()), std::memory_order_release);` → `stage_b_tid.store(BbPlatform::CurrentThreadId(), std::memory_order_release);`.
`vk_breadcrumbs.cpp` lines 11–12: wrap `#include <sys/stat.h>` and `#include <unistd.h>` in `#ifndef _WIN32` / `#endif`.
`buffer_cache.cpp` line 32: wrap `#include <pthread.h>` in `#ifndef _WIN32` / `#endif` and add `#include "common/thread.h"` next to it (unconditional). Line 579: replace `pthread_getname_np(pthread_self(), requester.data(), requester.size());` with
```cpp
#ifdef _WIN32
        const std::string name = Common::GetCurrentThreadName();
        std::snprintf(requester.data(), requester.size(), "%s", name.c_str());
#else
        pthread_getname_np(pthread_self(), requester.data(), requester.size());
#endif
```

- [ ] **Step 7: Build the touched objects and the platform test**

Run: `powershell -File tools\windows\clang64.ps1 "ninja -C out/win gpu/CMakeFiles/bbgpu.dir/shadps4/video_core/page_manager.cpp.obj gpu/CMakeFiles/bbgpu.dir/shadps4/video_core/amdgpu/liverpool.cpp.obj gpu/CMakeFiles/bbgpu.dir/shadps4/core/libraries/videoout/driver.cpp.obj gpu/CMakeFiles/bbgpu.dir/shadps4/video_core/renderer_vulkan/vk_scheduler.cpp.obj gpu/CMakeFiles/bbgpu.dir/shadps4/video_core/renderer_vulkan/vk_breadcrumbs.cpp.obj gpu/CMakeFiles/bbgpu.dir/shadps4/video_core/buffer_cache/buffer_cache.cpp.obj platform-win32-test && ctest --test-dir out/win -R platform-win32 --output-on-failure"`
Expected: objects compile (errors naming `regs.h`, `texture_cache.h` or `vk_scheduler.h`'s `joinable()` belong to Task 9 — note and continue); platform test passes with the new `WorkingSetBytes` assert.

- [ ] **Step 8: Commit**

```bash
git add gpu/shim/bbport_platform.h gpu/shim/win32/bbport_platform_win32.cpp tests/test_platform_win32.cpp gpu/shadps4/video_core/page_manager.cpp gpu/shadps4/video_core/buffer_cache/region_manager.h gpu/shadps4/video_core/amdgpu/liverpool.cpp gpu/shadps4/video_core/amdgpu/liverpool.h gpu/shadps4/core/libraries/videoout/driver.cpp gpu/shadps4/video_core/renderer_vulkan/vk_scheduler.cpp gpu/shadps4/video_core/renderer_vulkan/vk_draw_pipe.h gpu/shadps4/video_core/renderer_vulkan/vk_breadcrumbs.cpp gpu/shadps4/video_core/buffer_cache/buffer_cache.cpp
git commit -m "gpu: route thread ids, CPU clocks, usage, backtraces and safe reads through BbPlatform"
```

---

### Task 9: libc++ compatibility and the `jthread::joinable()` hot path

**Files:**
- Modify: `gpu/shadps4/video_core/amdgpu/regs.h` (after the includes; `RegDirty::blocks`)
- Modify: `gpu/shadps4/video_core/texture_cache/texture_cache.h` (`IsUpToDate` and the `UpdateImageFastPath` check)
- Modify: `gpu/shadps4/common/lru_cache.h:59`
- Modify: `gpu/shadps4/video_core/renderer_vulkan/vk_bind_helper.h`
- Modify: `gpu/shadps4/video_core/renderer_vulkan/vk_scheduler.h`, `vk_scheduler.cpp`

**Interfaces:**
- Produces: `BlockBits<N>` (libc++ only) with the `std::bitset` subset `RegDirty` uses: `set`, `reset`, `test`, `size`, `_Find_first`, `_Find_next`.
- `Scheduler` gains `bool recorder_running`; `BindHelper` gains `bool running`. Behaviour identical to the `joinable()` checks they replace.

- [ ] **Step 1: `regs.h` — a bitset with `_Find_first/_Find_next` for libc++**

After the existing includes add
```cpp
#ifdef _LIBCPP_VERSION
#include <algorithm>
#include <array>
#include <bit>
#endif
```
Before `struct RegDirty {` add
```cpp
#ifdef _LIBCPP_VERSION
// bbport-windows: the std::bitset subset RegDirty uses, including libstdc++'s _Find_first /
// _Find_next (not in libc++), over 64-bit words.
template <std::size_t N>
class BlockBits {
public:
    void set(std::size_t bit) { words[bit / 64] |= u64(1) << (bit % 64); }
    void reset() { words = {}; }
    bool test(std::size_t bit) const { return (words[bit / 64] >> (bit % 64)) & 1; }
    static constexpr std::size_t size() { return N; }
    std::size_t _Find_first() const { return Scan(0); }
    std::size_t _Find_next(std::size_t bit) const { return bit + 1 >= N ? N : Scan(bit + 1); }

private:
    std::size_t Scan(std::size_t from) const {
        std::size_t word = from / 64;
        u64 bits = words[word] & (~u64(0) << (from % 64));
        while (!bits) {
            if (++word == words.size()) {
                return N;
            }
            bits = words[word];
        }
        return std::min<std::size_t>(word * 64 + std::countr_zero(bits), N);
    }
    std::array<u64, (N + 63) / 64> words{};
};
#endif
```
Inside `RegDirty`, replace `std::bitset<NumBlocks> blocks;` with
```cpp
#ifdef _LIBCPP_VERSION
    BlockBits<NumBlocks> blocks;
#else
    std::bitset<NumBlocks> blocks;
#endif
```
If the compiler reports another `std::bitset` member used on `blocks` (e.g. `any()`, `count()`, `operator[]`), add it to `BlockBits` with the same semantics (`any`: any word nonzero; `count`: sum of `std::popcount`; `operator[]`: `test`).

- [ ] **Step 2: `texture_cache.h` — atomic loads of `image.flags`**

In `IsUpToDate` and in the `UpdateImageFastPath` check, replace each
```cpp
        const u32 flags = std::atomic_ref<const u32>(reinterpret_cast<const u32&>(image.flags))
                              .load(std::memory_order_acquire);
```
with
```cpp
#ifdef _LIBCPP_VERSION
        // libc++ has no std::atomic_ref<const T>.
        const u32 flags = __atomic_load_n(reinterpret_cast<const u32*>(&image.flags), __ATOMIC_ACQUIRE);
#else
        const u32 flags = std::atomic_ref<const u32>(reinterpret_cast<const u32&>(image.flags))
                              .load(std::memory_order_acquire);
#endif
```

- [ ] **Step 3: `lru_cache.h:59` — the early-stop comparison (bug fix on both platforms)**

Replace `std::is_same_v<std::invoke_result<Func, ObjectType>, bool>;` with `std::is_same_v<std::invoke_result_t<Func, ObjectType>, bool>;` (the trait type itself was compared with `bool`, so the early stop never worked).

- [ ] **Step 4: `vk_bind_helper.h` — `running` flag**

In the constructor, after `thread = std::jthread(...)` add `running = true;`. Replace `if (thread.joinable()) {` in the destructor with `if (running) {`. Replace the body of `Available()` with `return running;` and add above it the comment `/// Asked per draw: a flag, because std::jthread::joinable() is a system call (GetThreadId) with libc++ on Windows.` Add the member `bool running = false; ///< the helper thread runs (see Available)` after `std::jthread thread;`.

- [ ] **Step 5: `vk_scheduler.h/.cpp` — `recorder_running` flag**

`vk_scheduler.h`: after `std::jthread recorder_thread;` add
```cpp
    /// bbport: recorder_thread runs. Checked per recorded command: std::jthread::joinable() asks
    /// the kernel for the thread id with libc++ on Windows (GetThreadId).
    bool recorder_running = false;
```
and replace the three `recorder_thread.joinable()` uses in the header (`CommandBuffer()`, `Record()`, `IsRecordingDeferred()`) with `recorder_running`.
`vk_scheduler.cpp`: in the constructor, after `recorder_thread = std::jthread(...)` add `recorder_running = true;`; in the destructor replace `if (recorder_thread.joinable()) {` with `if (recorder_running) {` and add `recorder_running = false;` right after `SyncRecording();`; replace the remaining `recorder_thread.joinable()` uses (`BeginRendering`, `KickRecording`, `SyncRecording`) with `recorder_running`. Verify with `grep -n "joinable" gpu/shadps4/video_core/renderer_vulkan/vk_scheduler.*` that only the destructor's `recorder_thread.join()` remains (no `joinable()` left).

- [ ] **Step 6: Build the affected objects**

Run: `powershell -File tools\windows\clang64.ps1 "ninja -C out/win gpu/CMakeFiles/bbgpu.dir/shadps4/video_core/renderer_vulkan/vk_scheduler.cpp.obj gpu/CMakeFiles/bbgpu.dir/shadps4/video_core/renderer_vulkan/vk_draw_prep.cpp.obj gpu/CMakeFiles/bbgpu.dir/shadps4/video_core/texture_cache/texture_cache.cpp.obj"`
Expected: compile.

- [ ] **Step 7: Commit**

```bash
git add gpu/shadps4/video_core/amdgpu/regs.h gpu/shadps4/video_core/texture_cache/texture_cache.h gpu/shadps4/common/lru_cache.h gpu/shadps4/video_core/renderer_vulkan/vk_bind_helper.h gpu/shadps4/video_core/renderer_vulkan/vk_scheduler.h gpu/shadps4/video_core/renderer_vulkan/vk_scheduler.cpp
git commit -m "gpu: libc++ compatibility (RegDirty bitset, atomic flag loads), lru_cache early-stop fix, no jthread::joinable() per draw"
```

---

### Task 10: `common/` on Windows, the Win32 window branch, and the full library build

**Files:**
- Modify: `gpu/shadps4/common/io_file.cpp:13-18,239-248`
- Modify: `gpu/shadps4/video_core/renderer_vulkan/vk_platform.cpp:270`
- Modify: `gpu/shim/window.cpp:1,32-44`
- Modify: `tests/test_upscaler_support.cpp:7`

**Interfaces:**
- Produces: `libbbgpu.a` links on Windows. `WindowSDL` fills `window_info.type = WindowSystemType::Windows` and the HWND on the `windows` SDL driver (consumed by the existing `VK_KHR_win32_surface` branch of `vk_platform.cpp`).

- [ ] **Step 1: `io_file.cpp` — delete-on-close without ntdll**

Lines 13–18: replace
```cpp
#ifdef _WIN32
#include "common/ntapi.h"

#include <io.h>
#include <share.h>
#include <windows.h>
```
with
```cpp
#ifdef _WIN32
#include <io.h>
#include <share.h>
#include <windows.h>
```
Lines 239–248 (`Unlink`): replace the `FILE_DISPOSITION_INFORMATION ... NtSetInformationFile(...)` block with
```cpp
#ifdef _WIN64
    // bbport-windows: Win32 delete-on-close (ntdll's NtSetInformationFile is not linked).
    const int fd = fileno(file);
    HANDLE hfile = reinterpret_cast<HANDLE>(_get_osfhandle(fd));
    FILE_DISPOSITION_INFO disposition{};
    disposition.DeleteFile = TRUE;
    SetFileInformationByHandle(hfile, FileDispositionInfo, &disposition, sizeof(disposition));
#else
```
(the `#else` / `unlink` branch and `#endif` stay).

- [ ] **Step 2: `vk_platform.cpp:270`**

Replace `setenv("VK_DRIVER_FILES", icd_path.c_str(), true);` with
```cpp
#ifdef _WIN32
    _putenv_s("VK_DRIVER_FILES", icd_path.c_str());
#else
    setenv("VK_DRIVER_FILES", icd_path.c_str(), true);
#endif
```
If the line is already inside a `#ifndef _WIN32` region (check with the surrounding `#if`s), leave it untouched.

- [ ] **Step 3: `window.cpp` — the Win32 driver**

Line 1 comment: `// bbport: SDL3 window for the Vulkan swapchain (X11, Wayland or Win32).`
Lines 34–44: replace the driver `if` chain with
```cpp
#ifdef _WIN32
    if (driver && !std::strcmp(driver, "windows")) {
        window_info.type = WindowSystemType::Windows;
        window_info.render_surface = SDL_GetPointerProperty(wp, SDL_PROP_WINDOW_WIN32_HWND_POINTER, nullptr);
    } else
#endif
    if (driver && !std::strcmp(driver, "x11")) {
        window_info.type = WindowSystemType::X11;
        window_info.display_connection = SDL_GetPointerProperty(wp, SDL_PROP_WINDOW_X11_DISPLAY_POINTER, nullptr);
        window_info.render_surface = reinterpret_cast<void*>(SDL_GetNumberProperty(wp, SDL_PROP_WINDOW_X11_WINDOW_NUMBER, 0));
    } else if (driver && !std::strcmp(driver, "wayland")) {
        window_info.type = WindowSystemType::Wayland;
        window_info.display_connection = SDL_GetPointerProperty(wp, SDL_PROP_WINDOW_WAYLAND_DISPLAY_POINTER, nullptr);
        window_info.render_surface = SDL_GetPointerProperty(wp, SDL_PROP_WINDOW_WAYLAND_SURFACE_POINTER, nullptr);
    } else {
        UNREACHABLE_MSG("Unsupported SDL video driver {}", driver ? driver : "(none)");
    }
```
Confirm `WindowSystemType::Windows` exists in `gpu/shim/sdl_window.h` (or the vendored `frontend` header it includes); if the enumerator is missing, add `Windows,` to the enum next to `X11` and `Wayland`.

- [ ] **Step 4: `tests/test_upscaler_support.cpp:7` — `setenv` on Windows**

Replace `#include <unistd.h>` with
```cpp
#ifdef _WIN32
#include <cstdlib>
static int setenv(const char* name, const char* value, int) { return _putenv_s(name, value); }
static int unsetenv(const char* name) { return _putenv_s(name, ""); }
#else
#include <unistd.h>
#endif
```

- [ ] **Step 5: Build the whole library and fix what remains**

Run: `powershell -File tools\windows\build.ps1 -Target bbgpu`
Expected: `out/win/gpu/libbbgpu.a` is produced. For every remaining error, apply this rule and record the file in the commit message: (a) a POSIX header or call in vendored `common/` or `video_core/` → guard with `#ifndef _WIN32` and add the Windows equivalent through `BbPlatform` (extend the facade, add an assert to `tests/test_platform_win32.cpp`); (b) a libstdc++-only API → `#ifdef _LIBCPP_VERSION` branch as in Task 9; (c) a Windows macro clash (`near`, `far`, `min`, `max`, `ERROR`, `DELETE`) → rename the local identifier; (d) a missing `ffx_*` target name → fix the list in Task 5 Step 2. Do not disable `-Werror` and do not remove source files from the build beyond the four diagnostics already excluded.

- [ ] **Step 6: Commit**

```bash
git add gpu/shadps4/common/io_file.cpp gpu/shadps4/video_core/renderer_vulkan/vk_platform.cpp gpu/shim/window.cpp tests/test_upscaler_support.cpp
git commit -m "gpu(windows): io_file delete-on-close via Win32, Win32 SDL driver in the window shim; libbbgpu.a builds"
```

---

### Task 11: Renderer tests on Windows under CTest

**Files:**
- Modify: `CMakeLists.txt` (root)
- Test: CTest tests `motion-history`, `motion-shader`, `ui-composition`, `upscaler-support` (no device), `scene-resolution`, `taa-shader`, `camera-motion` (label `gpu`)

**Interfaces:**
- Consumes: the test targets defined in `gpu/CMakeLists.txt` (`EXCLUDE_FROM_ALL`).
- Produces: `ctest --test-dir out/win` runs the device-less tests; `ctest -L gpu` runs the device tests.

- [ ] **Step 1: Register the tests in the root CMakeLists.txt**

Append:
```cmake
# Renderer tests from gpu/CMakeLists.txt (EXCLUDE_FROM_ALL there): built with everything here.
foreach(t IN ITEMS motion-history-test motion-shader-test ui-composition-test upscaler-support-test
        scene-resolution-test taa-shader-test camera-motion-test)
    set_target_properties(${t} PROPERTIES EXCLUDE_FROM_ALL FALSE)
    target_link_options(${t} PRIVATE -mconsole)
endforeach()
add_test(NAME motion-history COMMAND motion-history-test)
add_test(NAME motion-shader COMMAND motion-shader-test)
add_test(NAME ui-composition COMMAND ui-composition-test)
add_test(NAME upscaler-support COMMAND upscaler-support-test)
# These create a Vulkan device: run with `ctest -L gpu` on a machine with a GPU.
add_test(NAME scene-resolution COMMAND scene-resolution-test)
add_test(NAME taa-shader COMMAND taa-shader-test)
add_test(NAME camera-motion COMMAND camera-motion-test)
set_tests_properties(scene-resolution taa-shader camera-motion PROPERTIES LABELS gpu)
```

- [ ] **Step 2: Build everything and run the device-less tests**

Run: `powershell -File tools\windows\build.ps1` then `powershell -File tools\windows\clang64.ps1 "ctest --test-dir out/win -LE gpu --output-on-failure"`
Expected: `100% tests passed` for `gpu-capabilities-gamepads`, `platform-win32`, `motion-history`, `motion-shader`, `ui-composition`, `upscaler-support`. A failure inside a test body (not a build error) is reported with its output; fix only Windows-specific causes (paths with backslashes, `setenv`, line endings) in the test, never in the renderer.

- [ ] **Step 3: Run the device tests on this laptop's GPU**

Run: `powershell -File tools\windows\clang64.ps1 "ctest --test-dir out/win -L gpu --output-on-failure"`
Expected: the three pass on the RTX 3070 Ti. If `scene-resolution` reports a missing `VK_EXT_shader_stencil_export` or a format without blit support, that is a GPU capability result, not a build failure: record the output in the commit message.

- [ ] **Step 4: Run the platform-neutral Python tests**

Run: `python -m unittest tests.test_prepare tests.test_link_libc tests.test_game_check tests.test_upscaler_assets tests.test_apply_vendor_patches -v`
Expected: all pass. For a test that fails only because of a POSIX-only call (`os.symlink`, `/proc`, `chmod` bits), decorate that test method with `@unittest.skipIf(os.name == 'nt', 'needs <call>; plan A-4 provides the Windows equivalent')` and list it in the commit message; any other failure is a real bug to fix.

- [ ] **Step 5: Commit**

```bash
git add CMakeLists.txt tests
git commit -m "test(windows): renderer tests under CTest (device tests labelled gpu); platform-neutral Python tests pass"
```

---

### Task 12: CI workflows, developer README and attribution

**Files:**
- Create: `.github/workflows/windows.yml`
- Create: `.github/workflows/linux-compile.yml`
- Create: `.gitattributes`
- Create: `README-Windows.md`
- Modify: `THIRD_PARTY.md` (create if upstream has none)

**Interfaces:**
- Produces: a green `windows` check on every push to `windows` (artifact `bbport-windows-tools-<sha>`: `bb-gpu-capabilities.exe` + test logs) and a green `linux-compile` check.

- [ ] **Step 1: Windows workflow**

`.github/workflows/windows.yml`:
```yaml
name: windows
on:
  push:
    branches: [windows]
  pull_request:
  workflow_dispatch:
jobs:
  build:
    runs-on: windows-latest
    timeout-minutes: 90
    steps:
      - uses: actions/checkout@v4
        with:
          submodules: recursive
      - name: Package list
        id: packages
        shell: pwsh
        run: |
          $list = (Get-Content msys2-packages.txt | Where-Object { $_.Trim() -and -not $_.Trim().StartsWith('#') }) -join ' '
          "list=$list" >> $env:GITHUB_OUTPUT
      - uses: msys2/setup-msys2@v2
        with:
          msystem: CLANG64
          update: true
          install: ${{ steps.packages.outputs.list }}
      - name: Toolchain check
        shell: msys2 {0}
        run: python tools/windows/check_toolchain.py
      - name: Vendor patches
        shell: msys2 {0}
        run: python scripts/apply_vendor_patches.py
      - name: Configure
        shell: msys2 {0}
        run: cmake -S . -B out/win -G Ninja -DCMAKE_BUILD_TYPE=RelWithDebInfo -DBB_LTO=OFF
      - name: Build
        shell: msys2 {0}
        run: ninja -C out/win
      - name: Tests (no GPU on the runner)
        shell: msys2 {0}
        run: ctest --test-dir out/win -LE gpu --output-on-failure
      - name: Python tests
        shell: msys2 {0}
        run: python -m unittest tests.test_prepare tests.test_link_libc tests.test_game_check tests.test_upscaler_assets tests.test_apply_vendor_patches -v
      - name: Collect tools
        shell: msys2 {0}
        run: |
          mkdir -p package/bin
          cp out/win/bb-gpu-capabilities.exe package/bin/
          for dll in $(ldd out/win/bb-gpu-capabilities.exe | awk '{print $3}' | grep -E '^/clang64/bin/.*\.dll$'); do cp "$dll" package/bin/; done
          cp out/win/Testing/Temporary/LastTest.log package/ || true
      - uses: actions/upload-artifact@v4
        with:
          name: bbport-windows-tools-${{ github.sha }}
          path: package/
          if-no-files-found: error
```

- [ ] **Step 2: Linux compile-only workflow**

`.github/workflows/linux-compile.yml`:
```yaml
name: linux-compile
on:
  push:
    branches: [windows]
  pull_request:
  workflow_dispatch:
jobs:
  build:
    runs-on: ubuntu-latest
    timeout-minutes: 120
    steps:
      - uses: actions/checkout@v4
        with:
          submodules: recursive
      - uses: cachix/install-nix-action@v27
        with:
          nix_path: nixpkgs=channel:nixos-unstable
      - name: Build (upstream build.sh inside shell.nix, LTO off)
        run: nix-shell shell.nix --run "BB_IN_NIX_SHELL=1 BB_LTO=OFF bash build.sh --test"
      - name: Python tests
        run: nix-shell shell.nix --run "python3 -m unittest discover -s tests"
```
Note: upstream's `.gitmodules` does not list the three new submodules for Linux use; `build.sh` ignores them, and `gpu/CMakeLists.txt` only adds them under `if (WIN32)`.

- [ ] **Step 3: `.gitattributes` and README**

`.gitattributes`:
```
# cmd.exe and PowerShell read CRLF scripts reliably; everything else stays LF.
*.bat text eol=crlf
*.ps1 text eol=crlf
```
`README-Windows.md`:
```markdown
# Windows build (bbport-windows)

Status: plan A-1 — the GPU library, `bb-gpu-capabilities.exe` and the renderer tests build and
run on Windows. The loader/runtime (`bb-probe.exe`) follows in plans A-2/A-3; booting the game in
A-4. See `docs/superpowers/specs/2026-10-07-windows-host-layer-design.md`.

## Toolchain

MSYS2 CLANG64 only (clang, libc++, lld). MSVC cannot build the runtime (`__attribute__((sysv_abi))`,
GNU inline assembly).

    powershell -ExecutionPolicy Bypass -File tools\windows\setup-msys2.ps1   # installs C:\msys64 + packages
    tools\windows\clang64.ps1 "python tools/windows/check_toolchain.py"      # verifies versions

Set `BB_MSYS2` when MSYS2 lives elsewhere. Submodules: `git submodule update --init --recursive`;
then `python scripts/apply_vendor_patches.py` once (FSR-Vulkan patches, as build.sh does on Linux).

## Build and test

    tools\windows\build.ps1                 # configure out/win and build everything (BB_LTO=OFF)
    tools\windows\build.ps1 -Lto            # ThinLTO (release builds; the link takes minutes)
    tools\windows\clang64.ps1 "ctest --test-dir out/win -LE gpu --output-on-failure"   # no device needed
    tools\windows\clang64.ps1 "ctest --test-dir out/win -L gpu --output-on-failure"    # needs a Vulkan GPU

`bb-gpu-capabilities.exe --gamepads` lists controllers (GUID and name); `--read-input` captures a
key or button name for `bbport.ini`; no argument checks the GPU for live resolution changes.

## Notes

- Everything Windows-specific is behind `#ifdef _WIN32` / `if (WIN32)` or in `gpu/shim/win32/`,
  `tools/windows/`, `.github/workflows/windows.yml`. Linux is compile-checked by CI, not run.
- Forks that vendor `SPIRV-Headers` as files exceed `MAX_PATH`: `git config core.longpaths true`
  before cloning them. This tree does not need it.
- Diagnostics without a Windows implementation yet: `BB_FREE_CHECK`, `BB_LABEL_TRAP`,
  `BB_WAIT_TRACE`, `BB_UFFD`, `BB_GUEST_IN_PLACE` (no effect on Windows).
```

- [ ] **Step 4: Attribution**

Append to `THIRD_PARTY.md` (create the file with a heading `# Third-party components and borrowed designs` if it does not exist):
```markdown
## Designs borrowed for the Windows build (all GPL-2.0-or-later, re-implemented for this tree)

- yumlevi, bbport PR #6 "Native Windows port (MSYS2 CLANG64, Win32 API)": the platform facade
  (`gpu/shim/bbport_platform.h`), the `BbRecoverBuf`/`BB_RECOVER_SET` abstraction, the libc++
  bitset and atomic-load workarounds, the `recorder_running`/`running` flags replacing
  `std::jthread::joinable()`, the FidelityFX `-include` workaround.
- Supermedo/bloodborne_pc (`windows` branch): the shape of the Win32 shim CMake branch.
- DarkIzuku/bloodborne_pc: the GitHub Actions step structure and the renderer-test stub arrangement.
- shadPS4 (shadps4-emu/shadPS4): the vendored video core's own Windows branches
  (`common/thread.cpp`, `common/signal_context.cpp`, `vk_platform.cpp`).
```

- [ ] **Step 5: Push and watch both workflows**

```bash
git add .github/workflows/windows.yml .github/workflows/linux-compile.yml .gitattributes README-Windows.md THIRD_PARTY.md
git commit -m "ci: Windows (MSYS2 CLANG64) build+test workflow, Linux compile-only workflow; developer README; attribution"
git push origin windows
gh run list --branch windows --limit 4
gh run watch
```
Expected: both runs `completed success`. If `linux-compile` fails inside the vendored core with an error introduced by this plan (a file touched in Tasks 6–10), fix it under `#ifndef _WIN32` discipline and push again; if it fails on upstream code that never compiled under that Nix channel, pin `nix_path` to the channel upstream's `docs/` names and note it in `README-Windows.md`.

---

## Self-review (done while writing; the executor re-runs it before declaring A-1 complete)

- Spec coverage: §5.7 compile-side items (platform facade, diagnostics stubs, write log, window Win32 driver, libc++ fixes, `joinable()` flags, `lru_cache` fix, static library, no X11, submodules, FidelityFX includes) → Tasks 4–10; §5.8 toolchain/CMake → Tasks 1, 3, 5; §5.9 CI and attribution → Task 12; §7 device-less renderer tests on Windows → Task 11. Deferred by design: the HLE exception guard, SRT-walker handler, intro-movie, character-preview, overlay-widget and atomic-cache-write fixes (A-4, they change behaviour, not compilation); `bb-probe.exe` and `src/` (A-2/A-3).
- Placeholders: none — every step has its code or its exact command and expected output; the only conditional instructions are decision rules with a defined action.
- Type consistency: `BbPlatform::Usage` field names (`user_us`, `sys_us`, `invol_switches`, `vol_switches`, `minor_faults`) match between header, Windows implementation, `liverpool.cpp` and `driver.cpp`; `WorkingSetBytes()` is declared in Task 8 for both platforms and tested; `BbRecoverBuf`, `BB_RECOVER_SET`, `host_setjmp` are spelled identically in `bbport_toggles.h`, both recovery sites and the test stubs; `recorder_running` / `running` names match header and source.
