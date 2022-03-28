#!/usr/bin/python3.9
# Build the Heads runtime (coreboot, initrd, kernel) with worldbuilder
#
import worldbuilder
import cpiofile
import os
import sys
from glob import glob
import traceback

from worldbuilder import extend, zero_hash, sha256hex, global_mods, exists, mkdir, writefile

from crosscompile import gcc, crossgcc, cross_tools_nocc, cross_tools32_nocc, cross_tools, cross, target_arch, musl

for modname in glob("modules/*"):
	try:
		with open(modname, "r") as f:
			exec(f.read())
	except Exception as e:
		print(modname + ": failed to parse", file=sys.stderr)
		print(traceback.format_exc(), file=sys.stderr)
		exit(1)


class Initrd(worldbuilder.Submodule):
	def __init__(self,
		name,
		version = "0.0.1",
		filename = "initrd.cpio.xz",
		depends = None,
		files = None,
		symlinks = None,
		devices = None,
	):
		super().__init__(
			'initrd-' + name,
			depends = depends,
			version = version,
		)
		self.filename = filename
		self.files = files or {}
		self.symlinks = symlinks or []
		self.devices = devices or []
		self._install_dir = ""

		# make sure that we depend on any files that we bring in
		for dir_name in self.files:
			for f in self.files[dir_name]:
				self.dep_files.append(f)

	def fetch(self, check=False):
		self.fetched = True
		return self
	def unpack(self, check=False):
		self.unpacked = True
		return self
	def patched(self, check=False):
		self.patched = True
		return self
	def configure(self, check=False):
		print("---- initrd configure ----")
		# update our output hash based on our dependencies and our files
		self.src_hash = sha256hex((self.filename + "-" + self.version).encode('utf-8'))
		files_hash = zero_hash
		for dir_name in self.files:
			dir_hash = sha256hex(dir_name.encode('utf-8'))
			for f in self.files[dir_name]:
					dir_hash = extend(dir_hash, sha256hex(f.encode('utf-8')))
			files_hash = extend(files_hash, dir_hash)

		symlink_hash = zero_hash
		for symlink in self.symlinks:
			symlink_hash = extend(symlink_hash, symlink)

		devices_hash = zero_hash
		for device in self.devices:
			s = [ device[0], device[1], str(device[2]), str(device[3]) ]
			devices_hash = extend(devices_hash, s)

		self.src_hash = extend(self.src_hash, [files_hash, symlink_hash, devices_hash])

		# update our output hash and all of our state variables
		self.update_hashes(zero_hash)
		self.configured = True

		return self

	def add_file(self, dir_name, encoded_name):
		fullname = self.format(encoded_name)
		filename = os.path.split(fullname)[1]
		self.cpio.add(os.path.join(dir_name, filename), fullname)

	def build(self, force=False, check=False):
		if not self.configure(check=check):
			return False

		build_canary = os.path.join(self.out_dir, ".build-" + self.name)
		if not self.build_required(check, force, build_canary):
			return self

		print("initrd! time to build --------------", self.out_dir)

		self.cpio = cpiofile.CPIO()

		for dir_name in self.files:
			self.cpio.mkdir(dir_name)
			for f in self.files[dir_name]:
				self.add_file(dir_name, f)
		for symlink in self.symlinks:
			self.cpio.symlink(*symlink)
		for devices in self.devices:
			self.cpio.mknod(*devices)

		mkdir(self.out_dir)

		is_compressed = self.filename.endswith('.xz')
		image = self.cpio.tobytes(compressed=is_compressed)
		writefile(os.path.join(self.out_dir, self.filename), image)

		writefile(build_canary, b'')
		self.built = True
		return self

initrd = Initrd("qemu",
	depends = [ "fbwhiptail", "dropbear", "cryptsetup", "lvm2", "flashrom", "pciutils", "busybox", "kexec" ],
	files = {
		"/bin": [
			"%(busybox.bin_dir)s/busybox",
			"%(dropbear.bin_dir)s/ssh",
			"%(kexec.bin_dir)s/kexec",
		],
		"/lib": [
			"%(musl.lib_dir)s/libc.so",
		],
		"/": [
			"init",
		],
	},
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
	deps = [ "coreboot-qemu" ]


build = worldbuilder.Builder(deps)

#build.check()
if not build.build_all():
	exit(-1)
