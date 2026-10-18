// Copyright (c) 2026. RECONSTRUCTED source, NOT historical E1 client.
// Android ARMv7 PIE helper run by LibMMBD's posix_spawn as Kodi UID.
// It MUST remain executable in Kodi's own native-library execution namespace.
// Socket protocol carries *only opaque bytes*, no argv or extra control frames.
#define _GNU_SOURCE
#include <sys/types.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <poll.h>
#include <fcntl.h>
#include <stddef.h>
#include <unistd.h>
#include <errno.h>
#include <signal.h>
#include <stdio.h>
#include <stdint.h>
#include <string.h>
#include <time.h>
#include <stdlib.h>

#define SOCKNAME "gazelle.mmbd.app.e1"
#define QSIZE 32768
#define MAX_HELPER_LIFETIME_SEC 10800
#define MAX_IDLE_SEC 600

struct queue { unsigned char buf[QSIZE]; size_t off, count; };
static long long now_sec(void) {
  struct timespec t;
  if (clock_gettime(CLOCK_MONOTONIC, &t)) return -1;
  return (long long)t.tv_sec;
}
static int nonblock(int fd) {
  int old = fcntl(fd, F_GETFL, 0);
  if (old < 0) return -1;
  return fcntl(fd, F_SETFL, old | O_NONBLOCK);
}
static int connect_broker(void) {
  struct sockaddr_un a;
  socklen_t n;
  int fd = socket(AF_UNIX, SOCK_STREAM | SOCK_CLOEXEC, 0);
  if (fd < 0) return -1;
  memset(&a, 0, sizeof a);
  a.sun_family = AF_UNIX;
#ifdef GAZELLE_HOST_TEST
  const char *name = "gazelle.mmbd.app.e1.rebuild-test";
#else
  const char *name = SOCKNAME;
#endif
  size_t len = strlen(name);
  if (len + 1 > sizeof(a.sun_path)) { close(fd); return -1; }
  a.sun_path[0] = '\0';
  memcpy(a.sun_path + 1, name, len);
  n = (socklen_t)(offsetof(struct sockaddr_un, sun_path) + len + 1);
  if (connect(fd, (struct sockaddr *)&a, n) < 0) { close(fd); return -1; }
  struct ucred cred;
  socklen_t sz = sizeof cred;
  if (getsockopt(fd, SOL_SOCKET, SO_PEERCRED, &cred, &sz) != 0 ||
      sz != sizeof cred ||
#ifdef GAZELLE_HOST_TEST
      cred.uid != getuid()
#else
      cred.uid != 0
#endif
     ) { close(fd); return -1; }
  return fd;
}
static int fill(struct queue *q, int fd, int *at_eof) {
  ssize_t n;
  if (*at_eof || q->count || q->off) return 0;
  n = read(fd, q->buf, sizeof q->buf);
  if (n > 0) { q->count = (size_t)n; return 1; }
  if (n == 0) { *at_eof=1; return 0; }
  if (errno == EINTR || errno == EAGAIN || errno == EWOULDBLOCK) return 0;
  return -1;
}
static int drain(struct queue *q, int fd) {
  if (!q->count) return 0;
  ssize_t n = write(fd, q->buf + q->off, q->count);
  if (n > 0) {
    q->off += (size_t)n;
    q->count -= (size_t)n;
    if (!q->count) q->off = 0;
    return 1;
  }
  if (n < 0 && (errno == EINTR || errno == EAGAIN ||
                errno == EWOULDBLOCK)) return 0;
  return -1;
}
int main(int argc, char **argv) {
  struct queue to_broker = {{0},0,0}, to_kodi = {{0},0,0};
  int stdin_eof=0, socket_eof=0, shutdown_sent=0, rc=1;
  long long start, progress;
  if (argc != 3 || strcmp(argv[1],"guiserver") != 0 ||
      strcmp(argv[2],"A0001+std") != 0) return 2;
  signal(SIGPIPE, SIG_IGN);
  int s=connect_broker();
  if (s<0) { fprintf(stderr, "MMBD_HELPER_CONNECT_FAILED\n"); return 3; }
  if (nonblock(STDIN_FILENO) || nonblock(STDOUT_FILENO) || nonblock(s)) {
    close(s); return 4;
  }
  start=now_sec(); progress=start;
  while (1) {
    long long t=now_sec();
    if (t<0 || start<0 || t-start>=MAX_HELPER_LIFETIME_SEC ||
        t-progress>=MAX_IDLE_SEC) break;
    if (socket_eof && to_kodi.count==0) { rc=0; break; }
    if (stdin_eof && to_broker.count==0 && !shutdown_sent) {
      if (shutdown(s,SHUT_WR) != 0 && errno != ENOTCONN) break;
      shutdown_sent=1;
    }
    struct pollfd fds[3]={{STDIN_FILENO,0,0},{s,0,0},{STDOUT_FILENO,0,0}};
    if (!stdin_eof && !to_broker.count) fds[0].events |= POLLIN;
    if (!socket_eof && !to_kodi.count) fds[1].events |= POLLIN;
    if (to_broker.count && !shutdown_sent) fds[1].events |= POLLOUT;
    if (to_kodi.count) fds[2].events |= POLLOUT;
    int n=poll(fds,3,1000);
    if (n<0) { if (errno==EINTR) continue; break; }
    if (n==0) continue;
    if (fds[0].revents & (POLLIN|POLLHUP)) {
      int x=fill(&to_broker,STDIN_FILENO,&stdin_eof);
      if(x<0) break;
      if(x>0) progress=t;
    }
    if ((fds[1].revents & (POLLIN|POLLHUP)) && !socket_eof && !to_kodi.count) {
      int x=fill(&to_kodi,s,&socket_eof);
      if(x<0) break;
      if(x>0) progress=t;
    }
    if ((fds[1].revents & POLLOUT) && to_broker.count) {
      int x=drain(&to_broker,s);
      if(x<0) break;
      if(x>0) progress=t;
    }
    if ((fds[2].revents & POLLOUT) && to_kodi.count) {
      int x=drain(&to_kodi,STDOUT_FILENO);
      if(x<0) break;
      if(x>0) progress=t;
    }
    if (fds[1].revents & (POLLERR|POLLNVAL)) break;
    if (fds[2].revents & (POLLERR|POLLHUP|POLLNVAL)) break;
  }
  close(s);
  return rc;
}
