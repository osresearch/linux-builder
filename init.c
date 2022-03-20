/*
 * Setup a few directories, mount a few filesystems, and then exec the real application.
 */
#include <stdio.h>
#include <unistd.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <sys/mount.h>
#include <fcntl.h>

/*
#!/bin/bash
mkdir -p /proc /sys /tmp /dev /etc /root /run /boot /var
mount -t proc none /proc
mount -t devtmpfs none /dev
mount -t sysfs none /sys
mount -t securityfs none /sys/kernel/security
*/
int main(int argc, char * argv[] )
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
	dup2(fd, 0);
	dup2(fd, 1);
	dup2(fd, 2);

	fprintf(stderr, "init: exec sshd\n");
	mkdir("/run/sshd", 0755);
	execl("/bin/sshd", "/bin/sshd", "-D", "-e", NULL);

	printf("EXEC FAILED. We're toast\n");
	return -1;
}


/*
mkdir -p /run/sshd # /run/jump
#chown -R jump /run/jump

#if [ -x /bin/setsid ]; then
#	exec /bin/setsid -c /bin/bash
#fi

while true ; do
	/bin/sshd -D -e
	echo "--- sshd exited ---"
done

export PS1='\w# '
if [ -x /bin/setsid ]; then
	exec /bin/setsid -c /bin/bash
fi


# fall back to a normal shell with no job control
exec /bin/bash
*/
