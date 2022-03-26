#!/usr/bin/python3.9
# build a small initd world
import worldbuilder
import cpiofile
import os

mpfr = worldbuilder.Submodule("mpfr",
	version = "4.1.0",
	url = "https://ftp.gnu.org/gnu/%(name)s/%(name)s-%(version)s.tar.xz",
	tarhash = '0c98a3f1732ff6ca4ea690552079da9c597872d30e96ec28414ee23c95558a7f',
	configure = [
		worldbuilder.configure_cmd,
		"--prefix=%(install_dir)s",
		"--enable-static=yes",
		"--enable-shared=no",
	],
	make = [ "make", "install" ],
)
gmp = worldbuilder.Submodule("gmp",
	version = "6.2.1",
	url = "https://ftp.gnu.org/gnu/%(name)s/%(name)s-%(version)s.tar.xz",
	tarhash = 'fd4829912cddd12f84181c3451cc752be224643e87fac497b69edddadc49b4f2',
	configure = [
		worldbuilder.configure_cmd,
		"--prefix=%(install_dir)s",
		"--enable-static=yes",
		"--enable-shared=no",
	],
	make = [ "make", "install" ],
)

mpc = worldbuilder.Submodule("mpc",
	version = "1.2.1",
	url = "https://ftp.gnu.org/gnu/%(name)s/%(name)s-%(version)s.tar.gz",
	tarhash = '17503d2c395dfcf106b622dc142683c1199431d095367c6aacba6eec30340459',
	configure = [
		worldbuilder.configure_cmd,
		"--prefix=%(install_dir)s",
		"--with-mpfr=%(mpfr.install_dir)s",
		"--with-gmp=%(gmp.install_dir)s",
		"--enable-static=yes",
		"--enable-shared=no",
	],
	depends = [ mpfr, gmp ],
	make = [ "make", "install" ],
)

binutils = worldbuilder.Submodule("binutils",
	version = "2.38",
	url = "https://ftp.gnu.org/gnu/%(name)s/%(name)s-%(version)s.tar.xz",
	tarhash = 'e316477a914f567eccc34d5d29785b8b0f5a10208d36bbacedcc39048ecfe024',
	configure = [
		worldbuilder.configure_cmd,
		"--prefix=%(install_dir)s",
		"--target=x86_64-linux-musl",
		"--with-mpc=%(mpc.install_dir)s",
		"--disable-nls",
	],
	depends = [ mpc ],
	make = [
		[ "make" ],
		[ "make", "install" ],
	],
)

bison = worldbuilder.Submodule("bison",
	version = "3.8.2",
	url = "https://ftp.gnu.org/gnu/%(name)s/%(name)s-%(version)s.tar.xz",
	tarhash = '9bba0214ccf7f1079c5d59210045227bcf619519840ebfa80cd3849cff5a5bf2',
	configure = [
		worldbuilder.configure_cmd,
		"--prefix=%(install_dir)s",
	],
	make = [ "make", "install" ],
)

target_arch = "x86_64-linux-musl"
cross = "%(binutils.install_dir)s/bin/" + target_arch + "-"
gcc_cross_tools = [x.upper() + "_FOR_TARGET=" + cross + x
	for x in "ar as ld nm ranlib objcopy objdump strip".split(" ")]
cross_tools = [x.upper() + "=" + cross + x
	for x in "ar as ld nm ranlib objcopy objdump strip".split(" ")]
cross_tools_cc = [
	"CC=%(musl.install_dir)s/bin/musl-gcc", #" + cross + "gcc",
	"CFLAGS=-I%(linux.out_dir)s/usr/include",
	*cross_tools,
]

# this fakes the install into the binutils directory to avoid issues later
crossgcc = worldbuilder.Submodule("gcc",
	url = "https://ftp.gnu.org/gnu/gcc/gcc-%(version)s/%(name)s-%(version)s.tar.xz",
	#version = "9.4.0",
	#tarhash = 'd08edc536b54c372a1010ff6619dd274c0f1603aa49212ba20f7aa2cda36fa8b',
	version = "11.2.0",
	tarhash = 'c95da32f440378d7751dd95533186f7fc05ceb4fb65eb5b85234e6299eb9838e',
	configure = [
		worldbuilder.configure_cmd,
		"--prefix=%(binutils.install_dir)s", # note output!
		"--with-mpc=%(mpc.install_dir)s",
		"--with-gmp=%(gmp.install_dir)s",
		"--with-mpfr=%(mpfr.install_dir)s",
		#"--build", "x86_64-linux-gnu",
		#"--host", "x86_64-linux-gnu",
		"--target", target_arch,
		"--enable-languages=c",
		"--without-headers",
		"--with-newlib",
		"--with-build-time-tools=%(binutils.install_dir)s/bin",
		"--disable-nls",
		"--disable-plugin",
		"--disable-lto",
		"--disable-multilib",
		"--disable-decimal-float",
		"--disable-libmudflap",
		"--disable-libssp",
		"--disable-libgomp",
		"--disable-libquadmath",
		*cross_tools,
	],
	depends = [ binutils, mpc, mpfr, gmp ],
	make = [
		[ "make", "all-gcc" ], 
		[ "make", "install-gcc" ],
	],
)

