# Windows host layer for bbport — design (sub-project A)

Date: 2026-10-07. Status: approved in brainstorming, pending written review.
Repository: `nickdotx/bbport-windows` (fork of `deadinside28/bloodborne_pc`), branch `windows`, based on upstream 0.3 (`4d4d208`).
Scope of the whole effort: a native Windows build of Bloodborne (CUSA03173 v1.09) for NVIDIA GPUs that is playable start to credits. This document covers only **sub-project A: the Windows host layer** — everything needed to build upstream 0.3 with a Windows toolchain and boot the game to the Hunter's Dream on an RTX 3090.

Related research (static analysis of upstream, the yumlevi/Supermedo/yaonikaixin/Mrsuss60 ports and the NielsL92 experiment, 2026-10-07): the `research/` folder kept next to the working clones (`RESEARCH_SUMMARY.md` and `reports/01..08`); it is not part of this repository.

## 1. Goals and non-goals

Goals
- Build `bb-probe.exe` (loader + HLE runtime + statically linked GPU library) from upstream 0.3 sources with MSYS2 CLANG64, with every Windows-specific line behind `#ifdef _WIN32` / `if(WIN32)` in separate files, so upstream `master` keeps merging cheaply.
- Boot a decrypted CUSA03173 v1.09 dump to gameplay on Windows 10/11 + NVIDIA: title screen, new game through character creation, Hunter's Dream, Central Yharnam, save and continue, gamepad, audio, 1080p with FSR 3.1.
- Replace each Linux facility with a Win32-native equivalent that preserves PS4 semantics (16 KiB page granularity, memory aliasing, TLS, fault-driven GPU write tracking, mutex types, absolute-time waits).
- Produce a portable zip that runs on a test machine with nothing installed, and a crash-log/return-log loop (build on the laptop, test on the RTX 3090 PC).
- Keep upstream's Linux build compiling (CI), without running it.

Non-goals for A (own sub-projects later)
- B: the bug catalog (0.3 regressions, `0x263b8e7`, texture budget, poisoned cache, device-lost survival, red-zone patcher).
- C: DLSS Super Resolution, FSR 4 v07 validation on Ampere, frame generation.
- D: DLC mounting, high-FPS game-logic fixes, boss/cutscene verification, KB/M, launcher GUI, packaging polish.
- E: reverse-engineering track (IDA) feeding B and D.
- Not supported: AMD/Intel GPUs on Windows, the 0.3 in-place (dma-buf) memory model, FSR 4.1.1 (needs a Mesa-only Vulkan extension), MSVC (the runtime relies on `__attribute__((sysv_abi))` and GNU asm).

## 2. Decisions and rationale

