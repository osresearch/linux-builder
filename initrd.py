# an in-memory initrd builder
import worldbuilder
import cpiofile
import os

from worldbuilder import sha256hex, zero_hash, extend, mkdir, writefile

class Initrd(worldbuilder.Submodule):
	def __init__(self,
		name,
		version = "0.0.1",
		filename = "initrd.cpio",
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
		self.files = files or []
		self.symlinks = symlinks or []
		self.devices = devices or []
		self._install_dir = ""

		# make sure that we depend on any files that we bring in
		for files in self.files:
			for f in files[1:]:
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
		# update our output hash based on our dependencies and our files
		self.src_hash = sha256hex((self.filename + "-" + self.version).encode('utf-8'))
		files_hash = zero_hash
		for files in self.files:
			files_hash = extend(files_hash, files)

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

		self.cpio = cpiofile.CPIO()

		for files in self.files:
			dir_name = files[0]
			self.cpio.mkdir(dir_name)
			for f in files[1:]:
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

