#!/usr/bin/python3
# Build the Heads runtime (coreboot, initrd, kernel) with worldbuilder
#
import worldbuilder
import cpiofile
import os
import sys
import traceback
import glob
from shlex import quote

from worldbuilder.util import extend, zero_hash, sha256hex, exists, mkdir, writefile
from worldbuilder.submodule import global_mods
from worldbuilder import commands

from worldbuilder.crosscompile import gcc, crossgcc, cross_tools_nocc, cross_tools32_nocc, cross_tools, cross, target_arch, musl, cross_gcc

board = 'qemu'
kernel = 'virtio'

for modname in sorted(glob.glob("modules/*")):
	try:
		with open(modname, "r") as f:
			exec(f.read())
	except Exception as e:
		print(modname + ": failed to parse", file=sys.stderr)
		print(traceback.format_exc(), file=sys.stderr)
		exit(1)

initrdfile = worldbuilder.Initrd(board,
	filename = "initrd.cpio.xz",
	depends = [
		"fbwhiptail",
		"dropbear",
		"cryptsetup2",
		"lvm2",
		"flashrom",
		"pciutils",
		"busybox",
		"kexec",
		"openssh",
	],
	dirs = [ "/bin", "/lib" ],
	files = [
	],
	symlinks = [
		[ "/bin/sh", "busybox" ],
		[ "/lib/ld-musl-x86_64.so.1", "libc.so" ],
		[ "/lib64", "lib" ],
	],
	devices = [
		[ "/dev/console", "c", 5, 1 ],
	],
)

#	coreboot = global_mods["coreboot-qemu"]
#	coreboot.depends.append(initrd)
#	initrd.configure(check=True)
#	coreboot.configure(check=True)
	
if len(sys.argv) > 1:
	deps = sys.argv[1:]
else:
	deps = [ "coreboot-" + board ]


build = worldbuilder.Builder(deps)

#build.check()
if not build.build_all():
	exit(-1)
