# Mi4 internal audio, audio1 bring-up (2026-10-18)

**New higher-priority issue: idle/screen-off black screen requiring manual reboot.
Read HANDOFF-MI4-AUDIO-20261018.md section 13. Read-only logs collected; GPU div0
and MDP pp timeout observed, userspace/key logs continue afterwards. Not fixed.
User has rebooted: runtime audio overlay/card currently absent.**

**Latest: rc7 max-normal-volume 20-second playback was audibly confirmed by
the user. Ordinary PipeWire output and boot persistence remain unfinished.
User requested documentation-only handoff. Read `HANDOFF-MI4-AUDIO-20261018.md`
first. The baseline/pending/no-sound sections below are chronological history.**

## Preserved baseline

- Running kernel: 6.15.11-mi4-test1; internal ALSA card absent.
- Exact current battery-fixed boot partition SHA256:
  `1071d6eb43c2dc87cd84b2048fedbd7ddd05db583e17a94da8bfe086231160f8`.
- `boot-now-ocvfix.img` is the recovery source, including lk2nd in the first 512 KiB.
- Reuse the live OCV-fixed DTB, not the stale kernel-source battery table.
- Original WLED and touch source changes copied unchanged into isolated build.

## New evidence

Read-only QRTR lookup on the Mi4 itself returned:

```
SLIM_QMI_SERVER version=1 instance=0 node=5 port=3
SLIM_QMI_SERVER_COUNT 1
```

This proves the DSP publishes the SLIMbus control service; it is not codec
enumeration or an audio-output test. Earlier APR queries also proved DSP state
READY and 11 advertised services.

## Implementation

Isolated kernel source `/root/mi4-audio-work/linux`, output
`/root/mi4-audio-work/build`, release `6.15.11-mi4-audio1`.

