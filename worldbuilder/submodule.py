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
from glob import glob

from worldbuilder.util import *

build_dir = 'build'
ftp_dir = os.path.join(build_dir, 'ftp')
src_dir = os.path.join(build_dir, 'src')
out_dir = os.path.join(build_dir, 'out')
cache_dir = os.path.join(build_dir, 'cache')
install_dir = os.path.join(build_dir, 'install')
cache_server = None

# global list of modules; names must be unique
global_mods = {}

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
		kconfig_file = ".config",
		config_append = None,
		configure = None,
		make = None,
		install = None,
		depends = None,
		dep_files = None,
		#install_dir = "install",
		lib_dir = "lib",
		bin_dir = "bin",
		inc_dir = "include",
		patch_level = 1,
		strip_components = 1,
		bins = None,
		libs = None,
		report_hashes = False,
		cacheable = False,
	):
		#if not url and not git:
			#raise RuntimeError("url or git must be specified")
		if name.endswith("-" + version):
			self.fullname = name
		else:
			self.fullname = name + "-" + version

		if name in global_mods:
			info(name + ": already exists in the global module list?")
		else:
			global_mods[name] = self
		global_mods[name + "-" + version] = self

		self.name = name
		self.url = url
		#self.git = git
		self.report_hashes = report_hashes
		self.version = "NOVERSION" if not version else version
		self.tarhash = tarhash
		self.patch_files = patches or []
		self.config_files = config_files or []
		self.config_append = config_append or []
		self.kconfig_file = kconfig_file

		self.configure_commands = configure # or [ "true" ]
		self.make_commands = make  #or [ "true" ]
		self.install_commands = install  #or [ "true" ]
		self.cacheable = cacheable

		self.depends = depends or []
		self.dep_files = dep_files or []
		self._bin_dir = "bin" if bin_dir is None else bin_dir
		self._lib_dir = "lib" if lib_dir is None else lib_dir
		self._inc_dir = "include" if inc_dir is None else inc_dir
		#self._install_dir = install_dir # "install" if install_dir is None else install_dir

		# referenced to the install directory
		# todo: how to handle symlinks?
		self._bins = bins or []
		self._libs = libs or []
		self.bins = []
		self.libs = []

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
		self.top_dir = build_dir
		self.last_logfile = "NONE"

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
			print(self.fullname + ":", self.dict)
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
			"top_dir": self.top_dir,
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
			return False

		# make sure we have a place to put it
		mkdir(ftp_dir)

		info("FETCH   " + self.fullname + ": fetching " + url)

		r = requests.get(url)
		if r.status_code != requests.codes.ok:
			print(url + ": failed!", r.text, file=sys.stderr)
			return False
			
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

		if not self.fetch(check=check):
			return False

		# if the name includes its own version, don't double append it
		if self.name.endswith(self.version):
			src_subdir = self.name
		else:
			src_subdir = self.name + "-" + self.version

		if self.dirty:
			# the src_subdir is based on the output hash,
			# not the src hash, since it writes to the
			# directory.
			src_subdir = os.path.join(src_subdir, self.out_hash[0:16])
			self.src_dir = os.path.abspath(os.path.join(out_dir, src_subdir))
		else:
			# unpack the clean source in its own directory
			src_subdir = os.path.join(src_subdir, self.src_hash[0:16])
			self.src_dir = os.path.abspath(os.path.join(src_dir, src_subdir))
		self.update_dict()

		unpack_canary = os.path.join(self.src_dir, '.unpacked')
		if exists(unpack_canary):
			self.unpacked = True
			return self

		if check:
			return self

		if self.dirty:
			info("CLEANUP " + self.fullname)
			system("rm", "-rf", self.src_dir)

		mkdir(self.src_dir)

		info("UNPACK  " + self.fullname + ": " + relative(self.tar_file) + " -> " + relative(self.src_dir))
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
			if len(self.patch_files) > 0:
				self.patched = True
			else:
				self.unpacked = True
			return self

		if not self.unpack(check):
			return False
		patch_canary = os.path.join(self.src_dir, '.patched')
		if exists(patch_canary):
			if len(self.patch_files) > 0:
				self.patched = True
			return self

		if check:
			return self

		mkdir(self.out_dir)

		for (patch_file,patch) in self.patches:
			info("PATCH   " + self.fullname + ": " + relative(patch_file))

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
		if len(self.patch_files) > 0:
			self.patched = True
		return self

	def compute_src_hash(self):
		self.src_hash = self.tarhash or zero_hash

		self.patches = []
		for filename in self.patch_files:
			expanded = self.format(filename)
			files = sorted(glob(expanded))
			if len(files) == 0:
				# files are missing!
				print(self.fullname + ": no match for " + expanded + "(originally " + filename + ")", file=sys.stderr)
				#return False
			for patch_filename in files:
				patch = readfile(patch_filename)
				self.patches.append([patch_filename, patch])
				self.src_hash = extend(self.src_hash, [patch])
				#print(self.name + ": patch file " + patch_filename, self.src_hash)

	def compute_out_hash(self, config_file_hash = zero_hash):
		# the output hash depends on the source hash,
		# the source config files, any updates to those files,
		# the commands executed to configure the programs,
		# and any dependencies
		# todo: should the hash be on the unexpanded append lines?
		self.configs = readfiles(self.config_files)
		config_file_hash = extend(config_file_hash, self.configs)

		# hash the unexpanded the configuration appended lines first
		for append in self.config_append:
			config_file_hash = extend(config_file_hash, append)

		config_hash = zero_hash
		if self.configure_commands:
			if  type(self.configure_commands[0]) == str:
				self.configure_commands = [ self.configure_commands ]
			for commands in self.configure_commands:
				cmd_hash = extend(None, commands)
				config_hash = extend(config_hash, cmd_hash)

		config_hash = extend(config_hash, [
			#self._install_dir,
			self._inc_dir,
			self._lib_dir,
			self._bin_dir,
			"dirty-tree" if self.dirty else "clean-tree",
			*self.dep_files,
			*self._bins,
			*self._libs
		])

		make_hash = zero_hash
		if self.make_commands:
			if type(self.make_commands[0]) == str:
				self.make_commands = [ self.make_commands ]
			for commands in self.make_commands:
				cmd_hash = extend(None, commands)
				make_hash = extend(make_hash, cmd_hash)

		install_hash = zero_hash
		if self.install_commands:
			if type(self.install_commands[0]) == str:
				self.install_commands = [ self.install_commands ]
			for commands in self.install_commands:
				cmd_hash = extend(None, commands)
				install_hash = extend(install_hash, cmd_hash)

		new_out_hash = extend(self.src_hash, [config_file_hash, config_hash, make_hash, install_hash])

		# and the output hash of the direct dependencies
		for dep in self.depends:
			new_out_hash = extend(new_out_hash, dep.out_hash)

