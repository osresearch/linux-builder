# Base class for the builders, which can specialize individual functions
# this should be invoked via `make` so that there is a make job server
# available for parallel builds.
#
# downloaded artifacts are placed in build/ftp
# extracted files are in src/short-name/src-hash/
# build files are in out/short-name/build-hash/
#
# src-hash is sha256(sha256(file) || sha256(patches...))
# config-hash is sha256(src-hash || sha256(config...))
# build-hash is sha256(config-hash || sha256(deps...))
#
# the merkle tree ensures that the output in the build directory is
# reproducible based on its dependencies (assuming that each source
# has a reproducible build) and the configuration applied to the build.
#
# does this capture the actual build instructions? since the builder can
# change the parameters to `configure` or `make`, the `self.configure` array should
# be captured (before the substitutions)
# 
import os
import sys
import requests
import hashlib
import subprocess
import traceback
from tempfile import NamedTemporaryFile
from threading import Thread
from time import sleep
from graphlib import TopologicalSorter  # requires python3.9

verbose = 3
build_dir = 'build'
ftp_dir = os.path.join(build_dir, 'ftp')
src_dir = os.path.join(build_dir, 'src')
out_dir = os.path.join(build_dir, 'out')

zero_hash = '0' * 64

# some submodules use the same arguments
kbuild_make = [
	"make",
		"-C%(src_dir)s",
		"O=%(rout_dir)s",
		"KBUILD_HOST=builder",
		"KBUILD_USER=%(out_hash)s",
		"KBUILD_BUILD_TIMESTAMP=1970-01-01",
		"KBUILD_BUILD_VERSION=%(src_hash)s",
]

configure_cmd = "%(src_dir)s/configure"


def sha256hex(data):
	#print("hashing %d bytes" % (len(data)), data)
	return hashlib.sha256(data).hexdigest()
def extend(h, data):
	if h is None:
		h = zero_hash
	for datum in data:
		if type(datum) is str:
			datum = datum.encode('utf-8')
		h = sha256hex((h + sha256hex(datum)).encode('utf-8'))
	return h

def system(*s, cwd=None, log=None):
	if not cwd:
		cwd = '.'
	if verbose > 2:
		print(cwd, s)

	if log:
		logfile = open(log, "w+")
	else:
		logfile = None

	# do not close file descriptors, which will allow
	# communication from sub-make invocations to the make
	# that invoked us
	subprocess.run(s, cwd=cwd, check=True, close_fds=False, stdout=logfile, stderr=logfile)
	if logfile:
		logfile.close()

def die(*s):
	print(*s, file=sys.stderr)
	exit(1)
def info(s):
	if verbose > 0:
		print(s, file=sys.stderr)


def exists(*paths):
	try:
		os.stat(os.path.join(*paths))
		return True
	except Exception as e:
		return False

def mkdir(d):
	os.makedirs(d, exist_ok=True)

def writefile(name, data):
	with open(name, "wb") as f:
		f.write(data)
def readfile(name):
	with open(name, "rb") as f:
		return f.read()
def readfiles(names):
	d = []
	for name in names:
		d.append(readfile(name))
	return d

class Submodule:
	def __init__(self,
		name,
		url = None,
		#git = None,
		version = None,
		tarhash = None,
		patches = None,
		patch_dir = None,
		dirty = False,
		config_files = None,
		configure = None,
		make = None,
		depends = None,
		lib_dir = None,
		bin_dir = None,
		inc_dir = None,
	):
		#if not url and not git:
			#raise RuntimeError("url or git must be specified")

		self.name = name
		self.url = url
		#self.git = git
		self.version = version
		self.tarhash = tarhash
		self.patch_files = patches or []
		self.config_files = config_files or []
		self.configure_commands = configure or [ configure_cmd ]
		self.make_commands = make or [ "make" ]
		self.depends = depends or []
		self._bin_dir = bin_dir or "bin"
		self._lib_dir = lib_dir or "lib"
		self._inc_dir = inc_dir or "include"
		self._install_dir = "install"

		self.patch_level = 1
		self.strip_components = 1
		self.tar_options = []
		self.dirty = dirty

		self.src_hash = zero_hash
		self.out_hash = zero_hash
		self.tar_file = None
		self.major = None
		self.minor = None
		self.patchver = None
		self.src_dir = None
		self.out_dir = "/UNINITIALIZED"
		self.rout_dir = None
		self.install_dir = None
		self.bin_dir = None
		self.lib_dir = None
		self.inc_dir = None

		self.fetched = False
		self.unpacked = False
		self.patched = False
		self.configured = False
		self.built = False
		self.building = False


