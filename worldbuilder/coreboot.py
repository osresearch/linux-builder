# coreboot is such a bear that it gets its own python module
# and the crosscompiler is required

from worldbuilder import Submodule
from worldbuilder import commands
from worldbuilder.util import *

versions = {
	"4.8.1": {
		"tarhash": "f0ddf4db0628c1fe1e8348c40084d9cbeb5771400c963fd419cda3995b69ad23",
		"blobs_hash": "18aa509ae3af005a05d7b1e0b0246dc640249c14fc828f5144b6fd20bb10e295",
	},
	"4.11": {
		"tarhash": "97fd859b4c39a25534fe33c30eb86e54a233952e08a024c55858d11598a8ad87",
		"blobs_hash": "aa7855c5bd385b3360dadc043ea6bc93f564e6e4840d9b3ee5b9e696bbd055db",
	},
	"4.13": {
		"tarhash": "4779da645a25ddebc78f1bd2bd0b740fb1e6479572648d4650042a2b9502856a",
		"blobs_hash": "060656b46a7859d038ddeec3f7e086e85f146a50b280c4babec23c1188264dc8",
	},
	"4.15": {
		"tarhash": "20e6aaa6dd0eaec7753441c799711d1b4630e3ca709536386f2242ac2c8a1ec5",
		"blobs_hash": "c0e2d8006da226208ba274a44895d102cb2879cf139cc67bba5f62e67b871f6d",
		#"extra_flags": "-fdebug-prefix-map=$(pwd)=heads -gno-record-gcc-switches -Wno-error=packed-not-aligned -Wno-error=address-of-packed-member -Wno-error",
	},
}



def CorebootSrc(
	version,
	patches = None,
	tarhash = None,
	blobhash = None,
):
	if not tarhash:
		if version not in versions:
			warn("coreboot " + version + " is unknown")
		else:
			tarhash = versions[version]["tarhash"]
			blobhash = versions[version]["blobs_hash"]

	src = Submodule(
		"coreboot-" + version,
		version = version,
		depends = [ "gcc32", "iasl" ],
		url = "https://www.coreboot.org/releases/coreboot-%(version)s.tar.xz",
		tarhash = tarhash,
		patches = patches,
	)

	# the src depends on the blobs so that the return from the function
	# can be the src tree, which will be ready to try compiling once
	# things are ready.
	blobs = Submodule(
		"coreboot_blobs-" + version,
		version = version,
		depends = [ src ],
		url = "https://www.coreboot.org/releases/coreboot-blobs-%(version)s.tar.xz",
		tarhash = blobhash,
		strip_components = 3,
		install = [
			"ln", "-sf",
			"%(src_dir)s",
			"%(" + src.name + ".src_dir)s/3rdparty/blobs",
		],
	)

	return src

def Coreboot(
	name,
	src = None,
	config = None,
	initrd = None,
	kernel = None,
	compiler = None,
):
	if not config or not initrd or not kernel or not compiler:
		die(name + ": coreboot requires config,initrd, kernel and crosscompiler")

	if type(initrd) == str:
		initrd_name = initrd
	else:
		initrd_name = initrd.name

	if type(kernel) == str:
		kernel_name = kernel
	else:
		kernel_name = kernel.name

	if type(src) == str:
		coreboot_name = src
		(stub,coreboot_version) = coreboot_name.rsplit('-', 1)
	else:
		coreboot_name = src.name
		coreboot_version = src.version

	initrd_file = '%(' + initrd_name + '.install_dir)s/initrd.cpio.xz'
	kernel_file = '%(' + kernel_name + '.install_dir)s/bzImage'

	extra_env = [
		"V=1",
		"BUILD_TIMELESS=1",
		"obj=%(out_dir)s/" + name,
		"DOTCONFIG=%(out_dir)s/.config",
		"IASL=%(iasl.bin_dir)s/iasl",
		"CROSS_COMPILE_x86=" + compiler.cross32,
		"CROSS_COMPILE_x64=" + compiler.cross,
		"CC_x86_32=" + compiler.cross32 + "gcc",
		"CC_x86_64=" + compiler.cross + "gcc",
		"CFLAGS_x86_32="
			+ "-Wno-error=packed-not-aligned -Wno-error=address-of-packed-member "
			+ commands.prefix_map,
		*compiler.cross_tools32_nocc,
	]

	return Submodule(
		"coreboot-" + name,
		version = coreboot_version,
		depends = [
			initrd,
			kernel,
			src,
			"coreboot_blobs-" + coreboot_version,
		],
		config_files = [ config ],
		dep_files = [ initrd_file, kernel_file ],
		config_append = [
			'CONFIG_LINUX_INITRD="' + initrd_file + '"',
			'CONFIG_PAYLOAD_FILE="' + kernel_file + '"',
			'CONFIG_LOCALVERSION="%(out_hash)s"',
			'CONFIG_MAINBOARD_SMBIOS_PRODUCT_NAME="' + name + '"',
		],

		configure = [
			"make",
			"olddefconfig",
			"-C%("+coreboot_name+".src_dir)s",
			*extra_env,
		],

		# work around a bug in make that doesn't pass command line vars in the environment
		# which prevents the local iasl binary from being used by subshells
		make = [ "bash", "-c", " ".join([
			*make_env(extra_env),
			"make",
			"-C%("+coreboot_name+".src_dir)s",
		])],

		install_dir = '',
		bin_dir = name,

		bins = [ "coreboot.rom" ],
		report_hashes = True,
	)

"""
$(build)/$(BOARD)/$(CB_OUTPUT_FILE): $(build)/$(coreboot_dir)/.build
	# Use coreboot.rom, because custom output files might not be processed by cbfstool
	"$(build)/$(coreboot_dir)/cbfstool" "$(dir $<)coreboot.rom" print
	$(call do-copy,$(dir $<)$(CONFIG_COREBOOT_ROM),$@)
	@touch $@   # update the time stamp

ifneq ($(CONFIG_COREBOOT_BOOTBLOCK),)
$(build)/$(BOARD)/$(CB_BOOTBLOCK_FILE): $(build)/$(coreboot_dir)/.build
	$(call do-copy,$(dir $<)$(CONFIG_COREBOOT_BOOTBLOCK),$@)
	@touch $@   # update the time stamp
endif

endif

#
# Helpful target for reconfiguring the coreboot target
#
coreboot.menuconfig:
	$(MAKE) \
		-C "$(build)/$(coreboot_base_dir)" \
		DOTCONFIG="$(build)/$(coreboot_dir)/.config" \
		menuconfig

# The config file in the repo is stored as a "defconfig" format
# which only includes the options that have changed from the defaults.
coreboot.saveconfig:
	$(MAKE) \
		-C "$(build)/$(coreboot_base_dir)" \
		DOTCONFIG="$(build)/$(coreboot_dir)/.config" \
		DEFCONFIG="$(pwd)/$(CONFIG_COREBOOT_CONFIG)" \
		savedefconfig


# if we are not building from a git checkout,
# we must also download the coreboot-blobs tree
ifneq "$(coreboot_version)" "git"

coreboot_depends += coreboot-blobs
modules-y += coreboot-blobs

coreboot-blobs_version := $(coreboot_version)
coreboot-blobs_tar := coreboot-blobs-$(coreboot-blobs_version).tar.xz
coreboot-blobs_url := https://www.coreboot.org/releases/$(coreboot-blobs_tar)


## there is nothing to build for the blobs, this should be
## made easier to make happen
coreboot-blobs_output := .built
coreboot-blobs_configure := echo -e 'all:\n\ttouch .built' > Makefile

endif
endif
"""
