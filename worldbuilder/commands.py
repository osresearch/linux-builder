# Common comands for different build systems

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
# these are applied in reverse order?
prefix_map = "-gno-record-gcc-switches" \
	+ " -Wl,--build-id=none" \
	+ " -ffile-prefix-map=%(top_dir)s/out=/build" \
	+ " -ffile-prefix-map=%(top_dir)s/src=/src" \
	+ " -ffile-prefix-map=%(install_dir)s=/" \

#	+ " -ffile-prefix-map=%(src_dir)s=/src/%(name)s-%(version)s" \
#	+ " -ffile-prefix-map=%(out_dir)s=/build" \

# Some broken configure scripts ignore the `--disable-rpath`, so this
# forcibly rewrites their libtool in place to avoid it.
fix_libtool = [
	'sed',
	'-i',
	#'s/hardcode_into_libs=yes/hardcode_into_libs=no/g',
	's/^hardcode_libdir_flag_spec=.*$/hardcode_libdir_flag_spec="-D__LIBTOOL_IS_A_FOOL__"/',
	"%(src_dir)s/configure",
]

delete_la = [ "find", "%(install_dir)s", "-name", "*.la", "-exec", "rm", "{}", ";" ]

strip_libs = [ "find", "%(lib_dir)s", "-name", "*.so", "-a", "-type", "f", "-exec", "strip", "{}", ";" ]

