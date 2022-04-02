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
 
 

----

# worldbuilder

`worldbuilder` uses Python3 (> 3.9), make and patch,
various autotools need flex/bison/m4,
`json-c` uses cmake,
`openssl` uses some Perl packages.
linux kernel wants rsync, bc, lz4, and host-side tools need openssl

Fedora requirements:
```
dnf install \
  make patch gcc g++ python3 git \
  texinfo \
  bzip2 xz \
  cmake \
  perl-FindBin perl-File-Compare \
  bc lz4 openssl-devel \
  flex bison m4 elfutils-libelf-devel
```

Debian requirements:
```
apt install \
  make patch gcc g++ python3 git \
  texinfo \
  bzip2 xz-utils \
  cmake \
  bc lz4 libssl-dev flex bison m4 rsync libelf-dev
```

```
git clone https://github.com/osresearch/linux-builder
cd linux-builder
make -j64 heads
```


TODO: can we remove the texinfo requirement?
TODO: can we reduce the @development-tools to just gcc?

