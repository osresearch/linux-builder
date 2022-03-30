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
import time
from tempfile import NamedTemporaryFile
from threading import Thread
from time import sleep, asctime
from graphlib import TopologicalSorter  # requires python3.9

verbose = 1
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

# Try to remove any absolute paths and things that make reproducibility hard
prefix_map = "-gno-record-gcc-switches" \
	+ " -ffile-prefix-map=%(src_dir)s=%(name)s-%(version)s" \
	+ " -ffile-prefix-map=%(out_dir)s=/build" \
	+ " -ffile-prefix-map=%(install_dir)s=/" \


# global list of modules; names must be unique
global_mods = {}

def now():
	return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())

def sha256hex(data):
	#print("hashing %d bytes" % (len(data)), data)
	if type(data) is str:
		data = data.encode('utf-8')
	return hashlib.sha256(data).hexdigest()
def extend(h, data):
	if h is None:
		h = zero_hash
	for datum in data:
		h = sha256hex(h + sha256hex(datum))
	return h

def system(*s, cwd=None, log=None):
	if not cwd:
		cwd = '.'
	if verbose > 2:
		print(cwd, s)

	if log:
		logfile = open(log, "a+")
		print("----- " + now() + " -----", file=logfile)
		print("cd " + os.path.abspath(cwd), file=logfile)
		print(*s, file=logfile)
		logfile.flush()
	else:
		logfile = None

	# do not close file descriptors, which will allow
	# communication from sub-make invocations to the make
	# that invoked us
	subprocess.run(s, cwd=cwd, check=True, close_fds=False, stdout=logfile, stderr=logfile)
	if logfile:
		logfile.close()

def die(*s):
	print(now(), *s, file=sys.stderr)
	exit(1)
def info(*s):
	if verbose > 0:
		print(now(), *s)


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
		config_append = None,
		configure = None,
		make = None,
		install = None,
		depends = None,
		dep_files = None,
		install_dir = None,
		lib_dir = None,
		bin_dir = None,
		inc_dir = None,
		patch_level = 1,
		strip_components = 1,
	):
		#if not url and not git:
			#raise RuntimeError("url or git must be specified")
		if name in global_mods:
			die(name + ": already exists in the global module list?")
		global_mods[name] = self

		self.name = name
		self.url = url
		#self.git = git
		self.version = "NOVERSION" if not version else version
		self.tarhash = tarhash
		self.patch_files = patches or []
		self.config_files = config_files or []
		self.config_append = config_append or []

		self.configure_commands = configure or [ "true" ]
		self.make_commands = make or [ "true" ]
		self.install_commands = install or [ "true" ]

		self.depends = depends or []
		self.dep_files = dep_files or []
		self._bin_dir = "bin" if bin_dir is None else bin_dir
		self._lib_dir = "lib" if lib_dir is None else lib_dir
		self._inc_dir = "include" if inc_dir is None else inc_dir
		self._install_dir = "install" if install_dir is None else install_dir

		self.patch_level = patch_level
		self.strip_components = strip_components
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
		self.installed = False
		self.building = False


