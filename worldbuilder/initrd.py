# an in-memory initrd builder
import cpiofile
import os
import sys

from worldbuilder.util import *
from worldbuilder.submodule import Submodule

class Initrd(Submodule):
	def __init__(self,
		name,
		version = "0.0.1",
		filename = "initrd.cpio",
		depends = None,
		dirs = None,
		files = None,
		symlinks = None,
		devices = None,
		add_hashes = True,
	):
		super().__init__(
			'initrd-' + name,
			depends = depends,
			version = version,
		)
		self.filename = filename
		self.dirs = dirs or []
		self.files = files or []
		self.symlinks = symlinks or []
		self.devices = devices or []
		self.add_hashes = add_hashes

		# make sure that we depend on any files that we bring in
		for files in self.files:
			for f in files[1:]:
				self.dep_files.append(f)

		# todo: we should also depend on our output to force rebuilds

	def fetch(self, check=False):
		self.fetched = True
		return self
	def unpack(self, check=False):
		self.unpacked = True
		return self
	def patched(self, check=False):
		self.patched = True
		return self

	def compute_src_hash(self):
		self.src_hash = sha256hex((self.filename + "-" + self.version).encode('utf-8'))

	def compute_out_hash(self, config_file_hash = zero_hash):
		# update our output hash based on our dependencies and our files
		dirs_hash = extend(zero_hash, self.dirs)

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

		config_file_hash = extend(config_file_hash,[dirs_hash, files_hash, symlink_hash, devices_hash])

		# update our output hash and all of our state variables
		return super().compute_out_hash(config_file_hash)

	def add_file(self, dir_name, encoded_name, dep=None):
		if not dep:
			dep = self
		fullname = dep.format(encoded_name)

		if not exists(fullname):
			print("FAIL    " + dep.name + ": file not found " + relative(fullname), file=sys.stderr)
			return False

		image = readfile(fullname)
		mode = 0o700 # os.stat(fullname).st_mode  # we're all root here
		file_hash = sha256hex(image)

		# quick check for path names
		if image.find(b'/home/ubuntu') != -1:
			print(relative(fullname) + ": contains full path name", file=sys.stderr)

		self.cpio.add(dir_name, fullname, data=image, mode=mode)

		return file_hash

	# recursively add dependencies
	def add_deps(self, depends):
		fail = False

		for dep in depends:
			if dep.name in self.visited:
				continue

			self.visited[dep.name] = 1

			for filename in dep.bins:
				file_hash = self.add_file("/bin", filename, dep=dep)
				if not file_hash:
					fail = True
				self.hashes.append(relative(filename) + ": " + (file_hash or "MISSING"))
			for filename in dep.libs:
				file_hash = self.add_file("/lib", filename, dep=dep)
				if not file_hash:
					fail = True
				self.hashes.append(relative(filename) + ": " + (file_hash or "MISSING"))

			if not self.add_deps(dep.depends):
				fail = True

		return not fail


	def build(self, force=False, check=False):
		if not self.configure(check=check):
			return False

		build_canary = os.path.join(self.out_dir, ".build-" + self.name)
		if not self.build_required(force, build_canary):
			self.built = True
			return self
		if check:
			return False

		self.cpio = cpiofile.CPIO()

		# first thing make any directories
		for dirname in self.dirs:
			self.cpio.mkdir(dirname)

		self.hashes = []

		# add any binaries and libraries from dependencies
		self.visited = {}
		fail = not self.add_deps(self.depends)

		# add any additional ones they have requested
		for files in self.files:
			dir_name = files[0]
			self.cpio.mkdir(dir_name)
			for filename in files[1:]:
				file_hash = self.add_file(dir_name, filename)
				if not file_hash:
					fail = True
				else:
					self.hashes.append(relative(filename) + ": " + file_hash)

		for symlink in self.symlinks:
			self.cpio.symlink(*symlink)
		for devices in self.devices:
			self.cpio.mknod(*devices)

		hash_list = "".join([x + "\n" for x in self.hashes])
		#print(hash_list)
		hash_list = hash_list.encode('utf-8')

		if self.add_hashes:
			self.cpio.add("/hashes", "hashes", hash_list)

		if fail:
			return False


		mkdir(self.install_dir)
		initrd_file = os.path.join(self.install_dir, self.filename)

		info("BUILD   " + self.name + ": " + relative(initrd_file))

		is_compressed = self.filename.endswith('.xz')
		image = self.cpio.tobytes(compressed=is_compressed)
		writefile(initrd_file, image)
		writefile(initrd_file + ".hashes", hash_list)

		writefile(build_canary, b'')
		self.built = True

		info("INSTALL  " + self.name + ": " + sha256hex(image))

		return self

