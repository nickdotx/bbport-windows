# Side-by-side test: bbhost v0.2.14 vs bbport (Supermedo windows-v1.4) — RTX 3090 box

Purpose: decide which project becomes our base. Same machine, same dump, same route, same settings. Budget ~2.5 hours. Written 2026-10-07, updated the same evening for the real dump.

## Dump status (verified 2026-10-07)

The dump is Bloodborne CUSA00900 (US digital edition) with the 1.09 update merged: `sce_sys\param.sfo` says `APP_VER 01.09`, the change log lists 1.01–1.09, and the add-on licences for The Old Hunters (`SPEXPANSIONDLC03`) and both messenger hats are in it. Its `eboot.bin` is byte-identical to the CUSA03173 1.09 one, so both tools accept it:

| File | SHA-256 | Meaning |
|---|---|---|
| `CUSA00900\eboot.bin` | `d65f0b4f01d59166aed16f8604196d8b7dd805abbf0758b356e8f1354c9429f9` | the decrypted SELF as dumped |
| loaded image of it | `071df19c8880086d97182dbc057bc8cb37badaca57d9112683836b24a0444c0a` | = bbport's `SUPPORTED_IMAGE` (game check passes) |
| `out\eboot.elf` | `941f887a562aae054fac35af8cc8f27cf075f3d4cc2e029fb5ae2a663aaa5ae7` | = bbhost's required eboot hash (the SELF's own digest of the original ELF) |

**Missing: `CUSA00900\sce_module\` is empty.** bbport links the game's own `libc.prx` and `libSceFios2.prx` from that folder (the full game ships seven `.prx` there), so its half of the test cannot start until the folder is dumped again — decrypted the same way as `eboot.bin` (each file starts with the bytes `4F 15 3D 1D`) and copied into `CUSA00900\sce_module\`. bbhost does not need it. The bbhost half can run now.

## 0. Preparation (once)

Folders (any drive; `D:\bb\` below):
- `D:\bb\game\CUSA00900\` — the dump folder above, copied as it is (plus `sce_module\` once dumped). Both tools read this folder; neither writes into it.
- `D:\bb\game\eboot.elf` — the ELF written by `scripts\prepare.py`. Check it on the 3090 box: `certutil -hashfile D:\bb\game\eboot.elf SHA256` must print `941f887a…5ae7`. (To regenerate: from this clone, `python scripts\prepare.py D:\bb\game\CUSA00900 --out D:\bb\out`; it writes `D:\bb\out\eboot.elf`, prints whether it is byte-exact, and then stops at the missing modules until `sce_module` exists — that is expected.)
- `D:\bb\bbhost\` — unzip `bbhost-win-v0.2.14.zip` from https://github.com/droogie/bbhost/releases/tag/v0.2.14. Verify first: download `SHA256SUMS` from the same page and compare `certutil -hashfile bbhost-win-v0.2.14.zip SHA256` with its line.
- `D:\bb\bbport\` — unzip the `windows-v1.4` zip from https://github.com/Supermedo/bloodborne_pc/releases/tag/windows-v1.4 (no published hashes; its launcher checks GitHub for updates on start — decline any update during the test). Only once `sce_module` is in place.
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
- bbport: 60 FPS mode, resolution 1440p, object motion vectors on (default), effects at defaults. bbport has no DLC support at all today (its AppContent answer lists zero add-ons), so The Old Hunters will not be recognised there — expected, not a defect of this run.
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

Zip `D:\bb\results\` (bbhost: the console log — start it as `bbhost.exe 2> bbhost.log` — plus `%LOCALAPPDATA%\bbhost\` logs; bbport: `out\last_run.log` + any `crash-*.log`; the filled table; screenshots) — paste the table in chat or upload the zip; I take it from there.
