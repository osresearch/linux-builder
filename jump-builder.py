#!/usr/bin/python3.9
# Build the jumphost
import worldbuilder
import initrd
import os
import sys
from glob import glob
import traceback

kernel = "virtio"
board = None

from worldbuilder import extend, zero_hash, sha256hex, global_mods, exists, mkdir, writefile, global_submodules

#from crosscompile import gcc, crossgcc, cross_tools_nocc, cross_tools32_nocc, cross_tools, cross, target_arch, musl
from localcompile import gcc, cross_tools_nocc, cross_tools, cross, target_arch

for modname in glob("modules/*"):
	try:
		with open(modname, "r") as f:
			exec(f.read())
	except Exception as e:
		print(modname + ": failed to parse", file=sys.stderr)
		print(traceback.format_exc(), file=sys.stderr)
		exit(1)

initrdfile = initrd.Initrd("jump",
	depends = [ "openssh" ],
	filename = "initrd.cpio",
	files = {
		"/bin": [
			"%(openssh.out_dir)s/sshd",
			#"%(dropbear.bin_dir)s/ssh",
			#"%(kexec.bin_dir)s/kexec",
		],
		"/lib": [
			#"%(musl.lib_dir)s/libc.so",
		],
		"/": [
			"init",
		],
	},
	symlinks = [
		[ "/lib/ld-musl-x86_64.so.1", "libc.so" ],
		[ "/lib64", "lib" ],
	],
	devices = [
		[ "/dev/console", "c", 5, 1 ],
	],
)

initrd_filename = "%(initrd-jump)s/initrd.cpio"

bzimage = global_submodules("linux-" + kernel)
bzimage.depends.append(initrdfile)
bzimage.dep_files.append(initrd_filename)
bzimage.config_append.append('CONFIG_INITRAMFS_SOURCE="' + initrd_filename + '"')

build = worldbuilder.Builder([bzimage])

#build.check()
if not build.build_all():
	exit(-1)
