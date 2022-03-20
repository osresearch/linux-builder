# Linux Appliance Builder

These scripts are useful for building Linux appliances or firmware images that
do not require a full user-land and have a custom kernel configuration with
optional patches.  It also has a script to build a unified kernel image with
the initrd and command line in a signed EFI application.

## linux-builder

To use, start with a `linux.config` file and run:

```
linux-builder \
    -v \
    --version 5.4.117 \
    --config linux.config
```

This will download Linux 5.4.117 from kernel.org, (todo verify it),
unpack it, apply any patches, generate the `.config` file for it
and then invoke a recursive `make` to build it in `./build`.

## initrd-builder

For the kernel's initial ramdisk cpio file, you might be able to just
list the binaries that you want to include and then:

```
initrd-builder \
    -v \
    -o build/initrd.cpio.xz \
    base-initrd.conf \
    my-initrd.conf
```

## unify-kernel

```
unify-kernel \
  --kernel build/vmlinuz-linux \
  --initrd build/initrd.cpio.xz \
  --commandline commandline.txt \
  -o build/bootx64.efi
```
 
