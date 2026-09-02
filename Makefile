.PHONY: install test

DESTDIR ?=
BINDIR ?= /usr/bin
OPENRC_INITDDIR ?= /etc/init.d
OPENRC_CONFDIR ?= /etc/conf.d

install:
	install -D -m 0700 "t2saild" "$(DESTDIR)$(BINDIR)/t2saild"
	install -D -m 0755 "t2saild.initd" "$(DESTDIR)$(OPENRC_INITDDIR)/t2saild"
	install -D -m 0644 "t2saild.confd" "$(DESTDIR)$(OPENRC_CONFDIR)/t2saild"

test:
	python3 -m unittest discover -s tests -p 'test_*.py'
