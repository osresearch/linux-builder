#!/usr/bin/python3
# Build the Heads runtime (coreboot, initrd, kernel) with worldbuilder
# Currently produces x230 and qemu to demonstrate multiple build targets
#
import worldbuilder
import cpiofile
import os
import sys
import traceback
import glob

from worldbuilder.util import extend, zero_hash, sha256hex, exists, mkdir, writefile
from worldbuilder.submodule import global_mods
from worldbuilder import commands

from worldbuilder.crosscompile import gcc, crossgcc, cross_tools_nocc, cross_tools32_nocc, cross_tools, cross, target_arch, target_arch, musl, cross_gcc
from worldbuilder import crosscompile

from worldbuilder.linux import LinuxSrc, Linux
from worldbuilder.coreboot import CorebootSrc, Coreboot

# cache server can be passed in the environment
worldbuilder.submodule.cache_server = os.getenv("CACHE_SERVER", None)

for modname in sorted(glob.glob("modules/*")):
	try:
		with open(modname, "r") as f:
			exec(f.read())
	except Exception as e:
		print(modname + ": failed to parse", file=sys.stderr)
		print(traceback.format_exc(), file=sys.stderr)
		exit(1)

def Heads(
	board,
	kernel,
	kernel_version,
	coreboot_version,
	tools,
	extra_files = None,
	cmdline = None,
):
	initrdfile = worldbuilder.Initrd(board,
		filename = "initrd.cpio.xz",
		depends = tools,
		dirs = [ "/bin", "/lib" ],
		files = extra_files,
		symlinks = [
			[ "/bin/sh", "busybox" ],
			[ "/lib/ld-musl-x86_64.so.1", "libc.so" ],
			[ "/lib64", "lib" ],
		],
		devices = [
			[ "/dev/console", "c", 5, 1 ],
		],
	)

	linux_src = LinuxSrc(
		version = kernel_version,
		patches = [ "patches/linux-%(version)s/*" ],
	)

	linux = Linux(
		name = kernel,
		linux_src = linux_src,
		config = "config/linux-" + kernel + ".config",
		cmdline = cmdline or "console=ttyS0",
		compiler = worldbuilder.crosscompile,
	)

	coreboot_src = CorebootSrc(
		version = coreboot_version,
		patches = [ "patches/coreboot-%(version)s/*" ],
	)

	coreboot = Coreboot(
		name = board,
		src = coreboot_src,
		config = "config/coreboot-" + board + ".config",
		kernel = linux,
		initrd = initrdfile,
		compiler = worldbuilder.crosscompile,
	)
	
	return coreboot

qemu_firmware = Heads(
	board = "qemu",
	kernel = "virtio",
	kernel_version = "5.4.117",
	coreboot_version = "4.15",
	tools = [
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
)

x230_firmware = Heads(
	board = "x230",
	kernel = "x230",
	kernel_version = "4.14.62",
	coreboot_version = "4.13",
	tools = [
		"fbwhiptail",
		"dropbear",
		"cryptsetup2",
		"lvm2",
		"flashrom",
		"pciutils",
		"busybox",
		"kexec",
	],
)

builder = worldbuilder.Builder([ qemu_firmware, x230_firmware ])

if os.getenv("SINGLE_THREAD", None):
	builder.single_thread = True

if len(sys.argv) > 1:
	if sys.argv[1] == "cache":
		exit(builder.cache_create("build/cache"))
	elif sys.argv[1] == "check":
		exit(builder.check())
	builder.mods = sys.argv[1:]

if not builder.build_all():
	exit(-1)
