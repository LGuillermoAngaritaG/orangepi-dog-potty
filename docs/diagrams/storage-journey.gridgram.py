from gridgram import Diagram

# Columns are the system disks tried, in order (the hard disk was written
# from the RAM system, which then carried on until the SSD arrived). The top row is the disk and
# what went wrong; the bottom row is the boot fix each step needed.

d = Diagram(canvas="readme", cols=[1, 1, 1, 1, 1], rows=[80, 100], row_gap=40, col_gap=34,
            title="Finding a system disk that works")
for col, name in enumerate(["Nov 10", "Nov 11", "Nov 11", "Nov 11 to 20", "Nov 20"]):
    d.header(col, name)
stick = d.box(0, 0, "USB 2.0 stick", "73 KB/s writes; an OS update took 2 h 16 min", "risk", valign="top")
card = d.box(1, 0, "Unbranded microSD", "lost writes silently; root went read-only", "risk", valign="top")
ram = d.box(3, 0, "System in RAM", "soft-reboot into tmpfs; DNS kept running", "plain", valign="top")
hdd = d.box(2, 0, "Old USB hard disk", "4 MB/s, 789 pending sectors", "risk", valign="top")
ssd = d.box(4, 0, "USB 3 SSD, 128 GB", "334 MB/s reads; runs everything", "live", valign="top")
loader = d.box(1, 1, "Boot loader mix-up", "2017 factory SPL with 2026 U-Boot: fixed by writing Armbian's U-Boot to SPI", "live", valign="top")
usb = d.box(4, 1, "No USB-only boot", "SPI U-Boot won't start the SSD alone: the card keeps /boot", "live", valign="top")

d.arrow(stick, card)
d.arrow(card, hdd)
d.arrow(hdd, ram)
d.arrow(ram, ssd)
d.arrow(card, loader)
d.arrow(ssd, usb)
d.legend({"risk": "Failed", "plain": "Stopgap", "live": "In use today"})
d.save("storage-journey.drawio")
