# Legacy optical-addon packaging (historical)

**Superseded.** The userspace optical VFS and UDF checker described in
older commits are no longer part of the Fire TV build. The current build
uses the kernel-mounted read-only UDF path and packages local sources,
including native LibMMBD, its helper and Kodi startup service.

See [current standalone APK build](gazelle-kernel-udf-self-contained-build.md).
Historical implementation details remain available in Git history.
