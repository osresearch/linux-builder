all: init
init: init.c
	$(CC) -O3 -W -Wall -o $@ $<

world:
	+./helloworld.py
heads:
	+./heads-builder.py

jump:
	+./jump-builder.py