#		print(self.name + ": ", new_out_hash, self.src_hash)
		if new_out_hash != self.out_hash and self.out_hash != zero_hash:
			print(self.fullname + ": HASH CHANGED ", new_out_hash, self.out_hash)
			exit(-1)
		self.out_hash = new_out_hash

		# todo: include more configuration in the out_hash (dirty, inc_dir, etc)
		if self.name.endswith(self.version):
			out_subdir = self.name
		else:
			out_subdir = self.name + "-" + self.version

		out_subdir = os.path.join(out_subdir, self.out_hash[0:16])
		self.out_dir = os.path.abspath(os.path.join(out_dir, out_subdir))
		self.rout_dir = os.path.join('..', '..', '..', 'out', out_subdir)
		self.install_dir = os.path.abspath(os.path.join(install_dir, out_subdir))
		self.bin_dir = os.path.join(self.install_dir, self._bin_dir)
		self.lib_dir = os.path.join(self.install_dir, self._lib_dir)
		self.inc_dir = os.path.join(self.install_dir, self._inc_dir)
		self.top_dir = os.path.abspath(build_dir)

		self.update_dict()

		# build the list of output binaries and libraries
		self.bins = [self.format("%(bin_dir)s/" + f) for f in self._bins]
		self.libs = [self.format("%(lib_dir)s/" + f) for f in self._libs]


	def run_commands(self, logfile_name, command_list):
		self.last_logfile = os.path.join(self.out_dir, logfile_name)
		for commands in command_list:
			cmds = []
			for cmd in commands:
				cmds.append(self.format(cmd))

			system(*cmds,
				cwd=self.out_dir,
				log=self.last_logfile,
			)

	def configure(self, check=False):
		if not self.patch(check):
			return False

		config_canary = os.path.join(self.out_dir, ".configured")
		if exists(config_canary):
			self.configured = True
			return self

		if check:
			# don't actually touch anything
			return self

		mkdir(self.out_dir)

		kconfig_file = os.path.join(self.out_dir, self.kconfig_file)

		# expand the configuration appended lines now
		for append in self.config_append:
			#print(self.name + ": adding " + append)
			self.configs.append(self.format(append).encode('utf-8'))

		writefile(kconfig_file, b'\n'.join(self.configs))

		if self.configure_commands:
			info("CONFIG  " + self.fullname)
			self.run_commands("configure-log", self.configure_commands)

		writefile(config_canary, b'')
		self.configured = True
		return self


	def build_required(self, force, build_canary):
		# update our check time for GC of build trees
		mkdir(self.out_dir)
		writefile(os.path.join(self.out_dir, '.build-checked'), b'')

		# no canary? definitely have to rebuild
		self.built = False
		if not exists(build_canary) or force:
			return True

		# do a scan of the dependent files for timestamps relative to canary
		canary_build_time = os.stat(build_canary).st_mtime
		for filename in self.dep_files:
			real_filename = self.format(filename)
			if not exists(real_filename):
				#print(self.name + ": no " + real_filename)
				return True
			if os.stat(real_filename).st_mtime > canary_build_time:
				#print(self.name + ": newer " + real_filename)
				return True

		# and check all of our dependencies
		for dep in self.depends:
			if not dep.installed:
				return True

		# we're probably already built
		return False

	def build(self, force=False, check=False):
		if not self.configure(check=check):
			return False

		build_canary = os.path.join(self.out_dir, ".built-" + self.name)
		if not self.build_required(force, build_canary):
			# we're already done
			self.built = True
			return self
		if check:
			return False

		if self.make_commands:
			info("BUILD   " + self.fullname)
			self.run_commands("make-log", self.make_commands)

		writefile(build_canary, b'')
		self.built = True

		return self

	def cache_create(self, cache_dir):
		mkdir(cache_dir)
		cache_filename = self.fullname + "-" + self.out_hash[0:16] + ".tar.gz"
		tar_filename = os.path.join(cache_dir, cache_filename)
		info("CACHE   " + self.fullname + ": " + relative(tar_filename))
		system("tar", "-zcf", tar_filename, "-C", self.install_dir, ".")
		return True

	def cache_fetch(self):
		cache_filename = self.fullname + "-" + self.out_hash[0:16] + ".tar.gz"
		tar_filename = os.path.join(cache_dir, cache_filename)
		url = cache_server + "/" + cache_filename
		r = requests.get(url)
		if r.status_code != requests.codes.ok:
			return False

		mkdir(cache_dir)
		mkdir(self.install_dir)

		info("CACHED  " + self.fullname + ": " + url)
		writefile(tar_filename, r.content)
		system("tar", "-zxf", tar_filename, "-C", self.install_dir)

		return True

	def install(self, force=False, check=False):
		cache_canary = os.path.join(self.install_dir, ".cache-" + self.name)
		if exists(cache_canary) and not force:
			# this is a cached build, do not attempt any further builds
			print(self.name + ": cached build available " + self.install_dir)
			self.installed = True
			return self

		# if we're actually building and cacheable, try to see if the
		# cache server has a cached version for us
		if self.cacheable and cache_server and not check:
			if self.cache_fetch() and exists(cache_canary):
				return True

		if not self.build(force=force, check=check):
			return False

		install_canary = os.path.join(self.install_dir, ".install-" + self.name)
		if exists(install_canary) and not force:
			self.installed = True
			return self
		if check:
			return self

		mkdir(self.install_dir)

		if self.install_commands:
			info("INSTALL " + self.fullname + ": " + relative(self.install_dir) )
			self.run_commands("install-log", self.install_commands)

		if self.report_hashes:
			for filename in self.bins:
				full_name = os.path.join(self.bin_dir, filename)
				file_hash = sha256hex(readfile(full_name))
				print(relative(full_name) + ": " + file_hash)
			for filename in self.libs:
				full_name = os.path.join(self.bin_dir, filename)
				file_hash = sha256hex(readfile(full_name))
				print(relative(full_name) + ": " + file_hash)

		writefile(install_canary, b'')
		self.installed = True

		if self.cacheable:
			writefile(cache_canary, b'')

		return self

	def update_hashes(self):
		self.compute_src_hash()
		self.compute_out_hash()
