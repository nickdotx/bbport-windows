# Side-by-side test: bbhost (our fixed build of 2026-10-08) vs bbport (Supermedo windows-v1.5) — laptop first, then the RTX 3090 box

Purpose: decide which project becomes our base. Same machine, same dump, same route, same settings. Budget ~2.5 hours. Written 2026-10-07, updated the same evening for the real dump; updated 2026-10-08: the dump is complete, the bbhost column uses our fixed build (the v0.2.14 release freezes in the intro movie on Windows), the bbport column uses Supermedo's windows-v1.5 (released 2026-10-07 with DLSS).

Order: the laptop (RTX 3070 Ti 8 GB, 1920×1080, 60 FPS, no upscaling) runs each tool first, so the logs can be read live; the 3090 box then runs the full route at 1440p. Laptop status: bbhost done 2026-10-08 01:40–02:00 (run 7: launch, character creation, intro with sound, clinic, Dream, saves — all fine; performance not judged, the laptop ran on a weak charger); bbport pending.

## Dump status (complete since 2026-10-08)

The dump is Bloodborne CUSA00900 (US digital edition) with the 1.09 update merged: `sce_sys\param.sfo` says `APP_VER 01.09`, the change log lists 1.01–1.09, and the add-on licences for The Old Hunters (`SPEXPANSIONDLC03`) and both messenger hats are in it. Its `eboot.bin` is byte-identical to the CUSA03173 1.09 one, so both tools accept it:

| File | SHA-256 | Meaning |
|---|---|---|
| `CUSA00900\eboot.bin` | `d65f0b4f01d59166aed16f8604196d8b7dd805abbf0758b356e8f1354c9429f9` | the decrypted SELF as dumped |
| loaded image of it | `071df19c8880086d97182dbc057bc8cb37badaca57d9112683836b24a0444c0a` | = bbport's `SUPPORTED_IMAGE` (game check passes) |
| `out\eboot.elf` | `941f887a562aae054fac35af8cc8f27cf075f3d4cc2e029fb5ae2a663aaa5ae7` | = bbhost's required eboot hash (the SELF's own digest of the original ELF) |

The copy was interrupted on 2026-10-07 (`sce_module` and, under `dvdroot_ps4`, `script`, `sfx`, `shader`, `sound` were empty; the first bbhost run died at the first missing shader) and completed on 2026-10-08: 28,736 files under `dvdroot_ps4` (29.4 GB) and the 7 modules in `sce_module`. `python scripts\prepare.py <game> --out <dir>` passes on it (byte-exact `eboot.elf`; it names any empty or missing folder) and `scripts\link_modules.py` links both bundled modules (238 native bindings, 524 host imports, 17,127 TLS sites patched). bbhost needs the four `dvdroot_ps4` folders; bbport needs all five.

## 0. Preparation (once)

