# Build a GCC cross compiler
#
import worldbuilder

target_arch = "x86_64-linux-musl"
target_arch32 = "i386-linux-musl"

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

binutils_src = worldbuilder.Submodule("binutils_src",
	depends = [ mpc ],
	version = "2.38",
	url = "https://ftp.gnu.org/gnu/binutils/binutils-%(version)s.tar.xz",
	tarhash = 'e316477a914f567eccc34d5d29785b8b0f5a10208d36bbacedcc39048ecfe024',
	configure = [ "true" ],
	make = [ "true" ],
)

binutils = worldbuilder.Submodule("binutils",
	depends = [ binutils_src ],
	version = binutils_src.version,
	configure = [
		"%(binutils_src.src_dir)s/configure",
		"--target=" + target_arch,
		"--prefix=%(install_dir)s",
		"--with-mpc=%(mpc.install_dir)s",
		"--disable-nls",
	],
	make = [
		[ "make" ],
		[ "make", "install" ],
	],
)

binutils32 = worldbuilder.Submodule("binutils32",
	depends = [ binutils_src ],
	version = binutils_src.version,
	configure = [
		"%(binutils_src.src_dir)s/configure",
		"--target=" + target_arch32,
		"--prefix=%(install_dir)s",
		"--with-mpc=%(mpc.install_dir)s",
		"--disable-nls",
	],
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

cross = "%(binutils.install_dir)s/bin/" + target_arch + "-"
cross32 = "%(binutils32.install_dir)s/bin/" + target_arch32 + "-"

# these are for gcc's special "FOO_FOR_TARGET" instead of "FOO"
gcc_cross_tools = [x.upper() + "_FOR_TARGET=" + cross + x
	for x in "ar as ld nm ranlib objcopy objdump strip".split(" ")]
gcc_cross32_tools = [x.upper() + "_FOR_TARGET=" + cross32 + x
	for x in "ar as ld nm ranlib objcopy objdump strip".split(" ")]

cross_tools_nocc = [x.upper() + "=" + cross + x
	for x in "ar as ld nm ranlib objcopy objdump strip".split(" ")]
cross_tools32_nocc = [x.upper() + "=" + cross32 + x
	for x in "ar as ld nm ranlib objcopy objdump strip".split(" ")]

cross_tools = [
	"CC=%(musl.install_dir)s/bin/musl-gcc",
	"CXX=%(musl.install_dir)s/bin/musl-gcc",
	*cross_tools_nocc,
]

cross_tools32 = [
	"CC=%(musl32.install_dir)s/bin/musl-gcc",
	"CXX=%(musl32.install_dir)s/bin/musl-gcc",
	*cross_tools32_nocc,
]

gcc_version = "11.2.0"

# this fakes the install into the binutils directory to avoid issues later
crossgcc_src = worldbuilder.Submodule("crossgcc_src",
	depends = [ mpc, mpfr, gmp ],
	url = "https://ftp.gnu.org/gnu/gcc/gcc-%(version)s/gcc-%(version)s.tar.xz",
	#version = "9.4.0",
	#tarhash = 'c95da32f440378d7751dd95533186f7fc05ceb4fb65eb5b85234e6299eb9838e',
	version = gcc_version,
	tarhash = 'd08edc536b54c372a1010ff6619dd274c0f1603aa49212ba20f7aa2cda36fa8b',
	configure = [ "true" ],
	make = [ "true" ],
)

# submodule must also provide `--target=....`
crossgcc_configure_cmds = [
	"%(crossgcc_src.src_dir)s/configure",
	"--with-mpc=%(mpc.install_dir)s",
	"--with-gmp=%(gmp.install_dir)s",
	"--with-mpfr=%(mpfr.install_dir)s",
	"--enable-languages=c",
	"--without-headers",
	"--with-newlib",
	"--disable-nls",
	"--disable-plugin",
	"--disable-lto",
	"--disable-multilib",
	"--disable-decimal-float",
	"--disable-libmudflap",
	"--disable-libssp",
	"--disable-libgomp",
	"--disable-libquadmath",
]

crossgcc = worldbuilder.Submodule("crossgcc",
	version = crossgcc_src.version,
	depends = [ crossgcc_src, binutils ],
	configure = [
		*crossgcc_configure_cmds,
		"--target", target_arch,
		"--prefix=%(binutils.install_dir)s", # note output!
		"--with-build-time-tools=%(binutils.install_dir)s/bin",
		*gcc_cross_tools,
	],
	make = [
		[ "make", "all-gcc" ], 
		[ "make", "install-gcc" ],
	],
)

crossgcc32 = worldbuilder.Submodule("crossgcc32",
	version = crossgcc_src.version,
	depends = [ crossgcc_src, binutils32 ],
	configure = [
		*crossgcc_configure_cmds,
		"--target=" + target_arch32,
		"--prefix=%(binutils32.install_dir)s", # note output!
		"--with-build-time-tools=%(binutils32.install_dir)s/bin",
		*gcc_cross32_tools,
	],
	make = [
		[ "make", "all-gcc" ], 
		[ "make", "install-gcc" ],
	],
)

musl_src = worldbuilder.Submodule("musl_src",
	version = "1.2.2",
	url = "https://musl.libc.org/releases/musl-%(version)s.tar.gz",
	tarhash = '9b969322012d796dc23dda27a35866034fa67d8fb67e0e2c45c913c3d43219dd',
	patches = [ "patches/musl-0000-fastmath.patch" ],

	# source only; don't build anything
	configure = [ "true" ],
	make = [ "true" ],
)

musl_configure_cmds = [
	"%(musl_src.src_dir)s/configure",
	"--prefix=%(install_dir)s",
	"--syslibdir=%(install_dir)s/lib",
	"--enable-wrapper=gcc",
	"DESTDIR=%(install_dir)s",
]

musl = worldbuilder.Submodule("musl",
	depends = [ crossgcc, musl_src ],
	version = musl_src.version,
	configure = [
		*musl_configure_cmds,
		"--target=" + target_arch,
		"CC=" + cross + "gcc",
		"CFLAGS=-ffast-math -O3", # avoid libgcc circular math dependency
		*cross_tools_nocc,
	],
	make = [
		"make",
		"install",
		"LDSO_PATHNAME=/lib/ld-musl-x86_64.so.1",
	],
)

musl32 = worldbuilder.Submodule("musl32",
	depends = [ crossgcc32, musl_src ],
	version = musl_src.version,
	configure = [
		*musl_configure_cmds,
		"--target=" + target_arch32,
		"CC=" + cross32 + "gcc",
		"CFLAGS=-ffast-math -O3", # avoid libgcc circular math dependency
		"LDFLAGS=-Wl,--unresolved-symbols=ignore-in-object-files", # also libgcc issue
		*cross_tools32_nocc,
	],
	make = [
		"make",
		"install",
		"LDSO_PATHNAME=/lib/ld-musl-i386.so.1",
	],
)

# pick up in the cross gcc target once musl has been built so that
# libgcc can use the musl headers to build. This is a fake package
# with no source; it simply runs another command in the crossgcc tree
# to build the libgcc library once musl headers are available
# it is named gcc to be easier to refer to
gcc = worldbuilder.Submodule("gcc",
	version = crossgcc_src.version,
	depends = [ crossgcc, musl ],
	configure = [ "true" ],
	make = [ [
			"make",
			"-C", "%(crossgcc.out_dir)s",
			"all-target-libgcc",
			"CFLAGS_FOR_TARGET=-I%(musl.install_dir)s/include -v -B%(musl.install_dir)s/lib",
			*gcc_cross_tools,
		], [
			"make",
			"-C", "%(crossgcc.out_dir)s",
			"install-target-libgcc",
		],
	],
)

gcc32 = worldbuilder.Submodule("gcc32",
	version = crossgcc_src.version,
	depends = [ crossgcc32, musl32 ],
	configure = [ "true" ],
	make = [ [
			"make",
			"-C", "%(crossgcc32.out_dir)s",
			"all-target-libgcc",
			"CFLAGS_FOR_TARGET=-I%(musl32.install_dir)s/include -v -B%(musl32.install_dir)s/lib",
			*gcc_cross32_tools,
		], [
			"make",
			"-C", "%(crossgcc32.out_dir)s",
			"install-target-libgcc",
		],
	],
)

