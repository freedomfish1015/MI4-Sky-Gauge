#!/bin/bash
# Mi4 internal speaker bring-up at boot.
# Full rationale: HANDOFF-MI4-AUDIO-20261018.md section 14.
set -u

OVERLAY=/home/umeko/desktop-offline/mi4_audio_overlay.ko
DTBO=mi4-audio-output-prepare.dtbo

# 1. DT overlay: the sound node is disabled in the boot DT itself.
if [ ! -e /sys/module/mi4_audio_overlay ]; then
	insmod "$OVERLAY" firmware="$DTBO" || exit 1
fi

# 2. Wait (max 90s) for RPM vreg-boost to have a consumer. Probing the codec
#    before that fails with -ENODEV and the codec caches the error forever
#    (supply_hw_enabled=-19): card and routes look fine but playback is silent.
wait_boost() {
	for i in $(seq 1 90); do
		for r in /sys/class/regulator/*; do
			[ "$(cat "$r/name" 2>/dev/null)" = "vreg-boost" ] || continue
			u=$(cat "$r/num_users" 2>/dev/null || echo 0)
			[ "$u" -gt 0 ] 2>/dev/null && return 0
		done
		sleep 1
	done
	return 1
}
wait_boost || true

# 3. Clean (re)load so `systemctl restart mi4-audio-init` can repair a bad probe.
modprobe -r snd_soc_lumia1520_q6 2>/dev/null || true
modprobe -r wcd9320 2>/dev/null || true
sleep 1
modprobe wcd9320 mi4_speaker_test_max=1 || exit 1
modprobe snd_soc_lumia1520_q6 || exit 1

# 4. Wait for the card.
for i in $(seq 1 40); do
	[ -e /sys/class/sound/card0 ] && break
	sleep 0.5
done

# 5. Routes must be on: the DAPM gate is OFF by default at probe time.
amixer -c 0 cset name='SLIMBUS_0_RX Audio Mixer MultiMedia1' 1 >/dev/null 2>&1
amixer -c 0 cset name='Mi4 Speaker Gate Switch' 1 >/dev/null 2>&1

# 6. MCLK divider (the MCLK enable vote is taken by the playback path).
for d in /sys/bus/platform/devices/*mi4-mclk-divider*; do
	[ -e "$d/mclk_div_test" ] || continue
	if ! grep -q 'applied=1' "$d/mclk_div_state"; then
		echo on > "$d/mclk_div_test"
	fi
done

exit 0