Port foundation from KorelisLabs/lumia-1520-mainline patches 0001, 0002, 0003,
0005. Downloaded through the user's requested mirror:
`[URL REDACTED]
Archive retained locally. The repository's scripts were inspected, not run as
an installer; its complete Lumia DT and battery settings are NOT used.

Mi4 adaptations:

- APR services 3/4/7/8; Q6 FE/BE graph described, card initially disabled.
- SLIMbus/BAM MMIO, reset GPIO 63, IRQ GPIO 72 and seven supplies mapped from
  cancro's original MIUI DT. Message DMA pipes 3/4 are distinct from its audio
  data-pipe ownership bitmap 0x60000000.
- Separate control and interface SLIM functions, elemental addresses matching
  the original Taiko entries. Physical identity must still be read on Mi4.
- NGD late-SSR recovery and regmap context fixes; additionally initialise NGD
  base BEFORE platform_device_add, since probe may schedule work immediately.
- Codec cache disabled for initial Mi4 measurements: do not trust another
  phone's fuse-loaded register defaults as this phone's measured state.
- Add Mi4 compatible to the Q6 machine driver; retain origin/license notices.
- Optional runtime DT overlay support allows later audio graph changes without
  repeatedly rewriting boot. Helper has no autoload or persistent configuration.

The initial transport stage did not enable speaker boost or PA. A subsequent,
explicit speaker-output test is recorded below. No micbias setting, charging
change or rootfs flash was made.

## Validation and install gates

- Full zImage/modules build required; no use of mismatched prebuilt modules.
- `pack_audio_boot.py` checks the exact baseline hash and every existing DT
  property, retaining the old ramdisk. Only audio nodes and an L1 reference are
  added; all old battery, display, touch and other properties must match.
- `install_audio_kernel.py --check` is read-only on boot.
- `--write` requires matching modules, verifies the complete current boot,
  saves an exclusive full-partition backup, writes only AFTER +512 KiB and
  checks complete partition readback. An error attempts exact rollback.
- No automated reboot inside the updater. Old module directory is retained.
- `--rollback` refuses unless both the saved original and current audio-test
  partition hashes match. It never overwrites lk2nd.

## Acceptance still required

1. New kernel boot, normal display/touch/USB and battery-fix regression check.
2. Real SLIM enumeration and Taiko identity/core initialisation.
3. Real Q6/ALSA playback-control and sample-transport checks.
4. Board-specific clock/output route, conservative gain, actual audible sound.

A PCM node, DSP reply or a completed build alone must NOT be reported as a
repaired internal sound card.

## Installed and tested on Mi4

Boot update passed full-partition readback. Current partition SHA256:
`5715032761b50157ea495d5dfb3d71b2b6de300f00ce7681f48f154dd9f67653`.
Phone is RUNNING `6.15.11-mi4-audio1`; serial COM10 remains functional.
lk2nd is unchanged. Full original phone backup:
`/home/umeko/desktop-offline/boot-before-audio1-full.img`, SHA256 matches the
OCV-fixed baseline above. Battery reads 99 after the test; this is preservation
of the existing fix, not a new capacity-accuracy claim.

Transport/codec proof, from `audio1-dsp-codec-probe.log`:

- NGD receives master capability, registers controller and discovers QMI v1/0.
- PGD hardware identity major 0x0102, minor 0x0001, logical address 0xcb.
- IFD logical address 0xca, online after real enumeration.
- Seven exact Mi4 supplies enabled, reset GPIO63 released.
- Core initialises 0 -> 94 -> 95 nonzero registers; canary 0x320=e4.
- 29 IRQ sources masked, level-high TLMM72 parent idle, no IRQ storm.

### Q6 card registration correction

The first enabled overlay reversed child/link order, putting the backend
before the frontend. In 6.15 that probes q6routing before q6asm creates its
MM_DL/MM_UL widgets, so registration fails -ENODEV with missing DAPM routes.
The machine driver now stably orders FE links before BE links. It does NOT
ignore route errors. Module version `mi4-q6-link-order1` is installed.

The real card now registers as **Mi4-Taiko**, PCM `MultiMedia1 Playback`.
Two-second mono 48 kHz S16_LE silence test exits 0. Codec stream prepare,
enable, disable and unprepare all return 0; runtime is freed afterwards.
See `audio1-pcm-silence-test.log`.

### Minimal speaker route, version mi4-spk-rc3

Primary cancro references downloaded via gh-proxy.org and retained in
`downstream-reference/`: kernel cm-14.1 `sound/soc/codecs/wcd9320.c`, device
cm-14.1 `audio/mixer_paths.xml`. Hammerhead cm-11.0 source also retained.
The cancro mixer confirms **SLIM RX1 -> RX7 MIX1 -> speaker**. Its generic
profile gain values are NOT blindly copied: the actual codec driver's 2.0
speaker gain range is 0..8, inverted. We use minimum legal gain 8 << 3 plus
manual-gain bit 2, register 0x1e0=0x44, with digital gain -12 dB. COMP0 stays
off for deterministic initial output.

Added DAPM route with a virtual speaker gate starting OFF. Only an explicit
playback plus gate enables PM8941 S4 speaker supply, 9.6 MHz MCLK, RX7
interpolator/bias and finally PA. Taiko 1.0 silicon and simultaneous research
headphone/earpiece bias users are refused. OCP/clip defaults match cancro 2.0.
Stop closes PA first, then RX7/bias/clock and releases its boost vote.

Clock description in `mi4-audio-output-prepare.dtso` matches Mi4 stock DT:
PM8941 GPIO15, DIV_CTL1=2 (19.2 MHz / 2), existing RPM DIV_A_CLK1 id47.
No duplicate CCF provider is registered. Runtime OF creates this node under
platform_bus rather than its SPMI parent, so the divider helper explicitly
resolves the existing PMIC on the SPMI bus for its regmap. It never creates
or substitutes a new regmap.

Also fixed IFD rebind state: an already-UP SLIM device gets no new UP callback
from the core. The new driver instance now reconciles that existing UP state,
instead of leaving `online=0` after a module replacement.

### Speaker test and cleanup

`speaker3-test-tone.log` records three ramped 660 Hz quiet tones at 48 kHz:
aplay exits normally, PA ON precedes stream START, stream STOP/teardown
complete, PA/bias/boost/MCLK go OFF. This is a successful SOFTWARE sequence,
**not yet evidence that a human heard sound**. User hearing confirmation and
display/touch/backlight regression confirmation were requested and are pending.

`speaker3-idle-cleanup-verified.log` proves afterwards:

- SPKR_DRV_EN=0x6f (PA bit7 clear), RX bias=0, fixed gain=0x44.
- Stream up=0, allocated=0, prepare/enable/disable/unprepare rc=0.
- Divider applied=0, MCLK hardware enabled=0; original divider factor restored.
- Speaker-supply enable count=0, shared S4 use count=0.
- WirePlumber, temporarily stopped for direct ALSA tests, is ACTIVE again.

No speaker autostart has been installed. The output overlay is runtime-only;
the boot DT still has the card disabled. **Do not assume audio survives a
reboot yet.** Await listening confirmation before enabling a daily-use profile,
volume controls or persistent boot setup. Current gate and routing mixer are
OFF, deliberately.

Additional observation: GPU `retire_submits` reports division-by-zero traces
on this build. No audio-path kernel panic occurred. This graphics issue has not
been attributed to the audio changes or proven absent in the previous kernel;
user UI-regression feedback is pending. Do not claim all regression checks pass.

Reproduction artifact: `mi4-audio1-speaker3-modules.tar.gz`, separate from the
original pre-speaker module package. Current source changes exported to
`mi4-audio1-kernel.patch`; original dirty WLED/touch changes remain untouched.

### Confirmed user feedback and subsequent revisions

The user confirmed the audio kernel's display, touch and both backlight halves
are normal. They **did not hear** the rc3 test, and also **did not hear** rc4.
Audio is NOT fixed. The earlier pending-listening statements above are historical.

rc4 changed SPKR_DRV_GAIN from 0x44 to 0x3c: downstream inverted control's first
non-mute TLV step, with the same -12 dB digital gain and quiet waveform. This
was a hypothesis, not a proven explanation of silence. No further gain increase
was made. Actual gain semantics must not be inferred from the TLV mute label alone.

rc5 added a read-only `mi4_speaker_state` snapshot: bypassed PGD register reads
and uncached IFD status/source reads, under the respective locks. It neither
clears interrupts nor changes route settings. `speaker5-live-status.log` shows:

- During playback: IFD port 16 config 0x040=05, channel mask 0x180=01,
  RX status 0x034=00 and source 0x060=00. No underflow/overflow was observed in
  that sample. Supply hardware enabled=1; speaker PA enable 0x1df=ef,
  OCP status 0x1eb=00, PA status 0x1ec=70 (raw, not a claim of audible output).
- After disconnect: RX status=01, source=04. This is the stock PORT_CLOSED
  event, not evidence of playback underflow. No unsolicited interrupt clearing.
- The old shortcut left RC_OSC_FREQ=0xc6 while selecting external MCLK.

### rc6: complete RCO/MCLK clock handoff

Current loaded/installed codec version: `mi4-spk-rc6-clock-handoff`.
Artifact: `wcd9320-mi4-spk-rc6.ko`, SHA256
`6757586f00c5492a765d850dbfafd664f0f273654dc904f08864963c52a8939d`.
It supersedes the codec inside the earlier speaker3 full-module tarball.

Reused the existing checked sequence tables corresponding to the actual cancro
`wcd9xxx-resmgr.c`: clock block OFF, deselect RCO, disable RCO configuration
mode, select external/VBG, settle buffer, clear reset, clock ON. The PA remains
off throughout the transition. On stop/error, PA/interpolator/bias are disabled
first, then the RCO is restarted and settled **before** the external clock vote
is released. Restore errors are logged; teardown still releases owned supplies.

`speaker6-clock-test.log` verifies every checked transition and readback:
RC_OSC_FREQ=c6 -> 46 during playback, BIAS_OSC_BG_CTL=16, CLK_BUFF_EN1=05,
CLK_BUFF_EN2=04. After stop: oscillator=c6, bias=17, mux=09, PA=6f, RX7/bias=0,
no supply/clock owned. IFD live status/source remain 00; shutdown gives source04.
CDC_CLK_POWER_CTL still reads 00; do not claim that its write is observable.

`speaker6-cleanup.log`: stream allocated=0/up=0, all stream operation rc=0,
divider applied=0/hardware enabled=0 with original factor0 restored,
WirePlumber ACTIVE again. Boot partition and battery settings were not changed.
Listening confirmation for this changed clock sequence was requested; pending.
No production audio auto-start or persistent speaker route has been enabled.

### rc6 listening result; user-requested 100% / sustained test pending USB

The user confirmed **rc6 is still silent**, then explicitly requested maximum
volume and a sustained beep. Prepared rc7 with an opt-in, read-only-at-runtime
module parameter `mi4_speaker_test_max=1`: downstream analog control logical8
(field0, manual bit2: 0x1e0=04), normal 0 dB digital (0x2e7=00), not the codec's
additional +40 dB digital boost. OCP/clip settings remain unchanged. PA-off
cleanup restores gain3c/digitalf4. Default module mode remains low.

`make_test_tone.py --long` generates `mi4-long-test.wav`: 20 seconds of 660 Hz,
48 kHz mono S16, peak3000 (-20.8 dBFS), with 10 ms start/end ramps.
`test_mi4_speaker.sh mi4-long-test.wav` has a 25-second timeout and the existing
EXIT cleanup for PA/route/divider. `replace_mi4_codec.sh` now accepts optional
`max` (only for rc7+) or default `low`; both reject other mode strings.

rc7 compiled successfully, but **was NOT transferred, installed or played**:
COM10 disappeared before any file transfer. Windows serial-port enumeration
and relevant present USB/PnP device checks both returned no phone devices.
Current phone module last confirmed rc6, route/PA OFF. Ask user to reconnect
USB with Linux running. After the one sustained maximum-normal-volume test,
reload rc7 in default low mode, confirm PA/supply/clock OFF and WirePlumber
restored; do not leave the max-test module parameter active.

### LATEST: rc7 actual audible output confirmed; handoff requested

USB reconnected on COM10. Phone had rebooted: reauthenticated, restored
/tmp/usb-receive.py, explicitly reloaded output-prepare runtime overlay and
recovered Mi4-Taiko card without flashing. Transferred SHA-verified rc7/scripts/WAV.

`speaker7-max-20s-test.log` records the 20-second 660Hz test, max-normal analog
gain1e0=04, digital2e7=00, PA1df=ef, supply/clock owned during playback.
**User explicitly confirmed hearing sustained beeping.** This is the first
actual listening success; previous no-sound/pending sections are historical.

EXIT cleanup restored codec rc7 default mode: max parameter N, PA6f, RX7/bias0,
supply/clock owned0, hardware supply0, divider restored factor0/applied0/enabled0,
stream unallocated/down, WirePlumber active. No ongoing playback or beep.

Do not overstate scope: ordinary PipeWire apps still use auto_null; no actual
speaker sink, UCM profile or persistent boot setup has been installed. The user
asked to stop further changes and document everything for another model.
**Read HANDOFF-MI4-AUDIO-20261018.md for complete current state and next steps.**
