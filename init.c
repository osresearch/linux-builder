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
#include <unistd.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <sys/mount.h>
#include <fcntl.h>

int main(void)
{
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

	int fd = open("/dev/console", O_RDWR);
	if (fd >= 0)
	{
		dup2(fd, 0);
		dup2(fd, 1);
		dup2(fd, 2);
	}

	fd = open("/args", O_RDONLY);
	if (fd < 0)
	{
		fprintf(stderr, "/args not found; not sure what to do!\n");
		return -1;
	}

	char args[4096];
	ssize_t len = read(fd, args, sizeof(args));
	//fprintf(stderr, "init: read %zu bytes\n", len);
	if (len < 0)
	{
		perror("/args");
		return -1;
	}

	char *argv[64] = {};
	int argc = 0;

	argv[argc++] = args;

	fprintf(stderr, "init: execv('%s'", argv[0]);

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
	execv(argv[0], argv);

	printf("EXEC FAILED. We're toast\n");
	return -1;
}
