#!/bin/sh
set -eu
modprobe qcom_sns_reg
modprobe qcom_smgr
modprobe qcom_smgr_accel
modprobe qcom_smgr_gyro
# Registry is now present before ADSP's first request. Retry a probe only if
# firmware enumeration raced service registration; never reset the audio DSP.
for attempt in $(seq 1 20); do
    if grep -l '^qcom-smgr-accel$' /sys/bus/iio/devices/iio:device*/name >/dev/null 2>&1; then
        exit 0
    fi
    for device in /sys/bus/qrtr/devices/*; do
        grep -qx 'MODALIAS=qrtr:100:1' "$device/uevent" || continue
        [ -L "$device/driver" ] || printf '%s' "${device##*/}" > /sys/bus/qrtr/drivers/qcom_smgr/bind || true
    done
    sleep 1
done
exit 1