#		if patch_dir is not None:
#			self.patch_files = glob(

		self.update_dict()

	def state(self):
		if self.built:
			return "BUILT"
		if self.configured:
			return "CONFIGURED"
		if self.patched:
			return "PATCHED"
		if self.unpacked:
			return "UNPACKED"
		if self.fetched:
			return "FETCHED"
		return "NOSTATE"

	def format(self, cmd):
		try:
 			return cmd % self.dict
		except Exception as e:
			print(self.name + ":", self.dict)
			raise

	def update_dict(self):
		# semver the version string
		version = self.version.split('.') if self.version else ['0']
		self.major = version[0]
		if len(version) > 1:
			self.minor = version[1]
		if len(version) > 2:
			self.patchver = version[2]

		self.dict = {
			"version": self.version,
			"name": self.name,
			"major": self.major,
			"minor": self.minor,
			"patch": self.patchver,
			"tar_file": self.tar_file,
			"src_hash": self.src_hash[0:16],
			"out_hash": self.out_hash[0:16],
			"src_dir": self.src_dir,
			"out_dir": self.out_dir,
			"rout_dir": self.rout_dir,
			"install_dir": self.install_dir,
			"lib_dir":  self.lib_dir,
			"inc_dir":  self.inc_dir,
			"bin_dir":  self.bin_dir,
		}

		self.update_dep_dict(self.depends)

	# recursively add the dependency keys
	def update_dep_dict(self,deps):
		for dep in deps:
			for key in dep.dict:
				if key.count('.') != 0:
					continue
				dep_key = dep.name + "." + key
				if dep_key in self.dict:
					# this dependency has been processed
					#return
					pass
				self.dict[dep_key] = dep.dict[key]
			# add of of this dependency's dependencies
			self.update_dep_dict(dep.depends)

	def get_url(self):
		url = self.format(self.url)
		(base,f) = os.path.split(url)
		return (base+"/" + f, f)

	def fetch(self, force=False, check=False):
		self.update_dict()
		if not self.url:
			# this is a fake package with no source
			self.fetched = True
			return self

		(url,tar) = self.get_url()
		dest_tar = os.path.abspath(os.path.join(ftp_dir, tar))
		self.tar_file = dest_tar
		if exists(dest_tar) and not force:
			self.fetched = True
			return self

		if check:
			return self

		# make sure we have a place to put it
		mkdir(ftp_dir)

		r = requests.get(url)
		if r.status_code != requests.codes.ok:
			print(url + ": failed!", r.text, file=sys.stderr)
			return False
			
		info(url + ": fetching")
		data = r.content

		if self.tarhash is not None:
			data_hash = sha256hex(data)
			if data_hash != self.tarhash:
				print(tar + ": bad hash! " + data_hash, file=sys.stderr)
				writefile(dest_tar + ".bad", data)
				return False
			info(tar + ": good hash")

		writefile(dest_tar, data)
		self.fetched = True
		return self

	def unpack(self, check=False):
		if not self.url:
			# this is a fake package with no source
			self.unpacked = True
			return self

		if not self.fetch():
			return False

		self.patches = readfiles(self.patch_files)
		self.src_hash = extend(self.tarhash, self.patches)

		if self.dirty:
			# the src_subdir is based on the output hash,
			# not the src hash, since it writes to the
			# directory
			src_subdir = os.path.join(self.name + "-" + self.version, self.out_hash[0:16])
			self.src_dir = os.path.abspath(os.path.join(out_dir, src_subdir))
		else:
			src_subdir = os.path.join(self.name + "-" + self.version, self.src_hash[0:16])
			self.src_dir = os.path.abspath(os.path.join(src_dir, src_subdir))
		self.update_dict()

		unpack_canary = os.path.join(self.src_dir, '.unpacked')
		if exists(unpack_canary):
			self.unpacked = True
			return self

		if check:
			return self

		if self.dirty:
			info("CLEANUP " + self.name)
			system("rm", "-rf", self.src_dir)

		mkdir(self.src_dir)

		info("UNPACK " + self.name + ": " + self.tar_file + " -> " + self.src_dir)
		system("tar",
			"-xf", self.tar_file,
			"-C", self.src_dir,
			"--strip-components", "%d" % (self.strip_components),
			*self.tar_options,
		)

		writefile(unpack_canary, b'')
		self.unpacked = True
		return self

	def patch(self, check=False):
		if not self.url:
			# this is a fake package with no source
			self.patched = True
			return self

		if not self.unpack(check):
			return False
		patch_canary = os.path.join(self.src_dir, '.patched')
		if exists(patch_canary):
			self.patched = True
			return self

		if check:
			return self

		for (patch_file,patch) in zip(self.patch_files, self.patches):
			info(self.src_dir + ": patching " + patch_file)

			with NamedTemporaryFile() as tmp:
				tmp.write(patch)
				tmp.flush()

				system("patch",
					"--input", tmp.name,
					"--directory", self.src_dir,
					"-p%d" % (self.patch_level)
				)

		writefile(patch_canary, b'')
		self.patched = True
		return self

	def configure(self, check=False):
		if not self.patch(check):
			return False

		# the output hash depends on the source hash,
		# the configure command, the make command
		configs = readfiles(self.config_files)
		config_hash = extend(None, [x.encode('utf-8') for x in self.configure_commands])

		# ensure that there is a list of make commands
		if type(self.make_commands[0]) == str:
			self.make_commands = [ self.make_commands ]
		make_hash = zero_hash
		for commands in self.make_commands:
			cmd_hash = extend(None, commands)
			make_hash = extend(make_hash, cmd_hash)

		new_out_hash = extend(self.src_hash, [*configs, config_hash, make_hash])

		# and the output hash of the direct dependencies
		for dep in self.depends:
			new_out_hash = extend(new_out_hash, dep.out_hash)

