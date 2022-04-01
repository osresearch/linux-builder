# Linux gets its own specialized builder since the kconfig
# setup is a little challenging and there is a need to have headers
# installed separately from the kernel builds.

from worldbuilder.submodule import Submodule
from worldbuilder.initrd import Initrd
from worldbuilder.util import *

versions = {
	"4.14.62": "51ca4d7e8ee156dc0f19bc7768915cfae41dbb0b4f251e4fa8b178c5674c22ab",
	"4.19.139": "9c4ebf21fe949f80fbcfbbd6e7fe181040d325e89475e230ab53ef01f9d55605",
	"5.4.69": "a8b31d716b397303a183e42ad525ff2871024a43e3ea530d0fdf73b7f9d27da7",
	"5.4.117": "4e989b5775830092e5c76b5cca65ebff862ad0c87d0b58c3a20d415c3d4ec770",
}

def LinuxSrc(
	version = "5.4.117",
	patches = None,
	tarhash = None,
):
	if not tarhash:
		if version not in versions:
			warn("Linux kernel version " + version + " unknown!")
		else:
			tarhash = versions[version]

	return Submodule(
		'linux',
		url = "https://cdn.kernel.org/pub/linux/kernel/v%(major)s.x/linux-%(version)s.tar.xz",
		version = version,
		tarhash = tarhash,
		configure = [
			"make",
			"-C%(src_dir)s",
			"O=%(install_dir)s",
			"defconfig",
		],
		install = [
			"make",
			"-C%(src_dir)s",
			"O=%(install_dir)s",
			"headers_install"
		],
		inc_dir = "usr/include",
	)

def Linux(
	name,
	src = None,
	depends = None,
	compiler = None,
	initrd = None,
	hostname = None,
	config = None,
	config_append = None,
	cmdline = None,
):
	if not depends:
		depends = []

	# if they didn't say which kernel, use the default
	if not src:
		src = LinuxSrc()
	depends.append(src)

	if type(src) is str:
		(linux_name,linux_version) = src.rsplit("-", 1)
	else:
		linux_version = src.version
		linux_name = src.name
	

# The Linux kernel will create an irreproducible initrd
# if one is not specified.  This creates a tiny one with
# just the /dev/console required to boot the kernel.
	if not initrd:
		initrd = Initrd("dev-" + name,
			filename = "initrd.cpio",
			version = "0.0.0",
			add_hashes = False,
			devices = [
				[ "/dev/console", "c", 5, 1 ],
			],
		)
		initrd_name = "initrd-dev-" + name
	elif type(initrd) == str:
		initrd_name = initrd
	else:
		initrd_name = initrd.name

	depends.append(initrd)

	cross_tools_if_cross = []
	if compiler:
		depends.append(compiler.crossgcc)
		cross_tools_if_cross = [
			*compiler.cross_tools_nocc,
			"CROSS_COMPILE=" + compiler.cross,
			"CC=" + compiler.cross + "gcc",
		]

	if not config_append:
		config_append = []
	config_append.append('CONFIG_INITRAMFS_SOURCE="%('+initrd_name+'.install_dir)s/initrd.cpio"')

	if hostname:
		config_append.append('CONFIG_DEFAULT_HOSTNAME="' + hostname + '"')
	if cmdline:
		config_append.append('CONFIG_CMDLINE="' + cmdline + '"')
		config_append.append('CONFIG_CMDLINE_BOOL=y')

	return Submodule(
		'linux-' + name,
		version = linux_version,
		depends = depends,
		config_files = [ config ],
		config_append = config_append,
		configure = [
			"make",
			"-C%("+linux_name +".src_dir)s",
			"O=%(out_dir)s",
			"olddefconfig",
			*cross_tools_if_cross,
		],
		make = [ 
			"make",
			"-C%("+linux_name+".src_dir)s",
			"O=%(out_dir)s",
			"V=1",
			"KBUILD_BUILD_HOST=builder",
			"KBUILD_BUILD_USER=%(out_hash)s",
			"KBUILD_BUILD_TIMESTAMP=1970-01-01T00:00:00",
			"KBUILD_BUILD_VERSION=%("+linux_name+".src_hash)s",
			*cross_tools_if_cross,
		],
		install_dir = "arch/x86/boot",
		bin_dir = '',
		bins = [ 'bzImage' ],
		report_hashes = True,
	)
