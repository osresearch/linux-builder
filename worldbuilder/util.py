# utility functions for the worldbuilder classes
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

def now():
	return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())

zero_hash = '0' * 64
verbose = 0

def sha256hex(data):
	#print("hashing %d bytes" % (len(data)), data)
	if type(data) is str:
		data = data.encode('utf-8')
	return hashlib.sha256(data).hexdigest()

def extend(h, data):
	if h is None:
		h = zero_hash
	for datum in data:
		h = sha256hex(h + sha256hex(datum))
	return h

def system(*s, cwd=None, log=None):
	if not cwd:
		cwd = '.'
	if verbose > 2:
		print(cwd, s)

	if log:
		logfile = open(log, "a+")
		print("----- " + now() + " -----", file=logfile)
		print("cd " + os.path.abspath(cwd), file=logfile)
		print(*s, file=logfile)
		logfile.flush()
	else:
		logfile = None

	# do not close file descriptors, which will allow
	# communication from sub-make invocations to the make
	# that invoked us
	subprocess.run(s, cwd=cwd, check=True, close_fds=False, stdout=logfile, stderr=logfile)
	if logfile:
		logfile.close()

def die(*s):
	print(now(), *s, file=sys.stderr)
	exit(1)

def info(*s):
	if verbose > 0:
		print(now(), *s)

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

def relative(dirname):
	#abs_build = os.path.abspath(build_dir)
	return os.path.relpath(dirname)