#		print(self.name + ": ", new_out_hash, self.src_hash)
		if new_out_hash != self.out_hash and self.out_hash != zero_hash:
			print(self.name + ": HASH CHANGED ", new_out_hash, self.out_hash)
			exit(-1)
		self.out_hash = new_out_hash

		out_subdir = os.path.join(self.name + "-" + self.version, self.out_hash[0:16])
		self.out_dir = os.path.abspath(os.path.join(out_dir, out_subdir))
		self.rout_dir = os.path.join('..', '..', '..', 'out', out_subdir)
		self.install_dir = os.path.join(self.out_dir, self._install_dir)
		self.bin_dir = os.path.join(self.install_dir, self._bin_dir)
		self.lib_dir = os.path.join(self.install_dir, self._lib_dir)
		self.inc_dir = os.path.join(self.install_dir, self._inc_dir)

		self.update_dict()

		config_canary = os.path.join(self.out_dir, ".configured")
		if exists(config_canary):
			self.configured = True
			return self

		if check:
			# don't actually touch anything
			return self

		mkdir(self.out_dir)

		kconfig_file = os.path.join(self.out_dir, ".config")
		writefile(kconfig_file, b'\n'.join(configs))

		cmds = []
		for cmd in self.configure_commands:
			cmds.append(self.format(cmd))

		system(*cmds, cwd=self.out_dir, log=os.path.join(self.out_dir, "configure-log"))

		writefile(config_canary, b'')
		self.configured = True
		return self

	def build(self, force=False, check=False):
		if not self.configure(check=check):
			return False

		build_canary = os.path.join(self.out_dir, ".built-" + self.name)
		if exists(build_canary) and not force:
			self.built = True
			return self
		if check:
			# don't actually run the make
			return self

		print("BUILD " + self.name + ": " + self.out_dir)

		for commands in self.make_commands:
			cmds = []
			for cmd in commands:
				cmds.append(self.format(cmd))

			system(*cmds, cwd=self.out_dir, log=os.path.join(self.out_dir, "make-log"))

		writefile(build_canary, b'')
		self.built = True
		return self



class Builder:
	def __init__(self, mods):
		self.mods = mods
		self.failed = False
		self.reset()

	def reset(self):
		self.waiting = {}
		self.building = {}
		self.built = {}
		self.failed = {}

	def report(self):
		wait_list = ','.join(self.waiting)
		building_list = ','.join(self.building)
		built_list = ','.join(self.built)
		failed_list = ','.join(self.failed)
		print(
			"building=[" + building_list
			+ "] waiting=[" +  wait_list
			+ "] done=[" + built_list 
			+ "]"
		)
		if len(self.failed) > 0:
			print("failed=" + failed_list, file=sys.stderr)
			return False

		return True

	def _build_thread(self, mod):

		del self.waiting[mod.name]
		self.building[mod.name] = mod
		self.report()

		try:
			if mod.build():
				self.built[mod.name] = mod
			else:
				self.failed[mod.name] = mod
				print(mod.name + ": FAILED", file=sys.stderr)

		except Exception as e:
			print(mod.name + ": FAILED. Logs are in", mod.out_dir, file=sys.stderr)
			print(traceback.format_exc(), file=sys.stderr)
			self.failed[mod.name] = mod

		del self.building[mod.name]
		#self.report()

	def check(self):
		# walk all the dependencies to ensure consistency of inputs
		self.reset()

		# build the transitive closure of all modules that are
		# required, and sort them into a build order so that
		# dependencies are maintained
		ts = TopologicalSorter()

		for mod in self.mods:
			ts.add(mod, *mod.depends)
			for dep in mod.depends:
				self.mods.append(dep)

		ordered_mods = [*ts.static_order()]
		print([x.name for x in ordered_mods])

		for mod in ordered_mods:
			mod.build(check=True)
			if mod.built:
				self.built[mod.name] = mod
			else:
				self.waiting[mod.name] = mod

		#self.report()
		for modname, mod in self.waiting.items():
			print(mod.state() + " " + modname + ": " + mod.out_dir)
		for modname, mod in self.built.items():
			print(mod.state() + " " + modname + ": " + mod.out_dir)


	def build_all(self):
		if len(self.waiting) == 0:
			self.check()

		while True:
			if len(self.waiting) == 0 or len(self.failed) != 0:
				# no mods left, no builders? we're done!
				if len(self.building) == 0:
					return self.report()

				# no mods left, and builds are in process,
				# wait for completions. is there a better way?
				sleep(1)
				continue

			for name in list(self.waiting):
				mod = self.waiting[name]
				ready = True
				for dep in mod.depends:
					if not dep.name in self.built:
						ready = False

				if not ready:
					# oh well, try the next one
					continue

				# it is time to build this mod!
				mod.building = True
				Thread(target = self._build_thread, args=(mod,)).start()

			# processed the list of waiting ones sleep for a bit and
			# try again in a little while
			sleep(0.1)



if __name__ == "__main__":
	pass
