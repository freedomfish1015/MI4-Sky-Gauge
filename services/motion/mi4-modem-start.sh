#!/bin/sh
set -eu
for node in /sys/class/remoteproc/remoteproc*; do
    if [ "$(cat "$node/name")" = 'fc880000.remoteproc' ]; then
        [ "$(cat "$node/state")" = running ] || printf start > "$node/state"
        exit 0
    fi
done
exit 1
