#!/usr/bin/env bash

# Boot from the microSD card, run the system from a USB SSD.
#
# Armbian's SPI U-Boot 2026.04 on this Orange Pi 5 never started from a USB
# disk alone, but it boots fine from a card. Run this on the Pi while it is
# booted from a card that holds Armbian, with the SSD (also holding Armbian,
# for example a copy of the card's system) attached. It gives the SSD's
# filesystem a UUID of its own, then points the card's armbianEnv.txt at it, so
# the card only serves U-Boot, kernel and initrd and the system runs from the SSD.
#
#   card-boot-ssd-root.sh /dev/sda1
#
# Afterwards the card must stay in the slot. Hold the kernel packages
# (apt-mark hold) until the card's /boot is kept in step with the SSD's, or a
# kernel update lands on the SSD while the card keeps starting the old kernel.

export LC_ALL=C
set -u
stop() { echo "STOPPED: $*"; exit 1; }
ssd=${1:?usage: card-boot-ssd-root.sh <SSD partition, e.g. /dev/sda1>}
cardenv=/boot/armbianEnv.txt
old=$(blkid -s UUID -o value "$ssd")

[ "$(findmnt -no SOURCE /)" = /dev/mmcblk1p1 ] || stop "not running from the card"
[ -n "$old" ] || stop "$ssd has no filesystem UUID"
grep -q "^$ssd " /proc/mounts && stop "$ssd is mounted"

echo "== check the SSD filesystem"
e2fsck -fy "$ssd"; rc=$?; echo "e2fsck_rc=$rc"; [ $rc -le 1 ] || stop "e2fsck reported problems"

echo "== new UUID for the SSD"
new=$(cat /proc/sys/kernel/random/uuid)
tune2fs -U "$new" "$ssd" | tail -1
udevadm settle
[ "$(blkid -s UUID -o value "$ssd")" = "$new" ] || stop "UUID change did not take"
echo "SSD UUID now $new"

echo "== point the SSD's own fstab and armbianEnv at it"
mkdir -p /mnt/ssd && mount "$ssd" /mnt/ssd || stop "mount failed"
sed -i "s/$old/$new/" /mnt/ssd/etc/fstab /mnt/ssd/boot/armbianEnv.txt
grep -v '^#' /mnt/ssd/etc/fstab
grep rootdev /mnt/ssd/boot/armbianEnv.txt
sync; umount /mnt/ssd

echo "== point the card at the SSD"
[ -e $cardenv.before-ssd ] || cp -p $cardenv $cardenv.before-ssd
sed -i "s/^rootdev=.*/rootdev=UUID=$new/" $cardenv

# USB disks can show up late; wait for them instead of dropping to (initramfs).
grep -q rootdelay= $cardenv || sed -i 's/^extraargs=.*/& rootdelay=120 usbcore.autosuspend=-1/' $cardenv
sync
cat $cardenv
echo 3 > /proc/sys/vm/drop_caches
grep -q "rootdev=UUID=$new" $cardenv && echo "card env verified after cache drop" || stop "card env did not stick"
echo "DONE new_uuid=$new"
