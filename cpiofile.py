#!/usr/bin/env python3
# Creates an in-memory, reproducible cpio file 
# Populate an initrd directory with programs and their libraries
# https://www.kernel.org/doc/Documentation/early-userspace/buffer-format.txt
import os
import re
import subprocess
import sys
from tempfile import NamedTemporaryFile
from enum import IntEnum


def align(data, b):
	if len(data) % b != 0:
		data += bytes(b - len(data) % b)
	return data

def cpio_hex(x):
	return ("%08x" % (x)).encode('utf-8')


# mode includes
class MODE(IntEnum):
	S_ISUID  = 0o4000   # Set uid
	S_ISGID  = 0o2000   # Set gid
	S_ISVTX  = 0o1000   # Save text (sticky bit)
	S_ISDIR  = 0o40000  # Directory
	S_ISFIFO = 0o10000  # FIFO
	S_ISREG  = 0o100000 # Regular file
	S_ISLNK  = 0o120000 # Symbolic link
	S_ISBLK  = 0o60000  # Block special file
	S_ISCHR  = 0o20000  # Character special file
	S_ISSOCK = 0o140000 # Socket

class CPIOFile:
	def __init__(self, filename, data, uid=0, gid=0, major=None, minor=None, mode=0o777):
		# remove any duplicate / and strip the leading /
		self.filename = filename
		self.filename = re.sub(r'//*/', '/', self.filename)
		self.filename = re.sub(r'^/*', '', self.filename)

		self.data = data
		self.uid = uid
		self.gid = gid

		# if major/minor are not set, then this is a regular file
		if mode & (MODE.S_ISDIR | MODE.S_ISBLK | MODE.S_ISCHR) == 0:
			mode |= MODE.S_ISREG
		self.mode = mode

		self.major = major
		self.minor = minor

		if self.major is None:
			self.major = 0
			self.minor = 0

# returns a blob formatted as a newc cpio entry
#       Field name    Field size	 Meaning
#       c_magic	      6 bytes		 The string "070701" or "070702"
#       c_ino	      8 bytes		 File inode number (always 0)
#       c_mode	      8 bytes		 File mode and permissions
#       c_uid	      8 bytes		 File uid
#       c_gid	      8 bytes		 File gid
#       c_nlink	      8 bytes		 Number of links (always 0)
#       c_mtime	      8 bytes		 Modification time (always 0)
#       c_filesize    8 bytes		 Size of data field
#       c_maj	      8 bytes		 Major part of file device number (always 0)
#       c_min	      8 bytes		 Minor part of file device number (always 0)
#       c_rmaj	      8 bytes		 Major part of device node reference
#       c_rmin	      8 bytes		 Minor part of device node reference
#       c_namesize    8 bytes		 Length of filename, including final \0
#       c_chksum      8 bytes		 Checksum of data field if c_magic is 070702;
				 #       otherwise zero
# followed by namesize bytes of name (padded to be a multiple of 4)
# followed dby filesize bytes of file (padded to be a multiple of 4)
#
	def tobytes(self):
		name = self.filename.encode('utf-8') + b'\0'

		name_len = len(name) # including nul terminator
		data_len = len(self.data) # as is

		# pad filename so that it ends up aligned on a
		# four byte block. HOWEVER, it starts offset by 2,
		# so there is some weirdness here.  note that the
		# data is *NOT* padded here, since it will be
		# aligned during the final write out
		if (name_len+2) % 4 != 0:
			name += bytes(4 - ((name_len+2) % 4))


		return b'' \
			+ b'070701' \
			+ b'00000000' \
			+ cpio_hex(self.mode) \
			+ cpio_hex(self.uid) \
			+ cpio_hex(self.gid) \
			+ b'00000000' \
			+ b'00000000' \
			+ cpio_hex(data_len) \
			+ b'00000000' \
			+ b'00000000' \
			+ cpio_hex(self.major) \
			+ cpio_hex(self.minor) \
			+ cpio_hex(name_len) \
			+ b'00000000' \
			+ name \
			+ self.data