| Decision | Choice | Why |
|---|---|---|
| Base | upstream `master` (0.3), tracked by regular merges into `windows` | every existing Windows port is 0.2-based and conflicts with 0.3 and the announced renderer rewrite |
| Approach | fresh, thin host layer; borrow specific proven pieces with attribution | reviewable, merge-friendly, upstreamable |
| Toolchain | MSYS2 CLANG64: clang 22, libc++, lld, ThinLTO; CMake + Ninja | validated by yumlevi (PR #6) and Supermedo; matches upstream's C++23/LTO build; no winpthreads dependency |
| Host abstraction | `src/host/host.h` with `src/host/linux/*` (verbatim moves) and `src/host/win32/*` (new) | one copy of the platform-neutral logic; the upstream author plans Windows and could take this as a PR |
| Guest memory | one `VirtualAlloc2` placeholder per guest range + one pagefile-backed `SEC_RESERVE` section mapped with `MapViewOfFile3(MEM_REPLACE_PLACEHOLDER)` | 16 KiB-exact mappings and PS4-style aliasing (placeholder replacement is page-granular); lazy commit |
| Guest TLS | patch `mov rax, gs:[0]` sites to TEB `TlsSlots[slot]`, per-site stubs if slot ≥ 64 | GS is the TEB; FS base is reloaded by the kernel on context switch (`wrfsbase` is unreliable — Mrsuss60's fault-driven re-arming proves it) |
| Faults | one vectored exception handler; recovery by rewriting CONTEXT to a trampoline that longjmps after the dispatcher returns | never longjmp out of a VEH; no SEH unwinding through guest frames |
| Sync | futex-style core on `WaitOnAddress`/`WakeByAddress*`; mutex/cond/rwlock on top | exact PS4 mutex types, absolute timeouts without spin-polling, cross-thread unlock of NORMAL mutexes; SRWLOCK can't give these |
| Stacks | OS-allocated: commit = guest stack size, reserve = large linker default | TEB stack limits correct by construction; guard page preserved for the probe-less game |
| Files | HANDLE-based Win32 I/O with OVERLAPPED offsets for `pread/pwrite` | no global lock, no file-pointer juggling (yaonikaixin's global mutex and Supermedo's stale-errno bug are avoided) |
| Red zone | measure in A, patch in B | the three working ports run 10–60 min without protection; shadPS4's static patcher exists (GPL-2.0+) if measurement shows corruption |
| Exit codes | identical to upstream (2, 20, 21, 22, 23, 132, 139, 142) | reports stay comparable across platforms |

## 3. Upstream facts the design relies on

- The eboot is converted offline into `out/boot-linked.bin`; `scripts/link_modules.py` already rewrites every exact 9-byte `mov rax, fs:[0]` (17,127 sites) to `gs:` (prefix 0x65). The same image is used on both platforms.
- `src/probe.c` maps the image at `0x8_0000_0000` through `runtime_low_map` (first-fit from `LOW_MIN = 0x8_0000_0000` with a 16 KiB gap after each block), resolves imports (host contract → native PRX export → trap stub), applies patches in RAM, runs module initializers and jumps to the entry on an 8 MiB stack below 1 TiB via `enter_on_stack`.
- `src/runtime_memory.c`: guest page 16 KiB (`PAGE`), direct pool `POOL_SIZE` 5056 MiB (`BB_DMEM_MB`, 9152 above 1080p) + `FLEXIBLE_SIZE` span, one `memfd` mapped as an unprotected backing view plus `MAP_SHARED|MAP_FIXED` views at guest addresses, `fallocate(PUNCH_HOLE)` zeroing, a VMA table, `protect_locked` → `mprotect`, `runtime_memory_gpu_protect`, `store_once` label writes through the backing view. User range `USER_MIN 0x10_0000_0000 … USER_MAX 0xfc_0000_0000`.
- `src/runtime_thread.c`: guest threads are pthreads with stacks from `runtime_low_map`; FreeBSD variant-II TCB (`{tcb_self, dtv, thread}`), GS base via `arch_prctl(ARCH_SET_GS)`; `pthread_exit` via `longjmp` to the start frame; priorities/affinity recorded only.
- `src/probe.c` fault handler order: GPU page tracker (`bbgpu_handle_fault`) → per-thread recovery point (`runtime_fault_recover`, `siglongjmp`) → fatal report and `_exit(128+signal)`.
- Sync: `runtime_mutex.c` (types 2 → recursive, 3 → normal, else error-check; `timedlock` on `CLOCK_REALTIME`), `runtime_rwlock.c` (ownership registry), `runtime_sema.c` (own registry, FIFO waiters on per-waiter cond), once/keys as atomics; no futex use.
- Every `runtime_*.c` is wrapped in `#ifndef _WIN32 … #else <stub> #endif` at HEAD; `probe.c` has `VirtualAlloc/VirtualProtect` scaffolding; the vendored shadPS4 `common/` has Win32 branches for threads, files, signal context and `vk_platform.cpp` has a `VK_KHR_win32_surface` branch; `gpu/shim/window.cpp` accepts only `x11`/`wayland` SDL drivers.
- GPU library ↔ runtime contract is the C interface in `gpu/bbgpu.h` and the `runtime_*` symbols in `src/runtime.h`; `gpu/` never includes host-specific headers from `src/`.

## 4. Architecture

```
run.py ──► scripts/{game_check,mods,prepare,link_modules,content_profile,patches}.py ──► out/*.bin
   │
   └─► bb-probe.exe
         ├── src/probe.c            loader; Windows main-path branches only
         ├── src/runtime_*.c        HLE runtime, platform-neutral, calls host_*
         ├── src/host/host.h        host primitive API
         │     ├── src/host/linux/*.c   verbatim moves of today's calls (compile-only CI)
         │     └── src/host/win32/*.c   mem, tls, fault(+asm), thread, sync, time, file, crash
         └── libbbgpu.a (gpu/)      vendored shadPS4 core + bbport shim; Windows bits in gpu/shim/win32/
```

Threads: the Windows process keeps upstream's thread topology (GPU command processor, draw recorder, prep workers, Vulkan recorders, copy threads, present, window, kernel service, guest threads). The guest entry runs on a dedicated host thread created by the loader (`main` waits on it), not on the process main thread.

## 5. Components

### 5.1 `src/host/host.h` — host primitive API

All functions are plain C, no PS4 semantics, no knowledge of the VMA table or guest objects. Names and groups (Linux implementation in parentheses):

Memory (`host/linux/mem.c` = memfd/mmap code moved from `runtime_memory.c`)
- `int host_mem_init(uint64_t pool_bytes, uint64_t flex_bytes)` — reserves the guest ranges, creates the pool, maps the backing view.
- `uint8_t *host_mem_backing(void)` — unprotected alias of pool + flexible span.
- `int host_mem_map(uintptr_t addr, uint64_t size, uint64_t phys, int prot)` — view of pool offset `phys` at guest `addr`.
- `int host_mem_unmap(uintptr_t addr, uint64_t size)` — may split an existing view; survivors keep their protections.
- `int host_mem_protect(uintptr_t addr, uint64_t size, int prot)` — 4 KiB granularity.
- `void host_mem_zero(uint64_t phys, uint64_t size)` — zero released physical memory (hole punch on Linux, memset of committed pages on Windows).
- `uintptr_t host_mem_blocked_end(uintptr_t addr, uint64_t size)` — 0, or the end of a host-occupied span overlapping the request (first-fit must skip it).
- `int host_low_map(uintptr_t addr, uint64_t size, int prot)` / `int host_low_unmap(uintptr_t addr, uint64_t size)` — private fixed blocks in the low arena (image, trap stubs, TLS templates).
- `void *host_low_alloc(size_t bytes, size_t align)` / `void host_low_free(void *p)` — host objects the guest holds pointers to.

TLS (`host/linux/tls.c` = `arch_prctl`)
- `int host_tls_init(void)` — Windows: `TlsAlloc`, must run before `host_tls_patch`.
- `size_t host_tls_patch(uint8_t *code, size_t len, uint8_t *stubs, size_t stubs_len)` — Windows: rewrites every `65 48 8B 04 25 00 00 00 00` in `code`; returns the number of sites; Linux: no-op returning 0.
- `void host_tls_set_tcb(void *tcb)` / `void *host_tls_get_tcb(void)`.

Faults (`host/linux/fault.c` = `sigaction` + `sigsetjmp` code moved from `probe.c`)
- `typedef struct host_jmpbuf host_jmpbuf;` `int host_setjmp(host_jmpbuf *)`, `void host_longjmp(host_jmpbuf *, int)` — asm on Windows (saves rbx, rbp, rdi, rsi, r12–r15, rsp, return address, xmm6–15, MXCSR, x87 control word); `sigsetjmp(buf, 1)`/`siglongjmp` on Linux.
- `void host_fault_install(const host_fault_hooks *hooks)` — hooks: `gpu_fault(ctx, addr, is_write) → handled`, `guest_breakpoint(ctx) → handled`, `report(ctx)`.
- `void host_fault_set_recovery(host_jmpbuf *buf)` — thread-local recovery point; NULL clears.
- `void host_fault_watchdog(unsigned seconds)` — 0 disables.

Threads (`host/linux/thread.c` = pthreads)
- `int host_thread_create(host_thread **t, void (*entry)(void *), void *arg, size_t stack_commit, const char *name)`, `int host_thread_join(host_thread *)`, `void host_thread_detach(host_thread *)`, `uint32_t host_thread_id(void)`, `void host_thread_set_name(const char *)`, `void host_thread_yield(void)`, `void host_thread_exit_cleanup(void)`.

Sync (`host/linux/sync.c` = pthread mutex/cond/rwlock)
- `host_mutex_{init(type),lock,trylock,timedlock(abs_realtime_ns),unlock,destroy}` with types NORMAL, ERRORCHECK, RECURSIVE.
- `host_cond_{init,wait,timedwait(abs_ns, clock),signal,broadcast,destroy}`.
- `host_rwlock_{init,rdlock,wrlock,tryrdlock,trywrlock,timedrdlock,timedwrlock,unlock,destroy}`.
- `host_once`, keys stay in `runtime_kernel.c` (platform-neutral atomics).

Time (`host/linux/time.c` = `clock_gettime`/`nanosleep`)
- `uint64_t host_clock_ns(host_clock id)` for MONOTONIC, REALTIME, THREAD_CPU, PROCESS_CPU; `void host_sleep_ns(uint64_t)`, `void host_sleep_until_ns(host_clock, uint64_t abs)`, `int host_tz_offset_seconds(void)`.

Files (`host/linux/file.c` = POSIX)
- `host_file_{open(path_utf8, flags, mode),close,read,write,pread,pwrite,lseek,fstat,stat,fsync,truncate}`, `host_dir_{open,next,close}`, `host_mkdir`, `host_rmdir`, `host_unlink`, `host_rename`, `host_remove_tree` (refuses reparse points on Windows), with a `host_stat` struct the runtime converts to the FreeBSD layout it already emits.

Misc
- `int host_random_bytes(void *, size_t)`, `unsigned host_cpu_count(void)`, `int host_process_restart(const char *const argv[])`, `const char *host_log_dir(void)`.

Rules: `gpu/` never includes `src/host/win32/*`; `src/runtime_*.c` never calls a Win32 or POSIX API directly after this change; every Windows function that can fail returns an error after logging the operation, `GetLastError()` and the request.

### 5.2 `src/host/win32/mem.c` — guest memory

Layout and reservation
- `bb-probe.exe` is linked with `--disable-high-entropy-va` (lld) so bottom-up allocations (heaps, stacks) stay in the low gigabytes; the first statement of `main` calls `host_mem_init`, before any thread or large allocation.
- Reservation walks `[0x8_0000_0000, 0xfc_0000_0000)` with `VirtualQuery`; every free run is reserved with `VirtualAlloc2(MEM_RESERVE | MEM_RESERVE_PLACEHOLDER, PAGE_NOACCESS)`; occupied runs are recorded as *blocked* spans and reported by `host_mem_blocked_end` so upstream's first-fit allocator (`runtime_low_map`, direct/flexible map hints) skips them. A span table (sorted, binary search) tracks placeholder / view / blocked state per range.
- The pool is `CreateFileMappingW(INVALID_HANDLE_VALUE, PAGE_EXECUTE_READWRITE | SEC_RESERVE, pool + flex)`; the backing view is `MapViewOfFile(FILE_MAP_ALL_ACCESS | FILE_MAP_EXECUTE)` of the whole section at an OS-chosen address (host-only, never handed to the guest).
- Requires Windows 10 1803+ (`VirtualAlloc2`, `MapViewOfFile3`, `UnmapViewOfFile2` resolved from kernelbase at startup; a clear message and exit 21 otherwise).

Mapping
- `host_mem_map(addr, size, phys, prot)`: commit `[phys, phys+size)` of the section through the backing view (`VirtualAlloc(MEM_COMMIT)`), clear any views inside `[addr, addr+size)` (see unmap), split the placeholder at `addr` and `addr+size` (`VirtualFree(MEM_RELEASE | MEM_PRESERVE_PLACEHOLDER)`), map with `MapViewOfFile3(section, process, addr, phys, size, MEM_REPLACE_PLACEHOLDER, PAGE_EXECUTE_READWRITE)`, then `VirtualProtect` down to `prot`. Views are always created with full access because a view born read-only cannot later gain write.
- 16 KiB granularity: placeholder splitting and replacement are page-granular; a unit test maps at a 16 KiB-aligned, 64 KiB-misaligned address and offset and verifies aliasing through the backing view before anything else is built on it.
- `host_mem_unmap(addr, size)`: for each view overlapping the range: snapshot its page protections with `VirtualQuery`, `UnmapViewOfFile2(MEM_PRESERVE_PLACEHOLDER)` the whole view, split the placeholder at the request boundaries, remap the surviving left/right pieces at their original section offsets, restore the snapshot protections (including GPU tracking protections), then coalesce adjacent free placeholders (`MEM_COALESCE_PLACEHOLDERS`).
- `host_mem_protect` → `VirtualProtect` with the prot → `PAGE_*` map (`PAGE_NOACCESS`, `PAGE_READONLY`, `PAGE_READWRITE`, `PAGE_EXECUTE*`).
- `host_mem_zero(phys, size)`: memset of the committed pages of the range through the backing view (uncommitted pages are already zero). Windows cannot decommit `SEC_RESERVE` pages; commit stays at its high-water mark for the session. Documented requirement: free RAM + page file ≥ ~6 GB at 1080p, ~10 GB at 1440p/4K.
- Reserved ranges (`sceKernelReserveVirtualRange`) stay placeholders and are only tracked in the VMA table; the flexible span uses section offsets beyond the pool, so `posix_mmap`-served heap growth needs no new mechanism.

Low arena
- `host_low_map(addr, size, prot)`: split the low placeholder and `VirtualAlloc2(MEM_RESERVE | MEM_COMMIT | MEM_REPLACE_PLACEHOLDER)` private pages; upstream's 16 KiB unmapped gap after each block is kept (it stays a placeholder, so any access faults).
- `host_low_alloc`: a bump allocator with size-class free lists over 1 MiB chunks obtained through `host_low_map`; replaces the `mallopt(M_ARENA_MAX)` trick. Used for `GuestThread`, TCBs, static TLS blocks, mutex/cond/rwlock/semaphore objects whose addresses the guest keeps.

Stacks
- No stack switching on Windows. `enter_on_stack` is Linux-only; on Windows the loader creates the guest main thread with `host_thread_create(entry, …, 16 MiB, "guest:main")` and waits for it. Guest threads: `_beginthreadex(stack_size = attr stack + 256 KiB margin)` with no `STACK_SIZE_PARAM_IS_A_RESERVATION`, so the size is *committed*; the PE default stack reserve is raised to 64 MiB (`-Wl,--stack=0x4000000,0x10000`) so every thread keeps a guard region above the commit. A startup assert checks that the main guest stack and the first guest thread stack are below 1 TiB.
- `scePthreadAttrGetStack*` answers from the TEB (`NtCurrentTeb()->StackBase/StackLimit`) through `host_thread_stack_bounds`.

### 5.3 `src/host/win32/tls.c` — guest TLS

- `host_tls_init` calls `TlsAlloc()` at the top of `main` (after `host_mem_init`); the slot index is logged.
- `host_tls_patch(code, len, stubs, stubs_len)` scans executable segments for the exact bytes `65 48 8B 04 25 00 00 00 00`:
  - slot < 64: overwrite the 4-byte displacement with `0x1480 + 8·slot` (TEB `TlsSlots`); same instruction length, no control-flow change.
  - slot ≥ 64: replace the 9 bytes with `E9 rel32` + 4 `NOP`s to a per-site stub in `stubs` (allocated by the loader in the low arena, RX): `mov rax, gs:[0x1780]` (TEB `TlsExpansionSlots`), `mov rax, [rax + 8·(slot−64)]`, `jmp back`. The stub never touches flags, other registers or the stack.
  - Patching runs on the loader thread before any guest thread exists, followed by `FlushInstructionCache`.
  - Diagnostics: counts patched sites (expected 17,127 incl. linked PRXs) and any remaining `64`-prefixed (FS) memory access found by a conservative byte scan; both printed at startup.
- `host_tls_set_tcb(tcb)` = `TlsSetValue(slot, tcb)`; the TCB layout, static TLS template copy and the HLE `__tls_get_addr` in `src/runtime.c` are unchanged. The loader calls it for the guest main thread; `runtime_thread.c` calls it at every guest thread start and for host threads that enter guest code (lazy attach, as today).
- Interaction with the Linux rewrite: the image's `gs:` prefix is kept; on Linux `host_tls_patch` is a no-op and `arch_prctl` sets GS; on Windows the displacement patch makes `gs:[disp]` read the TEB slot.

### 5.4 `src/host/win32/fault.c` + `host_setjmp.S` — exceptions and recovery

- `host_fault_install` registers one handler with `AddVectoredExceptionHandler(1, handler)` and sets `SetUnhandledExceptionFilter` to the same reporting path.
- Handler order for `EXCEPTION_ACCESS_VIOLATION`:
  1. `hooks->gpu_fault(ctx, addr, ExceptionInformation[0] == 1)` — the vendored `Core::Signals`/page-manager path (write faults unprotect a window and mark pages dirty; read faults with precise readbacks); handled → `EXCEPTION_CONTINUE_EXECUTION`.
  2. If the thread has a recovery point (`host_fault_set_recovery`): rewrite the CONTEXT — `Rcx = buf`, `Rdx = 1`, `Rip = host_longjmp`, `Rsp = (faulting Rsp − 256) & ~15` — and return `EXCEPTION_CONTINUE_EXECUTION`. The thread resumes in `host_longjmp` after the OS dispatcher has unwound; the handler itself never longjmps.
  3. Otherwise fatal: `hooks->report(ctx)` writes the crash log, then `TerminateProcess(139)`.
- `EXCEPTION_BREAKPOINT` → `hooks->guest_breakpoint(ctx)` (the dormant `int3` hooks of `bbport_guest_hooks.cpp`; unhandled → fatal). `EXCEPTION_ILLEGAL_INSTRUCTION`/`PRIV_INSTRUCTION` → crash log, exit 132 (with a hint naming MOVBE/BMI1/LZCNT when the CPU lacks them). `EXCEPTION_STACK_OVERFLOW` → crash log naming the thread, exit 139. `DBG_PRINTEXCEPTION_C` and the MSVC thread-name exception are passed through.
- `host_setjmp/host_longjmp`: hand-written x86-64 asm (GNU syntax, assembled by clang) saving rbx, rbp, rdi, rsi, r12–r15, rsp, the return address, xmm6–xmm15, MXCSR and the x87 control word; `host_longjmp` restores them and returns the value. This is also what `runtime_thread.c` uses for guest `pthread_exit`.
- Crash log (`out/crash-YYYYMMDD-HHMMSS.log`, duplicated on stderr): exception code and address, faulting thread id and name, guest offset when `Rip` lies inside the image, host module+offset otherwise (`GetModuleHandleEx` + `GetModuleFileName`), integer and SSE registers, an RBP chain of up to 64 frames read with `ReadProcessMemory(GetCurrentProcess())`, each annotated with guest offset or module+offset, and the last `BB_WRITE_LOG` entries when that log is enabled.
- Watchdog (`host_fault_watchdog`): a thread that sleeps `BB_TIMEOUT` seconds; on expiry it enumerates threads with `CreateToolhelp32Snapshot`, suspends them, prints `Rip` and an RBP chain per thread via `GetThreadContext`, and exits 142. Replaces `SIGALRM`/`SIGUSR2`.
- Red-zone hazard: Windows places the exception dispatch frame directly below the faulting RSP, overwriting the 128-byte SysV red zone of guest code; by the time any handler runs the bytes are already gone, so corruption cannot be observed at fault time. In A this is **measured, not fixed**: with `BB_FAULT_SITES=1` the GPU-fault hook keeps a histogram of faulting guest RIPs (guest offsets) and writes the top 200 sites with counts to `out/fault-sites.log` at exit. Sub-project B runs a static liveness analysis over those sites (Zydis, function starts from the eboot's `.eh_frame`, the same analysis shadPS4's patcher performs) to find sites where red-zone bytes are live across the faulting instruction; if any exist, B ports shadPS4's static red-zone patcher (`src/core/cpu_patches.cpp`, GPL-2.0+). The patcher moves into A only if A's acceptance runs show crashes or corruption attributable to such sites.

### 5.5 `src/host/win32/thread.c`, `sync.c`, `time.c`

- Threads: `_beginthreadex` with the commit size, `SetThreadDescription`, `GetCurrentThreadId`, `SwitchToThread`; join/detach on the handle; `host_thread_exit_cleanup` runs TLS key destructors (upstream code) and `TlsSetValue(slot, NULL)`. Priorities and affinity remain recorded only (parity with Linux).
- Sync core (`sync.c`): `host_futex_wait(addr32, expected, abs_ns, clock)` on `WaitOnAddress` (computes the relative timeout, retries on spurious wakeups until the deadline) and `host_futex_wake(addr32, count)` on `WakeByAddressSingle/All`.
  - Mutex: `{owner_tid, count, waiters, type}`; NORMAL does not check ownership (so a different thread may unlock it, as some PS4 code does); ERRORCHECK returns EDEADLK/EPERM; RECURSIVE counts; `timedlock` honours the absolute `CLOCK_REALTIME` deadline the runtime passes.
  - Cond: sequence word + waiter count; `timedwait` with the clock the runtime specifies (REALTIME for PS4 condvars, MONOTONIC for the semaphore registry's per-waiter conds); no lost wakeups (the sequence is read under the mutex before waiting).
  - Rwlock: writer-preferring state word with reader count; upstream's ownership registry stays on top. Timed variants map to the futex deadline.
- Time: `host_clock_ns`: MONOTONIC = `QueryPerformanceCounter` scaled to ns; REALTIME = `GetSystemTimePreciseAsFileTime` → Unix epoch ns; THREAD_CPU/PROCESS_CPU = `GetThreadTimes`/`GetProcessTimes`. `host_sleep_ns`/`host_sleep_until_ns`: per-thread `CreateWaitableTimerExW(CREATE_WAITABLE_TIMER_HIGH_RESOLUTION)` with a 100 ns-unit relative due time, finishing with a bounded spin (≤ 200 µs) for sub-millisecond accuracy; `timeBeginPeriod(1)` once at startup; the process is excluded from EcoQoS (`PROCESS_POWER_THROTTLING_EXECUTION_SPEED` off). `rdtsc` and the TSC-frequency calibration are unchanged. `host_tz_offset_seconds` from `GetTimeZoneInformation`.

### 5.6 `src/host/win32/file.c`

- Descriptors: a table of `{HANDLE, flags, is_dir, listing}`; `host_file_open` converts UTF-8 to UTF-16 (`MultiByteToWideChar`) and prefixes `\\?\` for long paths; flags map to `CreateFileW` (`O_CREAT/O_TRUNC/O_EXCL` → creation disposition, `O_DIRECTORY` → open with `FILE_FLAG_BACKUP_SEMANTICS` and a lazy `FindFirstFileExW` listing).
- `read/write` → `ReadFile/WriteFile` at the current position; `pread/pwrite` → `ReadFile/WriteFile` with an `OVERLAPPED` offset on a handle opened without `FILE_FLAG_OVERLAPPED` (synchronous positional I/O, no shared file pointer, no lock); `lseek` → `SetFilePointerEx`; `fstat/stat` → `GetFileInformationByHandleEx`/`GetFileAttributesExW` → `host_stat` (size, mode bits, mtime/ctime as ns since the epoch); `fsync` → `FlushFileBuffers`; `truncate` → `SetFilePointerEx` + `SetEndOfFile`; `rename` → `MoveFileExW(MOVEFILE_REPLACE_EXISTING)`; `unlink/rmdir/mkdir` → `DeleteFileW/RemoveDirectoryW/CreateDirectoryW`; `host_remove_tree` walks with `FindFirstFileExW` and refuses `FILE_ATTRIBUTE_REPARSE_POINT` entries.
- Errors map to the FreeBSD errno values upstream expects (`ERROR_FILE_NOT_FOUND`/`PATH_NOT_FOUND` → ENOENT, `ERROR_ACCESS_DENIED` → EACCES, `ERROR_ALREADY_EXISTS`/`FILE_EXISTS` → EEXIST, `ERROR_DIR_NOT_EMPTY` → ENOTEMPTY, `ERROR_SHARING_VIOLATION` → EBUSY). Errno is computed per call from `GetLastError()`, never left stale.
- The game's own mounts, fd table, path normalisation (`/app0`, `/hostapp`, `/savedata0–15`, `/temp0`, `/download0`, `/data`), save-data layout and the "sound hack" are untouched. NTFS case-insensitivity is a superset of what the game needs.

### 5.7 `gpu/` Windows bits (`gpu/shim/win32/` + guarded edits)

- `gpu/shim/window.cpp`: accept SDL's `windows` video driver; expose the HWND through `SDL_PROP_WINDOW_WIN32_HWND_POINTER`; `vk_platform.cpp`'s existing `VK_KHR_win32_surface` branch is enabled; borderless fullscreen for `BB_FULLSCREEN=1`; on `SDL_EVENT_WINDOW_MINIMIZED` / a 0×0 swapchain extent the presenter skips presents and defers swapchain recreation until restore (fixes the exit-23 of upstream issue #31).
- `gpu/shim/bbport_threads.h`: `THREAD_PRIORITY_IDLE` for speculative helpers instead of `SCHED_IDLE`; hardware-thread count from `GetProcessAffinityMask`.
- `gpu/shim/bbport_guest_memory.cpp` (dma-buf chunks) and the `userfaultfd` path of `page_manager.cpp` are compiled out on Windows; `BB_GUEST_IN_PLACE` is forced to 0 with a log line.
- `videoout/driver.cpp` `Memory:` line: process RSS/commit from `GetProcessMemoryInfo`, VRAM from `VK_EXT_memory_budget` (as today).
- `vk_scheduler.cpp`, `vk_breadcrumbs.cpp`, `bbport_write_log.cpp`, `bbport_free_check.cpp`, `bbport_wait_trace.cpp`: `gettid`/`process_vm_readv`/`dladdr` replaced by `GetCurrentThreadId`/`ReadProcessMemory`/module lookup through small inline helpers in `gpu/shim/win32/host_diag.h`.
- `gpu/shadps4/video_core/page_manager.cpp`: the Windows protect path goes through `runtime_memory_gpu_protect` → `host_mem_protect` (the vendored copy lost upstream's direct `VirtualProtect` branch; the runtime path is the one bbport already uses on Linux).
- HLE boundary guard (`gpu/shim/core/libraries/libs.h`): on Windows the `LIB_FUNCTION` wrapper template catches every C++ exception, logs it once per function name, and returns a failure value chosen from the wrapped function's return type: `ORBIS_KERNEL_ERROR_EINVAL` (`0x80020016`) for `s32`/`int` returns, `0` for other integers, `nullptr` for pointers, nothing for `void` — because libc++ exceptions cannot unwind through guest frames. The same guard pattern (not the same code) is yumlevi's.
- Windows/libc++ correctness and performance fixes required to reach the acceptance point (each cherry-picked from the named source with attribution, verified against 0.3's code first):
  - `Scheduler::IsRecordingDeferred`/`Record`/`BindHelper::Available`: replace `std::jthread::joinable()` per draw with flags (yumlevi PR #6 — on libc++/Windows it is a `GetThreadId` syscall costing ~70 % of the draw-recording thread).
  - `flatten_extended_userdata_pass.cpp`: register the fault handler for SRT walkers loaded from the pipeline cache and guard the walker patch with a mutex (yumlevi — otherwise the second start after a cache write crashes).
  - `gpu/shim/core/libraries/kernel/threads.h`: thread-safe `Kernel::Thread`, a thread stopping itself detaches, `Join` catches `std::system_error` (yumlevi + Supermedo 1.3 — intro movie end).
  - `texture_cache.cpp`: `MarkAsMaybeDirty`/`RefreshImage` hash the same range and record baseline hashes on upload (yumlevi — black character-creation preview).
  - `bbport_overlay.cpp`: evaluate the widget call before `Store(...)` (yumlevi — clang evaluation order made checkboxes/sliders inert).
  - `regs.h` bit scan and `texture_cache.h` atomic loads guarded for `_LIBCPP_VERSION`; `lru_cache.h` early-stop comparison fixed (`std::invoke_result_t`, not the trait).
  - `cache_storage.cpp`: write pipeline/shader cache blobs to a temp file and rename atomically (Supermedo 1.1) so a crash cannot leave a truncated cache.

### 5.8 Build system

- Root `CMakeLists.txt` (Windows only; `build.sh` stays for Linux): targets `bb-probe` (C11, `-O2 -Wall -Wextra -Werror`, `-fno-omit-frame-pointer`, links `libbbgpu.a`, `libatrac9.a`, SDL3, vulkan-1, kernel32/user32/winmm/bcrypt/dbghelp), `bb-gpu-capabilities`, the C test executables, and `host_setjmp.S`. Linker flags: `--disable-high-entropy-va`, `--stack=0x4000000,0x10000`, `-mconsole`, manifest with `longPathAware` and PerMonitorV2 DPI awareness.
- `gpu/CMakeLists.txt`: `if(WIN32)`: `STATIC` library, no X11/Wayland, `magic_enum`/`miniz`/`xbyak` from `gpu/third_party/` submodules (added to `.gitmodules`), FFmpeg/boost/fmt/xxhash/zydis/VMA/glslang from MSYS2 pkg-config; `-fno-exceptions` is **not** used (the HLE guard needs exceptions). ThinLTO on for release, off for CI.
- Toolchain file `cmake/clang64.cmake` records the compiler, flags and the MSYS2 prefix; `msys2-packages.txt` lists the `pacman` packages: `mingw-w64-clang-x86_64-{clang,lld,libc++,cmake,ninja,pkgconf,python,sdl3,boost,fmt,glslang,spirv-cross,spirv-headers,vulkan-headers,vulkan-loader,vulkan-memory-allocator,xxhash,zydis,robin-map,ffmpeg}` plus `git`; vulkan-headers ≥ 1.4.350.
- `scripts/patches.py`: CPU vendor from the registry (`HKLM\HARDWARE\DESCRIPTION\System\CentralProcessor\0`) instead of `/proc/cpuinfo`; `scripts/mods.py`: junctions for directories, hard links for files, copy fallback across volumes; `tests/test_pad.c` uses `_putenv_s` through a `setenv` shim.

### 5.9 `scripts/game_check.py`, `run.py`, packaging, CI

- Game check: hash table of verified executables (CUSA03173 v1.09 today; CUSA00900/CUSA03023 added once a dump has been played); for an unverified title/version it prints `title`, `APP_VER`, the executable hash and continues only with `BB_SKIP_GAME_CHECK=1`. Explains: an unmerged `*-patch`/`*-UPDATE` sibling folder, `APP_VER` < 01.09, missing `sce_module/libc.prx` or `libSceFios2.prx`, missing `dvdroot_ps4`; reports whether DLC files exist. Exit 2 with text.
- `run.py` (Windows driver, same pipeline as `run.sh`): options `--game-dir`, `--user-dir`, `--data-dir`, `--fps {30,60,90,uncap}`, `--fps-limit`, `--output-res`, `--upscaler`, `--preset`, `--fullscreen/--windowed`, `--present-mode`, `--prebuilt`, `--dry-run`, `--check`, `--vulkan-info`, `--smoke` (replay the recorded boot route with a timeout and verify the Hunter's Dream load in the log), `--after <pid>`; steps: game check → mod overlay → `prepare.py` → `link_libc.py` → `link_modules.py` → `content_profile.py` → settings/resolution/vblank computation (ported from `run.sh`) → `patches.py` → environment → `bb-probe.exe out/boot-linked.bin --content-profile … --patches … --app0 … --user … --timeout …` with stdout/stderr tee'd to `out/last-run.log` (rotating 5); exit-code explanation table printed on failure. `run.bat` double-click wrapper uses the embedded Python.
- `packaging/windows/package.py`: assembles `dist/bbport-windows-<sha>/` = `bin/` (exes + DLL closure from `ldd`), `python/` (embeddable CPython 3.12 x64 + the stdlib zip; no third-party packages needed), `scripts/`, `patches/`, `fsr4_shaders/` (FSR 4 v07 assets fetched by `tools/fetch_fsr4_assets.py`, a Python port of the shell script), `run.py`, `run.bat`, `README-Windows.md`, `LICENSES/` (bbport GPL-2.0+, shadPS4, FSR-Vulkan, LibAtrac9, ImGui, SDL3, FFmpeg, boost, fmt, xxhash, zydis, libc++, mingw-w64 runtime notices), `VERSION`; zips it.
- CI: `.github/workflows/windows.yml` (msys2/setup-msys2 → CLANG64 packages → CMake/Ninja build → CTest → `package.py` → artifact; release assets on `v*` tags) and `.github/workflows/linux-compile.yml` (cachix/install-nix-action → `nix-shell shell.nix --run "BB_LTO=0 bash build.sh --test"` → `python3 -m unittest discover -s tests`). Linux is compiled and unit-tested, never run with the game.
  The Windows job follows the step structure of DarkIzuku/bloodborne_pc's `windows-offline-build.yml`, which has been green on `windows-latest` since 2026-10-06 for a yumlevi-based tree: `actions/checkout` with recursive submodules, `msys2/setup-msys2` with `msystem: CLANG64`, `update: true` and exactly the package list of §5.8, a 90-minute timeout, `actions/setup-python` 3.12 followed by downloading `python-<ver>-embed-amd64.zip` from python.org into `package/python/` with `..\..\scripts` appended to its `python3*._pth`, the DLL closure computed by `ldd` on each exe filtered to `/clang64/bin/*.dll`, and `actions/upload-artifact` on the package directory. Differences: our build step is the root CMake project + CTest instead of `build.sh`, no launcher is published, and no DLSS/FSR 4 assets are fetched in A. Developer note for `README-Windows.md`: set `git config core.longpaths true` before cloning forks that vendor `SPIRV-Headers` as files (their paths exceed `MAX_PATH`); our tree does not need it.

## 6. Data flow at startup (Windows)

1. `run.py` validates the game folder, builds the overlay, runs the preparation scripts, computes settings, launches `bb-probe.exe` with the same arguments and environment `run.sh` would use.
2. `main`: `host_mem_init` (reserve ranges, create section) → `host_tls_init` → `host_fault_install` → `timeBeginPeriod` → parse `boot-linked.bin` → `host_low_map` the image at `0x8_0000_0000` → `host_tls_patch` over executable segments → trap stubs → `bbgpu_init` (window thread, Vulkan device, static library) → relocations/imports → in-RAM patches → protections → TLS templates → `host_thread_create("guest:main")` which attaches its TCB, runs module initializers and jumps to the entry; `main` waits and returns the guest's exit status.
3. Guest `sceKernelMapDirectMemory` → `runtime_memory.c` VMA bookkeeping (unchanged) → `host_mem_map`; GPU write tracking → `runtime_memory_gpu_protect` → `host_mem_protect`; a guest write to a tracked page → VEH → `gpu_fault` hook → unprotect window → continue.
4. Audio/pad/window: SDL3 on their existing threads; present via `bb:Present` with the Win32 surface.
5. Exit: window close → 0; guest `exit(n)` → n; faults → crash log + 139/132; GPU assert → 23; watchdog → 142.

## 7. Testing

- `tests/test_host_win32.c` (CTest, no GPU): memory — reserve, map at a 16 KiB-aligned/64 KiB-misaligned address and offset, alias visibility both ways, partial unmap keeps neighbours and their protections, protect/unprotect round trip, zero-on-reuse, blocked spans honoured; TLS — synthetic 9-byte site patched and executed on two threads with distinct TCBs, forced slot ≥ 64 stub path; faults — recoverable read of a `PAGE_NOACCESS` page via `host_fault_set_recovery`, nested recovery points, fatal path exercised in a child process that must exit 139 and leave a crash log; sync — NORMAL/ERRORCHECK/RECURSIVE semantics, cross-thread unlock of NORMAL, `timedlock` and `cond_timedwait` deadlines within 2 ms, no lost wakeup under a 4-thread stress loop; time — `host_sleep_ns(1 ms)` within 300 µs on average, monotonic clock never regresses across threads; files — concurrent `pread/pwrite` from 4 threads, UTF-8 names, listing, rename-replace, `remove_tree` refusing a junction.
- Upstream's C tests (`test_runtime`, `test_sema`, `test_content`, `test_pad`, `test_file_mods`) built and run under CTest on Windows; upstream's Python tests run where platform-neutral (`test_prepare`, `test_link_libc`, `test_patches`, `test_mods` with junctions, `test_game_check` extended, `test_probe`, `test_run_settings` adapted to `run.py`).
- Upstream's C++ renderer tests that need no Vulkan device (`motion-history-test`, `motion-shader-test`, `ui-composition-test`) build and run on Windows: `tests/test_gpu_runtime_stubs.cpp` declares `runtime_fault_recover` as a thread-local `host_jmpbuf *` and stubs `host_setjmp`/`host_longjmp`, and the targets link `winmm ws2_32 psapi onecore` (the arrangement DarkIzuku's CI uses with yumlevi's names). The device-dependent ones (`scene-resolution-test`, `taa-shader-test`, `camera-motion-test`, `upscaler-support-test`) run only when a Lavapipe ICD is present on the machine and are otherwise reported as skipped, not failed.
- Smoke route: a `BB_PAD_FILE` script (title → new game → character creation defaults → Hunter's Dream) recorded on the RTX 3090 PC; `run.py --smoke` replays it with `BB_TIMEOUT` and checks the log for the Hunter's Dream map load.
- Manual acceptance on the RTX 3090 PC per §9; logs and crash files returned for every run.

## 8. Error handling and exit codes

| Situation | Behaviour | Exit |
|---|---|---|
| Game folder wrong/unmerged/unknown | `game_check.py` explains | 2 |
| OS < Windows 10 1803, placeholder/section/view/protect/thread/timer failure | log operation + `GetLastError` + request, stop | 21 |
| Unresolved PS4 import | upstream message | 20 |
| Guest stack protector | upstream | 22 |
| GPU library assertion, guest `sceKernelDebugRaiseException` | upstream | 23 |
| Access violation / stack overflow not handled | crash log | 139 |
| Illegal instruction | crash log + ISA hint | 132 |
| Watchdog timeout | thread dump | 142 |
| Window closed / guest exit | as upstream | 0 / n |

No Windows code path silently returns success on an OS failure; no import is silently stubbed.

## 9. Acceptance criteria (definition of done for A)

1. `cmake --build` and `ctest` pass on the laptop (MSYS2 CLANG64), including `test_host_win32`.
2. The zip runs on the RTX 3090 PC with the user's dump: game check passes; title screen; new game through character creation; Hunter's Dream; Central Yharnam; save and continue; gamepad and audio; 1080p output with FSR 3.1 (Native AA or Quality).
3. 15 minutes in Central Yharnam without a crash at 1080p.
4. Minimize and Alt-Tab do not end the session.
5. Every fatal fault leaves `out/crash-*.log` with a guest offset or module+offset.
6. Both CI workflows green on the `windows` branch.

## 10. Risks and open questions

- Red-zone corruption on guest threads (see §5.4): measured in A; the static patcher is scheduled for B and pulled forward if the measurement shows live-data hits.
- Commit high-water mark: 6–10 GB of commit without decommit; acceptable on the target PC, documented in the README; a chunked-section scheme is the fallback.
- Title IDs other than CUSA03173: the executable hash of the user's dump is unknown until first run; the game check reports it and `BB_SKIP_GAME_CHECK=1` continues.
- Linux compile-only CI build time (full shadPS4 core): mitigated with `BB_LTO=0` and ccache; if it exceeds 60 minutes it moves to a weekly schedule.
- Upstream churn: the author rewrites `runtime_memory.c`/`vk_scheduler.*` often and has announced a renderer rewrite; the host layer keeps all Windows code in `src/host/win32/`, `gpu/shim/win32/` and `#ifdef` islands to keep merges mechanical.
- Attribution: pieces modelled on yumlevi (TLS stubs, libc++ fixes), Supermedo (VEH recovery pattern, atomic cache writes), yaonikaixin (partial-unmap sequence, minimize gating), DarkIzuku (CI step structure, embeddable-Python packaging, renderer-test stubs) and shadPS4 (placeholder/section scheme, TEB offsets) are GPL-2.0+; each borrowed piece is credited in the file header and in `THIRD_PARTY.md`.
- DarkIzuku/bloodborne_pc (yumlevi-derived; branches `offline-performance-precache-*`, `custom-loading-screens-v1`, `launcher-redesign-v2`) also carries pipeline-cache persistence/precache work, image-overlap and texture-memo validation, and an unfinished investigation of the loading-screen glyph flicker (upstream #11); these are leads for sub-project B, not inputs to A. Its WPF launcher ships game artwork and is not reused.
- Trademark: the fork is named `bbport-windows`; the game's name is not used in the project name or binaries.
