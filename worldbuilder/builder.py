# Building envrionment for a set of submodules
# TODO: have this drive the set of modules and name resolution

from worldbuilder.util import *
from worldbuilder.submodule import global_mods # TODO remove this

class Builder:
	def __init__(self, mods):
		self.mods = mods
		self.failed = False
		self.reset()

	def reset(self):
		self.waiting = {}
		self.building = {}
		self.installed = {}
		self.failed = {}

	def report(self):
		wait_list = ','.join(self.waiting)
		building_list = ','.join(self.building)
		installed_list = ','.join(self.installed)
		failed_list = ','.join(self.failed)
		print(now(),
			"building=[" + building_list
			+ "] waiting=[" +  wait_list
			+ "] installed=[" + installed_list
			+ "]"
		)
		if len(self.failed) > 0:
			print(now(), "failed=" + failed_list, file=sys.stderr)
			return False

		return True

	def _build_thread(self, mod):

		del self.waiting[mod.fullname]
		self.building[mod.fullname] = mod
		#self.report()

		try:
			start_time = time.time()
			if mod.installed:
				# nothing to do!
				pass
			elif mod.install():
				self.installed[mod.fullname] = mod
				print(now(), "DONE    " + mod.fullname + " (%d seconds)" % (time.time() - start_time))
			else:
				self.failed[mod.fullname] = mod
				print(now(), "FAILED! " + mod.fullname + ": logs are in " + relative(mod.last_logfile), file=sys.stderr)
				for line in readfile(mod.last_logfile).split(b'\n')[-20:-1]:
					print(mod.fullname + ": " + line.decode('utf-8'), file=sys.stderr)

		except Exception as e:
			print(now(), "FAILED! " + mod.fullname + ": logs are in " + relative(mod.last_logfile), file=sys.stderr)
			print(traceback.format_exc(), file=sys.stderr)
			self.failed[mod.fullname] = mod
			for line in readfile(mod.last_logfile).split(b'\n')[-20:-1]:
				print(mod.fullname + ": " + line.decode('utf-8'), file=sys.stderr)

		del self.building[mod.fullname]
		#self.report()

	def check(self):
		# walk all the dependencies to ensure consistency of inputs
		self.reset()

		# build the transitive closure of all modules that are
		# required, and sort them into a build order so that
		# dependencies are maintained
		ts = TopologicalSorter()

		for mod in self.mods:
			# lookup any strings-based dependencies
			depends = []
			if type(mod) == str:
				if not mod in global_mods:
					die(mod + ": not found?")
				mod = global_mods[mod]

			for dep in mod.depends:
				if type(dep) == str:
					if not dep in global_mods:
						die(dep + ": not found? referenced by " + mod.fullname)
					dep = global_mods[dep]
				depends.append(dep)

			mod.depends = depends
					
			ts.add(mod, *mod.depends)
			for dep in mod.depends:
				self.mods.append(dep)

		self.ordered_mods = [*ts.static_order()]
		print([x.fullname for x in self.ordered_mods])

		for mod in self.ordered_mods:
			mod.update_hashes()
			mod.install(check=True)
			if mod.installed:
				self.installed[mod.fullname] = mod
			else:
				self.waiting[mod.fullname] = mod
			print(mod.state() + " " + mod.fullname + ": " + relative(mod.out_dir))

		self.report()
#		for modname, mod in self.built.items():
#			print(mod.state() + " " + mod.name + ": " + mod.out_dir)
#		for modname, mod in self.waiting.items():
#			print(mod.state() + " " + mod.name + ": " + mod.out_dir)


	def build_all(self):
		if len(self.waiting) == 0:
			self.check()

		while True:
			if len(self.waiting) == 0 or len(self.failed) != 0:
				# no mods left, no builders? we're done!
				if len(self.building) == 0:
					return self.report()

				# no mods left, and builds are in process,
				# wait for completions. is there a better way?
				sleep(1)
				continue

			for name in list(self.waiting):
				mod = self.waiting[name]
				ready = True
				for dep in mod.depends:
					if not dep.fullname in self.installed:
						ready = False

				if not ready:
					# oh well, try the next one
					continue

				# it is time to build this mod!
				mod.building = True
				Thread(target = self._build_thread, args=(mod,)).start()

			# processed the list of waiting ones sleep for a bit and
			# try again in a little while
			sleep(0.1)

	def cache_create(self, cache_dir):
		self.check()
		fail = False

		for dep in self.ordered_mods:
			if not dep.cacheable:
				continue
			if not dep.installed:
				print(dep.fullname + ": not ready to build cache", file=sys.stderr)
				fail = True
				continue
		if fail:
			return False

		mkdir(cache_dir)

		for dep in self.ordered_mods:
			if not dep.cacheable:
				continue
			dep.cache_create(cache_dir)

		

if __name__ == "__main__":
	pass
