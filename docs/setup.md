# Setup

From a blank Orange Pi 5 to a running flow. Each step ends with a check. Read
[hardware.md](hardware.md) first about the system disk: it saves days.

## 1. Operating system

1. Write Armbian for the Orange Pi 5, **vendor kernel**, Debian trixie, minimal, to a microSD
   card (a brand-name one) or an SSD. Check the image's checksum and signature first.
2. Start the board, log in as `root` with the default password `1234`, and finish Armbian's
   first-login wizard (new root password, a normal user).
3. Set up SSH keys from your PC and give the Pi a fixed address in the router.

Check: `uname -r` contains `vendor`, `ls /dev/dri` lists `renderD128` and `renderD129`, and
`sudo cat /sys/kernel/debug/rknpu/version` prints the NPU driver.

If the screen stays on the Orange Pi logo, or warm restarts hang, the loader in the SPI flash
does not match the system: see "Boot loader mix-up" in [hardware.md](hardware.md). Armbian
ships its own SPI build at `/usr/lib/linux-u-boot-vendor-orangepi5/u-boot-rockchip-spi.bin`,
written with `flashcp -v -p <file> /dev/mtd0`. Save the old content first
(`dd if=/dev/mtd0 of=spi-backup.bin`).

## 2. Docker and port 53

```bash
sudo bash tools/host/install-docker.sh <your user>
```

It installs Docker from Docker's apt repository after checking the key's fingerprint, and
writes `/etc/docker/daemon.json` (one copy per image, capped logs) before the first start.

AdGuard needs port 53, which `systemd-resolved` holds. Turn off its stub listener:

```bash
sudo mkdir -p /etc/systemd/resolved.conf.d
printf '[Resolve]\nDNS=1.1.1.1\nDNSStubListener=no\n' | sudo tee /etc/systemd/resolved.conf.d/adguard.conf
sudo ln -sf /run/systemd/resolve/resolv.conf /etc/resolv.conf
sudo systemctl restart systemd-resolved
```

Check: `docker run --rm hello-world` works, and `ss -lnup | grep :53` shows nothing.

## 3. The stack

Copy `stack/` to the Pi, for example to `~/orangepi-home`, then:

```bash
cd ~/orangepi-home
./setup.sh            # creates .env from .env.example and stops
nano .env             # camera address, camera account, timezone
./setup.sh            # creates the folders
docker compose up -d
```

The camera account is the one set in the Tapo app under the camera's Advanced Settings, not
your TP-Link login. Use letters and digits only: other characters break the RTSP address.

Check: `docker compose ps` shows five containers running. Frigate's log shows the `rknn`
detector, and its web UI on port 8971 shows the camera. Read Frigate's first admin password
from `docker compose logs frigate`.

## 4. AdGuard Home

Open `http://<pi>:3000` and run the wizard. Then, optionally, with the container stopped:

```bash
docker compose stop adguardhome
sudo python3 tools/host/adguard-tune.py adguard/conf/AdGuardHome.yaml
docker compose start adguardhome
```

That adds the OISD Big blocklist, filtered DNS-over-HTTPS upstreams (Quad9, Cloudflare
security), a bigger cache and a 7-day query log.

Check: `nslookup doubleclick.net <pi>` answers `0.0.0.0` and `nslookup example.com <pi>`
answers a real address. Only then let the router hand out the Pi as DNS, with a public
resolver as the second server.

## 5. Home Assistant

1. Open `http://<pi>:8123` and create the account.
2. Add the **MQTT** integration: broker `127.0.0.1`, port 1883, no login.
3. Add the **Tuya** integration with your Smart Life account. Rename the hose's valve entity to
   `valve.potty_valve` (or the switch to `switch.potty_valve`). In the timer's own settings, set
   the irrigation duration to the rinse length.
4. Install the Home Assistant app on the phone and sign in. Find its notify action under
   Developer tools > Actions (`notify.mobile_app_<phone>`).
5. Copy `homeassistant/secrets.example.yaml` into `homeassistant/secrets.yaml` and fill it in.
6. Restart Home Assistant. The Potty page appears in the sidebar.
7. On its Settings tab, press "Reset timers" once to set the defaults.

Check: the Settings tab shows the camera online, and Developer tools > States lists
`binary_sensor.potty_cam_dog_occupancy`.

## 6. Aim the photo

The check photo is the part of the frame set by `POTTY_CROP` in `.env`, as fractions of the
frame (`x1,y1,x2,y2`), resized to 640x640. Take the whole floor and leave out walls and the
camera's clock.

```bash
curl -X POST http://127.0.0.1:8099/preview     # on the Pi
```

Then look at `http://<pi>:8123/local/potty/preview.jpg`: the red box is the crop. After a
change, `docker compose up -d poop-checker`.

## 7. Test without water

Fake a visit over MQTT and watch the flow, with a fake person on the patio so the hose cannot
open:

```bash
docker exec mosquitto mosquitto_pub -t frigate/potty_cam/person -m 1
docker exec mosquitto mosquitto_pub -t frigate/potty_cam/dog -m 1
docker exec mosquitto mosquitto_pub -t frigate/potty_cam/dog -m 0
docker exec mosquitto mosquitto_pub -t frigate/potty_cam/motion -m OFF
```

About 20 s later the phone gets the question. Answer "Clean": the photo is labeled and the
rinse waits for the patio to clear. Stop it with `script.turn_off` on `script.potty_rinse`
under Developer tools > Actions, then send `person` `0`.

## 8. Changes from a PC

```bash
cp stack/deploy.env.example stack/deploy.env   # SSH target and folder on the Pi
stack/deploy.sh --dry-run
stack/deploy.sh
```

## 9. A model

Once there are 20 or more poop photos (the Settings tab counts them), copy
`poop-checker/data/dataset/` from the Pi to a PC and run:

```bash
pip install ultralytics onnx
python stack/training/train.py path/to/dataset
```

Check that the report's poop row has 0 in "rinsed", then copy `model.onnx` to
`poop-checker/data/` on the Pi.
