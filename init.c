/*
 * tinyinit - finish kernel setup and get out of the way.
 *
 * Setup a few directories, mount a few filesystems,
 * and then exec the real application.
 *
 * By writing this as a small C program it avoids the need
 * to bring in bash and most of coreutils for smaller
 * unikernel images.
 */
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <sys/mount.h>
#include <fcntl.h>
#include <glob.h>
#include <sys/types.h>
#include <sys/wait.h>

static int forkit(const char * filename)
{
	int fd = open(filename, O_RDONLY);
	if (fd < 0)
	{
		fprintf(stderr, "%s not found; not sure what to do!\n", filename);
		return -1;
	}

	char args[4096];
	ssize_t len = read(fd, args, sizeof(args));
	//fprintf(stderr, "init: read %zu bytes\n", len);
	if (len < 0)
	{
		perror(filename);
		return -1;
	}

	char *argv[64] = {};
	int argc = 0;

	argv[argc++] = args;

	fprintf(stderr, "%s: execv('%s'", filename, argv[0]);

	// stop before the end of the argument data
	for(int offset = 0 ; offset < len-1 ; offset++)
	{
		if (args[offset] != '\0')
			continue;

		char * arg = &args[offset+1];
		argv[argc++] = arg;

		fprintf(stderr, ",'%s'", arg);
	}

	// terminate the list
	argv[argc] = NULL;
	fprintf(stderr, ")\n");

	// invoke it and hope for the best!
	int pid = vfork();
	if (pid == 0)
	{
		execv(argv[0], argv);
		exit(-1);
	}

	return 0;
}

int main(void)
{
	// these should already exist, but just in case
	fprintf(stderr, "init: creating directories\n");
	mkdir("/root", 0755);
	mkdir("/proc", 0755);
	mkdir("/sys", 0755);
	mkdir("/tmp", 0755);
	mkdir("/dev", 0755);
	mkdir("/run", 0755);
	mkdir("/var", 0755);

	fprintf(stderr, "init: mounting filesystems\n");
	mount("none", "/proc", "proc", 0, "");
	mount("none", "/dev", "devtmpfs", 0, "");
	mount("none", "/sys", "sysfs", 0, "");
	mount("none", "/sys/kernel/security", "securityfs", 0, "");

	// we do not need stdin
	close(0);

	int fd = open("/dev/console", O_RDWR);
	if (fd >= 0)
	{
		dup2(fd, 1);
		dup2(fd, 2);
	}

	glob_t globbuf;
	int rc = glob("/init.d/*", 0, NULL, &globbuf);
	const int matches = globbuf.gl_pathc;
	if (rc != 0 || matches == 0)
	{
		fprintf(stderr, "init: no programs to run? we're done here\n");
		return -1;
	}

	fprintf(stderr, "init: %d startup items found\n", matches);
	for(int i = 0 ; i < matches ; i++)
	{
		if (forkit(globbuf.gl_pathv[i]) == 0)
			continue;
		fprintf(stderr, "init: failed! we're done here\n");
		return -1;
	}

	globfree(&globbuf);

	// now just reap children
	while(1)
	{
		int status;
		pid_t pid = wait(&status);
		fprintf(stderr, "init: pid %d exited status %08x\n", (int) pid, status);
	}
}