#		if patch_dir is not None:
#			self.patch_files = glob(

		self.update_dict()

	def state(self):
		if self.installed:
			return "INSTALLED"
		if self.built:
			return "BUILT    "
		if self.configured:
			return "CONFIGED "
		if self.patched:
			return "PATCHED  "
		if self.unpacked:
			return "UNPACKED "
		if self.fetched:
			return "FETCHED  "
		return "NOSTATE??"

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
			if type(dep) is str:
				# defer this one until later
				continue
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
			
		info("FETCH   " + self.name + ": fetching")
		data = r.content

		if self.tarhash is not None:
			data_hash = sha256hex(data)
			if data_hash != self.tarhash:
				print(tar + ": bad hash! " + data_hash, file=sys.stderr)
				writefile(dest_tar + ".bad", data)
				return False
			#info(tar + ": good hash")

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

		info("UNPACK  " + self.name + ": " + self.tar_file + " -> " + self.src_dir)
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

		mkdir(self.out_dir)

		for (patch_file,patch) in zip(self.patch_files, self.patches):
			info("PATCH   " + self.src_dir + ": " + patch_file)

			with NamedTemporaryFile() as tmp:
				tmp.write(patch)
				tmp.flush()

				system("patch",
					"--input", tmp.name,
					"--directory", self.src_dir,
					"-p%d" % (self.patch_level),
					log=os.path.join(self.out_dir, "patch-log")
				)

		writefile(patch_canary, b'')
		self.patched = True
		return self

	def update_hashes(self, config_file_hash):
		# ensure that there is a list of make, and install commands
		if type(self.configure_commands[0]) == str:
			self.configure_commands = [ self.configure_commands ]
		if type(self.make_commands[0]) == str:
			self.make_commands = [ self.make_commands ]
		if type(self.install_commands[0]) == str:
			self.install_commands = [ self.install_commands ]

		config_hash = zero_hash
		for commands in self.configure_commands:
			cmd_hash = extend(None, commands)
			config_hash = extend(config_hash, cmd_hash)

		config_hash = extend(config_hash, [
			self._install_dir,
			self._inc_dir,
			self._lib_dir,
			self._bin_dir,
			"dirty-tree" if self.dirty else "clean-tree",
			*self.dep_files,
		])

		make_hash = zero_hash
		for commands in self.make_commands:
			cmd_hash = extend(None, commands)
			make_hash = extend(make_hash, cmd_hash)
		install_hash = zero_hash
		for commands in self.install_commands:
			cmd_hash = extend(None, commands)
			install_hash = extend(install_hash, cmd_hash)

		new_out_hash = extend(self.src_hash, [config_file_hash, config_hash, make_hash, install_hash])

		# and the output hash of the direct dependencies
		for dep in self.depends:
			new_out_hash = extend(new_out_hash, dep.out_hash)

#		print(self.name + ": ", new_out_hash, self.src_hash)
		if new_out_hash != self.out_hash and self.out_hash != zero_hash:
			print(self.name + ": HASH CHANGED ", new_out_hash, self.out_hash)
			exit(-1)
		self.out_hash = new_out_hash

		# todo: include more configuration in the out_hash (dirty, inc_dir, etc)

		out_subdir = os.path.join(self.name + "-" + self.version, self.out_hash[0:16])
		self.out_dir = os.path.abspath(os.path.join(out_dir, out_subdir))
		self.rout_dir = os.path.join('..', '..', '..', 'out', out_subdir)
		self.install_dir = os.path.join(self.out_dir, self._install_dir)
		self.bin_dir = os.path.join(self.install_dir, self._bin_dir)
		self.lib_dir = os.path.join(self.install_dir, self._lib_dir)
		self.inc_dir = os.path.join(self.install_dir, self._inc_dir)

		self.update_dict()

	def run_commands(self, logfile_name, command_list):
		for commands in command_list:
			cmds = []
			for cmd in commands:
				cmds.append(self.format(cmd))

			system(*cmds,
				cwd=self.out_dir,
				log=os.path.join(self.out_dir, logfile_name),
			)

	def configure(self, check=False):
		if not self.patch(check):
			return False

		# the output hash depends on the source hash,
		# the source config files, any updates to those files,
		# the commands executed to configure the programs,
		# and any dependencies
		# todo: should the hash be on the unexpanded append lines?
		configs = readfiles(self.config_files)
		config_file_hash = extend(zero_hash, configs)

		self.update_hashes(config_file_hash)

		config_canary = os.path.join(self.out_dir, ".configured")
		if exists(config_canary):
			self.configured = True
			return self

		if check:
			# don't actually touch anything
			return self

		mkdir(self.out_dir)

		kconfig_file = os.path.join(self.out_dir, ".config")

		# expand the configuration appended lines now
		for append in self.config_append:
			configs.append(self.format(append).encode('utf-8'))

		writefile(kconfig_file, b'\n'.join(configs))

		info("CONFIG  " + self.name)
		self.run_commands("configure-log", self.configure_commands)

		writefile(config_canary, b'')
		self.configured = True
		return self


	def build_required(self, check, force, build_canary):
		# update our check time for GC of build trees
		mkdir(self.out_dir)
		writefile(os.path.join(self.out_dir, '.build-checked'), b'')

		# no canary? definitely have to rebuild
		self.built = False
		if not exists(build_canary) or force:
			return not check

		# do a scan of the dependent files for timestamps relative to canary
		canary_build_time = os.stat(build_canary).st_mtime
		for filename in self.dep_files:
			real_filename = self.format(filename)
			if not exists(real_filename):
				print(self.name + ": no " + real_filename)
				return not check
			if os.stat(real_filename).st_mtime > canary_build_time:
				print(self.name + ": newer " + real_filename)
				return not check

		# and check all of our dependencies
		for dep in self.depends:
			if not dep.installed:
				return not check

		# we're probably ok; mark our status as built
		self.built = True
		return False

	def build(self, force=False, check=False):
		if not self.configure(check=check):
			return False

		build_canary = os.path.join(self.out_dir, ".built-" + self.name)
		if not self.build_required(check, force, build_canary):
			return self

		info("BUILD   " + self.name + ": " + self.out_dir)
		self.run_commands("make-log", self.make_commands)

		writefile(build_canary, b'')
		self.built = True

		return self

	def install(self, force=False, check=False):
		if not self.build(force=force, check=check):
			return False

		install_canary = os.path.join(self.out_dir, ".install-" + self.name)
		if exists(install_canary) and not force:
			self.installed = True
			return self
		if check:
			return self

		info("INSTALL " + self.name + ": " + self.install_dir)
		self.run_commands("install-log", self.install_commands)

		writefile(install_canary, b'')
		self.installed = True

		return self


