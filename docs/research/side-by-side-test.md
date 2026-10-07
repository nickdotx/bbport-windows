# Side-by-side test: bbhost v0.2.14 vs bbport (Supermedo windows-v1.4) — RTX 3090 box

Purpose: decide which project becomes our base. Same machine, same dump, same route, same settings. Budget ~2.5 hours. Written 2026-10-07.

## 0. Preparation (once)

Folders (any drive; `D:\bb\` below):
- `D:\bb\dump\` — the raw dump exactly as the console produced it (base + `CUSA03173-patch`). Never modified.
- `D:\bb\game\CUSA03173\` — a copy of the base with the 1.09 update copied over it (`eboot.bin`, `sce_sys\`, everything in the patch folder replaces the base's). Both tools read this folder; neither writes into it.
- `D:\bb\game\eboot.elf` — the 1.09 executable as a plain ELF, for bbhost. Get it one of two ways: (a) your dumper's "decrypt to ELF" output, if it offers one; (b) from the `bbport-windows` clone: `python scripts\prepare.py D:\bb\game\CUSA03173 --out D:\bb\out` (plain Python 3.12+, nothing to build) and take `D:\bb\out\eboot.elf`. bbhost checks the file's SHA-256 (`941f887a…5ae7`); if it refuses (b), use (a) — it prints the hash it saw, note it down.
- `D:\bb\bbhost\` — unzip `bbhost-win-v0.2.14.zip` from https://github.com/droogie/bbhost/releases/tag/v0.2.14. Verify first: download `SHA256SUMS` from the same page and compare `certutil -hashfile bbhost-win-v0.2.14.zip SHA256` with its line.
- `D:\bb\bbport\` — unzip the `windows-v1.4` zip from https://github.com/Supermedo/bloodborne_pc/releases/tag/windows-v1.4 (no published hashes; its launcher checks GitHub for updates on start — decline any update during the test).
- `D:\bb\results\bbhost\`, `D:\bb\results\bbport\` — logs, screenshots, your notes.

Machine:
- Latest NVIDIA Game Ready driver; Windows restarted after installing it.
- Steam Input, DS4Windows, reWASD, Discord/OBS/GeForce overlays, RivaTuner: all closed/disabled (overlays that hook Vulkan cause hangs in both tools).
- Run both tools from your normal user account, not as administrator.
- bbhost stays **offline**: do not link an account (setup window "Account", F10 > Account). If Windows Firewall asks, choose Cancel.
- DualSense on USB for the main runs. DualShock 4 and Bluetooth only in the controller checklist (§3).

Settings — identical on both, written down before starting:
- Output 2560×1440, borderless/fullscreen, frame cap 60, V-Sync off, **no upscaling** (bbport launcher: upscaler Off; bbhost F10: FSR 1 off).
- bbhost: in F10, switch every "PC enhancement" off (mirror editor, rebirth, extra invaders) so both run the game as shipped.
- bbport: 60 FPS mode, resolution 1440p, object motion vectors on (default), effects at defaults.
- 4K headroom check at the end (§2 step 9) is the only setting change.

## 1. The route — same order, same actions, ~45–60 minutes per tool

Start a stopwatch at launch; write the minute next to every observation.

1. **Launch.** Time to the title screen. Any warning or red line in the log.
2. **New game → character creation.** Is the name box visible and typeable? Does the character preview render (not black, not a white silhouette)? Finalize.
3. **Intro cinematic.** Let it play to the end. Audio in sync? Crash at the end (a known class)?
4. **Iosefka's Clinic.** Pick up the notes (item glow fades at normal speed?), open the door (animation speed), wake up in the Hunter's Dream: messengers animate normally, no replaying/popping?
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

Hard gates (both must pass to be eligible): boots; finishes the route with at most one crash; save/continue works; the controller checklist passes on DualSense USB.
Then: stability 40 %, visual correctness 30 %, performance 15 %, input + audio 15 %. If bbhost passes the gates it becomes the base unless bbport beats it on stability **and** visual correctness. A failed gate on one side decides it; failed gates on both sides mean we fix the one that got further.

## 5. Send back

Zip `D:\bb\results\` (bbhost `logs\`, bbport `out\last_run.log` + any `crash-*.log`, the filled table, screenshots) — paste the table in chat or upload the zip; I take it from there.
