#!/usr/bin/python3.9
# Build the Heads runtime (coreboot, initrd, kernel) with worldbuilder
#
import worldbuilder
import cpiofile
import os
import sys
from glob import glob
import traceback

from crosscompile import gcc, crossgcc, cross_tools_nocc, cross_tools, cross, target_arch, musl

for modname in glob("modules/*"):
	try:
		with open(modname, "r") as f:
			exec(f.read())
	except Exception as e:
		print(modname + ": failed to parse", file=sys.stderr)
		print(traceback.format_exc(), file=sys.stderr)
		exit(1)


if len(sys.argv) > 1:
	deps = sys.argv[1:]
else:
	deps = ["lvm2", "flashrom", "pciutils", "busybox", "kexec", "util-linux"]

build = worldbuilder.Builder(deps)

#build.check()
if not build.build_all():
	exit(-1)

# make a ramdisk
cpio = cpiofile.CPIO()

cpio.mkdir("/lib64")
cpio.mkdir("/lib")
#cpio.symlink("/lib/x86_64-linux-gnu", "../lib64")

cpio.mknod("/dev/console", "c", 5, 1)

cpio.mkdir("/bin")
#cpio.add("/bin", os.path.join(kexec.bin_dir, "kexec"))

#cpio.add("/bin", os.path.join(pciutils.bin_dir, "lspci"))
#cpio.add("/bin", os.path.join(flashrom.bin_dir, "flashrom"))

#cpio.add("/bin", os.path.join(busybox.bin_dir, "busybox"))
cpio.symlink("/bin/sh", "./busybox")

cpio.add("/lib", os.path.join(musl.lib_dir, "libc.so"))
cpio.symlink("/lib/ld-musl-x86_64.so.1", "libc.so")

image = cpio.tobytes()
with open("image.cpio", "wb") as f:
	f.write(image)
