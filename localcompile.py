# Use the local gcc instead of building a cross compiler
#
import worldbuilder

target_arch = "x86_64-linux-gnu"

binutils = worldbuilder.Submodule("binutils",
	version = "usrbin",
	install_dir = "/usr",
)

gcc = worldbuilder.Submodule("gcc",
	version = "usrbin",
	install_dir = "/usr/bin",
)


cross = "/usr/bin/"

# these are for gcc's special "FOO_FOR_TARGET" instead of "FOO"
gcc_cross_tools = [x.upper() + "_FOR_TARGET=" + cross + x
	for x in "ar as ld nm ranlib objcopy objdump strip".split(" ")]

cross_tools_nocc = [x.upper() + "=" + cross + x
	for x in "ar as ld nm ranlib objcopy objdump strip".split(" ")]

cross_tools = [
	"CC=gcc",
	"CXX=g++",
	*cross_tools_nocc,
]
