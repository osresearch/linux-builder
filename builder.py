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

verbose = 3
build_dir = 'build'
ftp_dir = os.path.join(build_dir, 'ftp')
src_dir = os.path.join(build_dir, 'src')
out_dir = os.path.join(build_dir, 'out')

def sha256hex(data):
	#print("hashing %d bytes" % (len(data)), data)
	return hashlib.sha256(data).hexdigest()
def extend(h, data):
	if h is None:
		h = '0' * 64
	for datum in data:
		if type(datum) is str:
			datum = datum.encode('utf-8')
		h = sha256hex((h + sha256hex(datum)).encode('utf-8'))
	return h

def system(*s, cwd=None):
	if not cwd:
		cwd = '.'
	if verbose > 2:
		print(s, 'cwd='+cwd)
	# do not close file descriptors, which will allow
	# communication from sub-make invocations to the make
	# that invoked us
	subprocess.run(s, cwd=cwd, check=True, close_fds=False)
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

class BuilderBase:
	def __init__(self,
		name,
		url = None,
		#git = None,
		version = None,
		tarhash = None,
		patch_files = None,
		config_files = None,
		configure = None,
		make = None,
		depends = None,
	):
		#if not url and not git:
			#raise RuntimeError("url or git must be specified")

		self.name = name
		self.url = url
		#self.git = git
		self.version = version
		self.tarhash = tarhash
		self.patch_files = patch_files
		self.config_files = config_files
		self.configure_commands = configure
		self.make_commands = make
		self.depends = depends

		self.patch_level = 1
		self.strip_components = 1
		self.tar_options = []

		self.src_hash = '0' * 64
		self.out_hash = '0' * 64
		self.major = None
		self.minor = None
		self.patchver = None
		self.src_dir = None
		self.out_dir = None
		self.rout_dir = None

		self.built = False
		self.building = False

		if not self.patch_files:
			self.patch_files = []
		if not self.config_files:
			self.config_files = []
		if not self.depends:
			self.depends = []

		if not self.configure_commands:
			self.configure_commands = [
				"%(src_dir)s/configure"
			]
		if not self.make_commands:
			self.make_commands = [ "make" ]

		self.update_dict()

	def format(self, cmd):
 		return cmd % self.dict

	def update_dict(self):
		self.dict = {
			"version": self.version,
			"major": self.major,
			"minor": self.minor,
			"patch": self.patchver,
			"src_hash": self.src_hash[0:16],
			"out_hash": self.out_hash[0:16],
			"src_dir": self.src_dir,
			"out_dir": self.out_dir,
			"rout_dir": self.rout_dir,
		}

		# recursively add the dependencies environments
		for dep in self.depends:
			for key in dep.dict:
				self.dict[dep.name + "." + key] = dep.dict[key]

	def get_url(self):
		# semver the version string
		version = self.version.split('.')
		self.major = version[0]
		if len(version) > 1:
			self.minor = version[1]
		if len(version) > 2:
			self.patchver = version[2]

		self.update_dict()

		url = self.format(self.url)
		(base,f) = os.path.split(url)
		return (base+"/" + f, f)

	def fetch(self, force=False):
		(url,tar) = self.get_url()
		dest_tar = os.path.join(ftp_dir, tar)
		if exists(dest_tar) and not force:
			return dest_tar

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
		return dest_tar

	def unpack(self):
		tarfile = self.fetch()
		if not tarfile:
			return False

		self.patches = readfiles(self.patch_files)
		self.src_hash = extend(self.tarhash, self.patches)

		src_subdir = os.path.join(self.name + "-" + self.version, self.src_hash[0:16])
		self.src_dir = os.path.abspath(os.path.join(src_dir, src_subdir))
		self.update_dict()

		unpack_canary = os.path.join(self.src_dir, '.unpacked')
		if exists(unpack_canary):
			return self

		mkdir(self.src_dir)

		info(tarfile + ": unpacking into " + self.src_dir)
		system("tar",
			"-xf", tarfile,
			"-C", self.src_dir,
			"--strip-components", "%d" % (self.strip_components),
			*self.tar_options,
		)

		writefile(unpack_canary, b'')
		return self

	def patch(self):
		if not self.unpack():
			return False

		patch_canary = os.path.join(self.src_dir, '.patched')
		if exists(patch_canary):
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
		return self

	def configure(self):
		if not self.patch():
			return False

		# the output hash depends on the source hash,
		# the configure command, the make command
		# and (TODO) the output hash of the direct dependencies
		configs = readfiles(self.config_files)
		config_hash = extend(None, [x.encode('utf-8') for x in self.configure_commands])
		make_hash = extend(None, [x.encode('utf-8') for x in self.make_commands])
		self.out_hash = extend(self.src_hash, [*configs, config_hash, make_hash])
		out_subdir = os.path.join(self.name + "-" + self.version, self.out_hash[0:16])
		self.out_dir = os.path.abspath(os.path.join(out_dir, out_subdir))
		self.rout_dir = os.path.join('..', '..', '..', 'out', out_subdir)
		self.update_dict()
		mkdir(self.out_dir)

		config_canary = os.path.join(self.out_dir, ".configured")
		if exists(config_canary):
			return self

		kconfig_file = os.path.join(self.out_dir, ".config")
		writefile(kconfig_file, b'\n'.join(configs))

		cmds = []
		for cmd in self.configure_commands:
			cmds.append(self.format(cmd))

		system(*cmds, cwd=self.out_dir)
		writefile(config_canary, b'')

		return self

	def build(self, force=False):
		if not self.configure():
			return False

		build_canary = os.path.join(self.out_dir, ".built")
		if exists(build_canary) and not force:
			self.built = True
			return self

		cmds = []
		for cmd in self.make_commands:
			cmds.append(self.format(cmd))

		system(*cmds, cwd=self.out_dir)

		writefile(build_canary, b'')
		self.built = True
		return self


if __name__ == "__main__":
	pass
