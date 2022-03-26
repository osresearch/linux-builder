#!/usr/bin/python3.9
# build a small initd world
import worldbuilder
import cpiofile
import os

from crosscompile import gcc, crossgcc, cross_tools_nocc, cross_tools, cross, target_arch, musl

linux = worldbuilder.Submodule("linux",
	depends = [ crossgcc ], # doesn't need musl so it can start earlier
	url = "https://cdn.kernel.org/pub/linux/kernel/v%(major)s.x/linux-%(version)s.tar.xz",
	version = "5.4.117",
	tarhash = "4e989b5775830092e5c76b5cca65ebff862ad0c87d0b58c3a20d415c3d4ec770",
	config_files = [ "config/linux-virtio.config" ],
	configure = [
		"make",
		"-C%(src_dir)s",
		"O=%(rout_dir)s",
		"olddefconfig",
		*cross_tools_nocc,
		#"CC=" + cross + "gcc",
	],
	#depends = [ binutils ], # should it use the cross compiler?
	make = [ 
		worldbuilder.kbuild_make,
		[ "make", "headers_install" ],
	]
)

linux_hdrs = "-I%(linux.out_dir)s/usr/include"

busybox = worldbuilder.Submodule("busybox",
	depends = [ gcc, linux ],
	url = "https://busybox.net/downloads/busybox-%(version)s.tar.bz2",
	version = "1.32.0",
	tarhash = "c35d87f1d04b2b153d33c275c2632e40d388a88f19a9e71727e0bbbff51fe689",
	config_files = [ "config/busybox.config" ],
	#patches = [ "patches/busybox-1.28.0.patch" ],
	configure = [
		"make",
		"-C%(src_dir)s",
		"O=%(rout_dir)s",
		"oldconfig",
		*cross_tools,
		"CFLAGS=" + linux_hdrs,
	],
	make = [
		*worldbuilder.kbuild_make,
		"V=1",
		"install",
		*cross_tools,
		"CFLAGS=" + linux_hdrs,
	],
)

util_linux = worldbuilder.Submodule("util-linux",
	version		= "2.29.2",
	url		= "https://www.kernel.org/pub/linux/utils/util-linux/v%(major)s.%(minor)s/util-linux-%(version)s.tar.xz",
	tarhash		= "accea4d678209f97f634f40a93b7e9fcad5915d1f4749f6c47bee6bf110fe8e3",
	depends		= [ linux, gcc ],
	configure	= [
		worldbuilder.configure_cmd,
		"--prefix=%(install_dir)s",
		"--target", target_arch,
		"--host", 'x86_64-linux-gnu',
		"--without-ncurses",
		"--without-ncursesw",
		"--without-tinfo",
		"--without-udev",
		"--without-python",
		"--disable-bash-completion",
		"--disable-all-programs",
		"--enable-libuuid",
		"--enable-libblkid",
		*cross_tools,
		"CFLAGS=" + linux_hdrs,
	],
	make = [ "make", "install", "V=1" ],
)

zlib = worldbuilder.Submodule('zlib',
	depends = [ gcc ],
	version = '1.2.11',
	url = 'https://www.zlib.net/zlib-%(version)s.tar.gz',
	tarhash = 'c3e5e9fdd5004dcb542feda5ee4f0ff0744628baf8ed2dd5d66f8ca1197cb1a1',
	configure = [
		worldbuilder.configure_cmd,
		"--prefix=%(install_dir)s",
		*cross_tools,
	],
	make = [ "make" ],
)
#zlib_libraries := libz.so.1

kexec = worldbuilder.Submodule('kexec',
	version = '2.0.20',
	url = 'https://kernel.org/pub/linux/utils/kernel/kexec/kexec-tools-%(version)s.tar.gz',
	tarhash = 'cb16d79818e0c9de3bb3e33ede5677c34a1d28c646379c7ab44e0faa3eb57a16',
	patches = [
		"patches/kexec-2.0.20.patch",
		"patches/kexec-2.0.20-duplicate-symbols.patch",
	],
	depends = [ linux, gcc ],
	configure = [
		worldbuilder.configure_cmd,
		"--prefix=%(install_dir)s",
		"--host", 'x86_64-linux-gnu', #'i386-elf-linux',
		"--target", 'x86_64',
		"--without-lzma",
		*cross_tools,
		"CFLAGS=" + linux_hdrs,
	],
	make = [ "make", "install" ],
	bin_dir = 'sbin',
)

pciutils = worldbuilder.Submodule("pciutils",
	depends = [ gcc, linux ],
	version = "3.5.4",
	url = "https://www.kernel.org/pub/software/utils/%(name)s/%(name)s-%(version)s.tar.xz",
	tarhash = "64293c6ab9318c40ef262b76d87bd9097531759752bac556e50979b1e63cfe66",
	patches = [ "patches/pciutils-3.5.4.patch" ],

	# the makefile writes in the source directory
	dirty = True,

	configure = [ "true" ],

# IDSDIR must be set to a constant during the build,
# but not during the install to make the libpci.so.3
# reproducible.  Otherwise the build path will be embedded
# in the library and executables.
	make = [ [
		"make",
		"ZLIB=no",
		"HWDB=no",
		"LIBKMOD=no",
		"SHARED=yes",
		"IDSDIR=/",
		"PREFIX=/",
		*cross_tools,
		"CFLAGS=-fpic " + linux_hdrs,
		], [
		"make",
		#"ZLIB=no",
		#"HWDB=no",
		#"LIBKMOD=no",
		#"SHARED=yes",
		"PREFIX=/",
		"DESTDIR=%(install_dir)s",
		"install",
		"install-lib",
	] ],
	bin_dir = "sbin",
)

#pciutils_output := lspci
#pciutils_libraries := lib/libpci.so.3.5.4 ../../install/lib/libpci.so.3


#kexec_output := build/sbin/kexec

#build = worldbuilder.Builder([kexec, util_linux, linux, busybox])
#build = builder.Builder([busybox, kexec, util_linux])
build = worldbuilder.Builder([pciutils, busybox, kexec, util_linux])
#build.check()
if not build.build_all():
	exit(-1)

# make a ramdisk
cpio = cpiofile.CPIO()

cpio.mkdir("/lib64")
cpio.mkdir("/lib")
#cpio.symlink("/lib/x86_64-linux-gnu", "../lib64")

cpio.mknod("/dev/console", "c", 5, 1)

cpio.mkdir("/bin")
cpio.add("/bin", os.path.join(kexec.bin_dir, "kexec"))

cpio.add("/bin", os.path.join(pciutils.bin_dir, "lspci"))

cpio.add("/bin", os.path.join(busybox.bin_dir, "busybox"))
cpio.symlink("/bin/sh", "./busybox")

cpio.add("/lib", os.path.join(musl.lib_dir, "libc.so"))
cpio.symlink("/lib/ld-musl-x86_64.so.1", "libc.so")

image = cpio.tobytes()
with open("image.cpio", "wb") as f:
	f.write(image)