class CPIO:
	def __init__(self):
		self.files = {}
		self.verbose = 0

	def normalize(self, filename):
		isdir = filename[-1] == '/'

		filename = os.path.normpath(filename)
		if filename[0] == '/':
			filename = filename[1:]

		return (filename, isdir)


	def mkdir(self, dirname, mode = 0o777):
		(dirname, isdir) = self.normalize(dirname)

		path = ''
		for subdir in re.split(r'/+', dirname):
			if path == '':
				path = subdir
			else:
				path += '/' + subdir
			if path in self.files:
				continue
			if path == '':
				continue

			self.files[path] = CPIOFile(path, b'', mode = mode | MODE.S_ISDIR)

	def isdir(self, path):
		(path,isdir) = self.normalize(path)

		if not path in self.files:
			return False
		return (self.files[path].mode & Mode.S_ISDIR) != 0

	def add(self,filename,data=None,mode=0o655):
		(filename,isdir) = self.normalize(filename)

		if isdir or self.isdir(dst):
			# destination directory
			fname = os.path.split(src)[1]
			dst = os.path.join(dst, fname)

		if dst in self.files:
			print("%s -> %s: destination already exists!" % (src,dst), file=sys.stderr)

		# read in the data from the file if not provided
		if data is None:
			mode = os.stat(src).st_mode
			with open(src, "rb") as datafile:
				data = datafile.read()

		# if the dest path does not already exist, be sure to make it
		self.mkdir(os.path.split(dst)[0])

		if self.verbose:
			print("add %s -> %s (%d bytes)" % (src, dst, len(data)))
#		if depsfile:
#			print("\t" + src + " \\", file=depsfile)

		self.files[dst] = CPIOFile(dst, data, mode=mode)

	def mknod(self, filename, devtype, major, minor):
		(filename,isdir) = self.normalize(filename)
		mode = 0o666
		if devtype == 'b':
			mode |= MODE.S_ISBLK
		elif devtype == 'c':
			mode |= MODE.S_ISCHR
		else:
			throw("bad dev type")

		# if the dest path does not already exist, be sure to make it
		self.mkdir(os.path.split(filename)[0])

		major = int(major)
		minor = int(minor)

		if self.verbose:
			print("mknod %s %s %d %d" % (filename, devtype, major, minor))

		self.files[filename] = CPIOFile(
			filename,
			b'',
			mode = mode,
			major = major,
			minor = minor)

	def symlink(self, filename, dest):
		(filename,isdir) = self.normalize(filename)

		if self.verbose:
			print("symlink %s -> %s" % (filename, dest))

		self.mkdir(os.path.split(filename)[0])
		self.files[filename] = CPIOFile(
			filename,
			dest.encode('utf-8'),
			mode = 0o777 | MODE.S_ISLNK)

	def tobytes(self, compressed=False):
		image = b''
		for dst in sorted(self.files):
			print(dst)
			f = self.files[dst]

			# align before starting the next file
			image = align(image, 4)

			image += f.tobytes()

		# align before starting the trailer file
		image = align(image, 4)
		image += CPIOFile("TRAILER!!!", b'', mode=0).tobytes()

		if compressed:
			# write to a temp file first
			old_len = len(image)

			with NamedTemporaryFile() as tmp:
				tmp.write(image)
				tmp.flush()
				sub = subprocess.run([
					"xz",
					"--check=crc32",
					"--lzma2=dict=256KiB",
					"--threads=0",
					"--stdout",
					tmp.name
				], capture_output=True)
				if sub.returncode != 0:
					#print(sub.stderr, file=sys.stderr)
					return None
				image = sub.stdout

		# pad compressed data to a full block size to make linux
		# happy if this is ever concatenated with another initrd
		image = align(image, 512)
		return image

