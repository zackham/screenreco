CC = gcc
CFLAGS = -Wall -O2 $(shell pkg-config --cflags wayland-client wayland-protocols gtk+-3.0)
WAYLAND_LIBS = $(shell pkg-config --libs wayland-client) -lrt -lm
GTK_LIBS = $(shell pkg-config --libs gtk+-3.0)

WAYLAND_SCANNER = wayland-scanner
WAYLAND_PROTOCOLS_DIR = /usr/share/wayland-protocols
WLR_PROTOCOLS_DIR = /usr/share/wlr-protocols

PROTOCOL_SRCS = xdg-shell-protocol.c wlr-layer-shell-unstable-v1-protocol.c
PROTOCOL_HDRS = xdg-shell-client-protocol.h wlr-layer-shell-unstable-v1-client-protocol.h

TARGETS = border-overlay button-window

PREFIX ?= /usr/local
BINDIR = $(PREFIX)/bin

all: protocols $(TARGETS)

protocols: $(PROTOCOL_HDRS) $(PROTOCOL_SRCS)

xdg-shell-client-protocol.h:
	$(WAYLAND_SCANNER) client-header \
		$(WAYLAND_PROTOCOLS_DIR)/stable/xdg-shell/xdg-shell.xml $@

xdg-shell-protocol.c:
	$(WAYLAND_SCANNER) private-code \
		$(WAYLAND_PROTOCOLS_DIR)/stable/xdg-shell/xdg-shell.xml $@

wlr-layer-shell-unstable-v1-client-protocol.h:
	$(WAYLAND_SCANNER) client-header \
		$(WLR_PROTOCOLS_DIR)/unstable/wlr-layer-shell-unstable-v1.xml $@

wlr-layer-shell-unstable-v1-protocol.c:
	$(WAYLAND_SCANNER) private-code \
		$(WLR_PROTOCOLS_DIR)/unstable/wlr-layer-shell-unstable-v1.xml $@

border-overlay: src/border-overlay.c $(PROTOCOL_SRCS)
	$(CC) $(CFLAGS) $< $(PROTOCOL_SRCS) -o $@ $(WAYLAND_LIBS)

button-window: src/button-window.c
	$(CC) $(CFLAGS) $< -o $@ $(GTK_LIBS)

install: all
	install -Dm755 border-overlay $(DESTDIR)$(BINDIR)/screenreco-border
	install -Dm755 button-window $(DESTDIR)$(BINDIR)/screenreco-buttons
	install -Dm755 scripts/screenreco $(DESTDIR)$(BINDIR)/screenreco

uninstall:
	rm -f $(DESTDIR)$(BINDIR)/screenreco-border
	rm -f $(DESTDIR)$(BINDIR)/screenreco-buttons
	rm -f $(DESTDIR)$(BINDIR)/screenreco

clean:
	rm -f $(TARGETS) $(PROTOCOL_SRCS) $(PROTOCOL_HDRS)

.PHONY: all protocols install uninstall clean