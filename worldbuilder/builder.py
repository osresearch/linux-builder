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

		del self.waiting[mod.name]
		self.building[mod.name] = mod
		#self.report()

		try:
			start_time = time.time()
			if mod.installed:
				# nothing to do!
				pass
			elif mod.install():
				self.installed[mod.name] = mod
				print(now(), "DONE    " + mod.name + " (%d seconds)" % (time.time() - start_time))
			else:
				self.failed[mod.name] = mod
				print(now(), "FAILED! " + mod.name + ": logs are in " + relative(mod.out_dir), file=sys.stderr)

		except Exception as e:
			print(now(), "FAILED! " + mod.name + ": logs are in " + relative(mod.out_dir), file=sys.stderr)
			print(traceback.format_exc(), file=sys.stderr)
			self.failed[mod.name] = mod

		del self.building[mod.name]
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
						die(dep + ": not found? referenced by " + mod.name)
					dep = global_mods[dep]
				depends.append(dep)

			mod.depends = depends
					
			ts.add(mod, *mod.depends)
			for dep in mod.depends:
				self.mods.append(dep)

		ordered_mods = [*ts.static_order()]
		print([x.name for x in ordered_mods])

		for mod in ordered_mods:
			mod.install(check=True)
			if mod.installed:
				self.installed[mod.name] = mod
			else:
				self.waiting[mod.name] = mod
			print(mod.state() + " " + mod.name + ": " + relative(mod.out_dir))

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
					if not dep.name in self.installed:
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



if __name__ == "__main__":
	pass
