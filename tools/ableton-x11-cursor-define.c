#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <X11/Xlib.h>
#include <X11/cursorfont.h>

static void usage(const char *argv0) {
  fprintf(stderr, "usage: %s define|undefine <window-id> [cursor-name]\n", argv0);
}

static unsigned int cursor_shape(const char *name) {
  if (name == NULL || strcmp(name, "left_ptr") == 0) return XC_left_ptr;
  if (strcmp(name, "arrow") == 0) return XC_left_ptr;
  if (strcmp(name, "crosshair") == 0) return XC_crosshair;
  if (strcmp(name, "xterm") == 0) return XC_xterm;
  return XC_left_ptr;
}

int main(int argc, char **argv) {
  if (argc < 3) {
    usage(argv[0]);
    return 2;
  }

  const char *action = argv[1];
  char *end = NULL;
  Window win = (Window)strtoul(argv[2], &end, 0);
  if (end == argv[2] || win == 0) {
    fprintf(stderr, "invalid window id: %s\n", argv[2]);
    return 2;
  }

  Display *dpy = XOpenDisplay(NULL);
  if (dpy == NULL) {
    fprintf(stderr, "cannot open DISPLAY\n");
    return 1;
  }

  int rc = 0;
  if (strcmp(action, "define") == 0) {
    Cursor cursor = XCreateFontCursor(dpy, cursor_shape(argc >= 4 ? argv[3] : "left_ptr"));
    if (cursor == None) {
      fprintf(stderr, "cannot create cursor\n");
      XCloseDisplay(dpy);
      return 1;
    }
    XDefineCursor(dpy, win, cursor);
    XFlush(dpy);
    XFreeCursor(dpy, cursor);
  } else if (strcmp(action, "undefine") == 0) {
    XUndefineCursor(dpy, win);
    XFlush(dpy);
  } else {
    usage(argv[0]);
    rc = 2;
  }

  XCloseDisplay(dpy);
  return rc;
}