Folders (any drive; `D:\bb\` below):
- `D:\bb\game\CUSA00900\` — the dump folder above, copied as it is (plus `sce_module\` once dumped). Both tools read this folder; neither writes into it.
- `D:\bb\game\eboot.elf` — the ELF written by `scripts\prepare.py`. Check it on the 3090 box: `certutil -hashfile D:\bb\game\eboot.elf SHA256` must print `941f887a…5ae7`. (To regenerate: from this clone, `python scripts\prepare.py D:\bb\game\CUSA00900 --out D:\bb\out`; it writes `D:\bb\out\eboot.elf`, prints whether it is byte-exact and names any empty or missing dump folder.)
- `D:\bb\bbhost\` — unzip **our fixed build** of bbhost (built from our bbhost clone, branch `win-16k-dmem-and-movie`, with the CLANG64 DLLs beside the exe; check the zip's SHA-256 against the one noted when it was packaged). Not the v0.2.14 release: on Windows its intro movie freezes after ~6 s (16 KiB audio-buffer maps against the 64 KiB view granularity; fixed on our `win-16k-dmem-and-movie` branch, verified on the laptop 2026-10-08). The fixed build reads the same `%APPDATA%\bbhost\bbhost.toml`; on a new machine start `run-bbhost.bat --setup` once to enter the game folder and the `eboot.elf` path. It reports v0.0.0-unknown and never checks for updates.
- `D:\bb\bbport\` — unzip `Bloodborne-Windows.zip` of **windows-v1.5** from https://github.com/Supermedo/bloodborne_pc/releases/tag/windows-v1.5 (2026-10-07; GitHub lists its SHA-256 as `4ce2c1898fd432af100af2bde18649ca8b27dd250a2e3a3c89a9c03ccedc99e8` — check with certutil). v1.5 added DLSS Super Resolution (RTX only; stays **off** for the route); v1.3 fixed the crash at the end of the opening cutscene; v1.4 lists a known defect: the character preview on the creation screen stays empty (record it; it is acknowledged upstream). Its launcher `Bloodborne.exe` shows an update notice bottom-left when a newer build exists — decline it during the test. The first start prepares the game image into `out\` (needs `sce_module`). Settings live in `bbport.ini` beside the exe (keys such as `upscaler`, `output_res`, `live_resolution`; the launcher's own options — game folder, fullscreen, FPS mode, update check — in `%APPDATA%\bbport-launcher`), saves and shader cache in `user\`, the log in `user\last_run.log`.
- `D:\bb\results\bbhost\`, `D:\bb\results\bbport\` — logs, screenshots, your notes.

Machine:
- Latest NVIDIA Game Ready driver; Windows restarted after installing it.
- Steam Input, DS4Windows, reWASD, Discord/OBS/GeForce overlays, RivaTuner: all closed/disabled (overlays that hook Vulkan cause hangs in both tools).
- Run both tools from your normal user account, not as administrator.
- bbhost stays **offline**: do not link an account (setup window "Account", F10 > Account). If Windows Firewall asks, choose Cancel.
- DualSense on USB for the main runs. DualShock 4 and Bluetooth only in the controller checklist (§3).

Settings — identical on both, written down before starting:
- Output 2560×1440, borderless/fullscreen, frame cap 60, V-Sync off, **no upscaling** (bbport launcher: upscaler Off; bbhost F10: FSR 1 off).
- bbhost: in F10, switch every "PC enhancement" off (mirror editor, rebirth, extra invaders) so both run the game as shipped. In the setup window's **Patches** tab leave `old-hunters` **on**: it makes the game treat itself as the edition that includes The Old Hunters, which this dump is licensed for. Everything else in that tab off.
- bbport: Graphics → Upscaler **Off** (the launcher defaults to FSR 4; not DLSS, not FSR, no TAA), FPS mode **60** (the default is unlocked), output resolution 1440p (1080p on the laptop), fullscreen on, present mode Mailbox (default), object motion vectors on (default), effects at defaults, no cheats. bbport has no DLC support at all today (its AppContent answer lists zero add-ons), so The Old Hunters will not be recognised there — expected, not a defect of this run.
- 4K headroom check at the end (§2 step 9) is the only setting change.

## 1. The route — same order, same actions, ~45–60 minutes per tool

Start a stopwatch at launch; write the minute next to every observation.

1. **Launch.** Time to the title screen. Any warning or red line in the log.
2. **New game → character creation.** Is the name box visible and typeable? Does the character preview render (not black, not a white silhouette)? Finalize.
3. **Intro cinematic.** Let it play to the end. Audio in sync? Crash at the end (a known class)?
4. **Iosefka's Clinic.** Pick up the notes (item glow fades at normal speed?), open the door (animation speed), wake up in the Hunter's Dream: messengers animate normally, no replaying/popping? DLC check: the messengers at the top of the workshop steps offer the **Eye of a Blood-drunk Hunter** when the game recognises The Old Hunters (expected on bbhost with the patch on; expected absent on bbport).
5. **Central Yharnam.** Lamp → ladder → the great bridge/bonfire square (watch the carriage and wheels for ghosting) → **the sewers** (watch the brick floor and the water: ghosting, shimmer, FPS drop) → fire the pistol (rumble, blood-bullet halo timing) → use a blood vial (blood halo timing) → drop from a ledge for fall damage.
6. **Cleric Beast** if you reach it within 30 minutes (boss stability; skip otherwise).
7. **Warp to the Hunter's Dream.** Loading screen: do the item pictures appear immediately or only at the last instant? Buy a vial, spend echoes if any, **save & quit to title, Continue** — the save must load.
8. **Free play 15 minutes**, then: minimize with Win+D and restore; Alt-Tab out and back; toggle windowed/fullscreen (F11 in both).
9. **4K headroom:** set output to 3840×2160, play 5 minutes in Central Yharnam, note FPS. Quit normally.

First-run pipeline hitches (both tools compile shaders when an area is new) are normal: note them, but judge stutter on the second visit to an area.

## 2. What to record — fill one column per tool

| Item | bbhost | bbport |
|---|---|---|
| Boots to title (time) | | |
| Character creation: name box visible / preview renders | | |
| Intro cinematic complete / in sync | | |
| DLC recognised (Eye of a Blood-drunk Hunter offered in the Dream) | | (expected: no) |
| Load times: Dream↔Yharnam (s) | | |
| FPS Clinic / Central Yharnam / sewers / boss (the tool's own counter) | | |
| FPS at 4K | | |
| RAM / VRAM after 30 min (Task Manager → Details) | | |
| Crashes: minute, what you were doing, last log lines | | |
| Visual defects: skybox flicker, smearing/ghosting (sewer floor, wolf eyes, reticle), missing effects, black/wrong textures, UI glitches, pop-in (screenshot each) | | |
| Effect timing: pickup glow, blood halo, messengers, wind in grass | | |
| Audio: level, crackle, sync | | |
| Input feel: latency, missed inputs | | |
| Save/Continue works | | |
| Minimize / Alt-Tab / fullscreen toggle survive | | |
| Anything not 1:1 with the PS4 you noticed | | |

Screenshots: Win+Shift+S works in borderless mode; if the tool runs exclusive fullscreen, a phone photo is fine.

## 3. Controller checklist (after the route, each tool, DualSense USB → DualSense Bluetooth → DualShock 4 USB)

Every face/shoulder/stick/Options button registers; left and right stick full range, neutral centre; L2/R2 analog (R2 attack strength); touchpad click opens the gesture menu; touchpad left/right half press; rumble on damage and gunshot; lightbar colour; unplug and replug mid-game → control returns within a few seconds; no double input with the keyboard connected.

## 4. Decision rule

Hard gates (both must pass to be eligible): boots; finishes the route with at most one crash; save/continue works; the controller checklist passes on DualSense USB. The DLC row is informational (bbport cannot pass it yet by design).
Then: stability 40 %, visual correctness 30 %, performance 15 %, input + audio 15 %. If bbhost passes the gates it becomes the base unless bbport beats it on stability **and** visual correctness. A failed gate on one side decides it; failed gates on both sides mean we fix the one that got further.

## 5. Send back

Zip `D:\bb\results\` (bbhost: the console log — start it as `bbhost.exe 2> bbhost.log` — plus `%LOCALAPPDATA%\bbhost\` logs; bbport: `user\last_run.log` + anything crash-like in `user\` or `out\`; the filled table; screenshots) — paste the table in chat or upload the zip; I take it from there.