class Builder:
	def __init__(self, mods):
		self.mods = mods
		self.failed = False
		self.reset()

	def reset(self):
		self.waiting = {}
		self.building = {}
		self.installed = {}
		self.failed = {}

	def report(self):
		wait_list = ','.join(self.waiting)
		building_list = ','.join(self.building)
		installed_list = ','.join(self.installed)
		failed_list = ','.join(self.failed)
		print(now(),
			"building=[" + building_list
			+ "] waiting=[" +  wait_list
			+ "] installed=[" + installed_list
			+ "]"
		)
		if len(self.failed) > 0:
			print(now(), "failed=" + failed_list, file=sys.stderr)
			return False

		return True

	def _build_thread(self, mod):

		del self.waiting[mod.name]
		self.building[mod.name] = mod
		#self.report()

		try:
			if mod.install():
				self.installed[mod.name] = mod
			else:
				self.failed[mod.name] = mod
				print(now(), mod.name + ": FAILED", file=sys.stderr)

		except Exception as e:
			print(now(), mod.name + ": FAILED. Logs are in", mod.out_dir, file=sys.stderr)
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
			# lookup any strings-based dependencies
			depends = []
			if type(mod) == str:
				if not mod in global_mods:
					die(mod + ": not found?")
				mod = global_mods[mod]

			for dep in mod.depends:
				if type(dep) == str:
					if not dep in global_mods:
						die(dep + ": not found? referenced by " + mod.name)
					dep = global_mods[dep]
				depends.append(dep)

			mod.depends = depends
					
			ts.add(mod, *mod.depends)
			for dep in mod.depends:
				self.mods.append(dep)

		ordered_mods = [*ts.static_order()]
		print([x.name for x in ordered_mods])

		for mod in ordered_mods:
			mod.install(check=True)
			if mod.installed:
				self.installed[mod.name] = mod
			else:
				self.waiting[mod.name] = mod
			print(mod.state() + " " + mod.name + ": " + mod.out_dir)

		self.report()
#		for modname, mod in self.built.items():
#			print(mod.state() + " " + mod.name + ": " + mod.out_dir)
#		for modname, mod in self.waiting.items():
#			print(mod.state() + " " + mod.name + ": " + mod.out_dir)


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
					if not dep.name in self.installed:
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
