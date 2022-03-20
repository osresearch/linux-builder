all: init
init: init.c
	$(CC) -O3 -W -Wall -o $@ $<