# select the cross compiler
gcc = crossgcc

linux = worldbuilder.Submodule("linux",
	url = "https://cdn.kernel.org/pub/linux/kernel/v%(major)s.x/linux-%(version)s.tar.xz",
	version = "5.4.117",
	tarhash = "4e989b5775830092e5c76b5cca65ebff862ad0c87d0b58c3a20d415c3d4ec770",
	config_files = [ "config/linux-virtio.config" ],
	configure = [
		"make",
		"-C%(src_dir)s",
		"O=%(rout_dir)s",
		"olddefconfig"
	],
	#depends = [ binutils ], # should it use the cross compiler?
	make = [ 
		worldbuilder.kbuild_make,
		[ "make", "headers_install" ],
	]
)

musl = worldbuilder.Submodule("musl",
	version = "1.2.2",
	url = "https://musl.libc.org/releases/%(name)s-%(version)s.tar.gz",
	tarhash = '9b969322012d796dc23dda27a35866034fa67d8fb67e0e2c45c913c3d43219dd',
	configure = [
		worldbuilder.configure_cmd,
		"--prefix=%(install_dir)s",
		"--syslibdir=%(install_dir)s/lib",
		"CFLAGS=-ffast-math -O3", # avoid libgcc circular math dependency
		"DESTDIR=%(install_dir)s",
		"--enable-wrapper=gcc",
		"--target=" + target_arch,
		"CC=" + cross + "gcc",
		*cross_tools,
	],
	depends = [ linux, gcc ],
	patches = [ "patches/musl-0000-fastmath.patch" ],
	make = [ "make", "install", ],
	#extra_path = "%(binutils.install_dir)s/bin",
)

# pick up in the cross gcc target once musl has been built so that
# libgcc can use the musl headers to build. This is a fake package
# with no source; it simply runs another command in the crossgcc tree
libgcc = worldbuilder.Submodule("libgcc",
	version = "0.0.0",
	depends = [ crossgcc, musl ],
	configure = [ "true" ],
	make = [ [
			"make",
			"-C", "%(gcc.out_dir)s",
			"all-target-libgcc",
			#"install-target-libgcc",
			"CFLAGS_FOR_TARGET=-I%(musl.install_dir)s/include -v -B%(musl.install_dir)s/lib",
			*gcc_cross_tools,
			*cross_tools,
		], [
			"make",
			"-C", "%(gcc.out_dir)s",
			"install-target-libgcc",
		],
	],
)


busybox = worldbuilder.Submodule("busybox",
	depends = [ libgcc, linux ],
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
		*cross_tools_cc,
	],
	make = [
		*worldbuilder.kbuild_make,
		"V=1",
		"install",
		*cross_tools_cc,
	],
)

util_linux = worldbuilder.Submodule("util-linux",
	version		= "2.29.2",
	url		= "https://www.kernel.org/pub/linux/utils/util-linux/v%(major)s.%(minor)s/util-linux-%(version)s.tar.xz",
	tarhash		= "accea4d678209f97f634f40a93b7e9fcad5915d1f4749f6c47bee6bf110fe8e3",
	depends		= [ linux, libgcc ],
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
		*cross_tools_cc,
	],
	make = [ "make", "install", "V=1" ],
)

zlib = worldbuilder.Submodule('zlib',
	depends = [ musl ],
	version = '1.2.11',
	url = 'https://www.zlib.net/zlib-%(version)s.tar.gz',
	tarhash = 'c3e5e9fdd5004dcb542feda5ee4f0ff0744628baf8ed2dd5d66f8ca1197cb1a1',
	configure = [
		worldbuilder.configure_cmd,
		"--prefix=%(install_dir)s",
		*cross_tools_cc,
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
	depends = [ libgcc ],
	configure = [
		worldbuilder.configure_cmd,
		"--prefix=%(install_dir)s",
		"--host", 'x86_64-linux-gnu', #'i386-elf-linux',
		"--target", 'x86_64',
		"--without-lzma",
		*cross_tools_cc,
	],
	make = [ "make", "install" ],
	bin_dir = 'sbin',
)

pciutils = worldbuilder.Submodule("pciutils",
	depends = [ libgcc, linux ],
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
		*cross_tools_cc,
		"CFLAGS=-fpic -I%(linux.out_dir)s/usr/include",
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
