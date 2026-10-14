include ../../Makefile.include LIBBLURAY-VERSION ../../download-files.include
DEPS = ../../Makefile.include LIBBLURAY-VERSION Makefile ../../download-files.include \
                                  001-darwinembed_DiskArbitration-revert.patch \
                                  002-darwin-dlopen_searchpath.patch \
                                  003-all-libxml_searchname.patch \
                                  004-win-remove-lib-version.patch \
                                  005-android-libmmbd-unversioned-dlopen.patch \
                                  gazelle-aacs-gate-v1.py \
                                  tvos.patch

MESON_BUILD_TYPE=release

ifeq ($(DEBUG_BUILD), yes)
  MESON_BUILD_TYPE=debug
endif

# configuration settings
CONFIGURE = $(NATIVEPREFIX)/bin/python3 $(NATIVEPREFIX)/bin/meson setup \
  --prefix=$(PREFIX) \
  --libdir=lib \
  --buildtype=$(MESON_BUILD_TYPE) \
  -Denable_tools=false \
  -Dembed_udfread=false \
  . build

ifeq ($(CROSS_COMPILING), yes)
  CONFIGURE += --cross-file=$(PREFIX)/share/cross-file.meson
  export CC=$(CC_FOR_BUILD)
  export CXX=$(CXX_FOR_BUILD)
  export CFLAGS=$(CFLAGS_FOR_BUILD)
  export CXXFLAGS=$(CXXFLAGS_FOR_BUILD)
else
  export CC CXX CFLAGS CXXFLAGS
endif
export PKG_CONFIG_LIBDIR=$(PREFIX)/share/pkgconfig

ifeq ($(OS), osx)
  # java and ant are dependencies for bdjs
  export ANT_HOME=$(PREFIX)/share/ant
  export PATH:=$(PREFIX)/share/ant/bin:$(PATH)
endif

LIBDYLIB=$(PLATFORM)/build/src/$(BYPRODUCT)

all: .installed-$(PLATFORM)

.configured-$(PLATFORM): $(DEPS) | $(TARBALLS_LOCATION)/$(ARCHIVE).$(HASH_TYPE)
	rm -rf $(PLATFORM); mkdir -p $(PLATFORM)
	cd $(PLATFORM); $(ARCHIVE_TOOL) $(ARCHIVE_TOOL_FLAGS) $(TARBALLS_LOCATION)/$(ARCHIVE)
ifeq ($(OS),darwin_embedded)
	cd $(PLATFORM); patch -p1 -i ../001-darwinembed_DiskArbitration-revert.patch
endif
	cd $(PLATFORM); patch -p1 -i ../002-darwin-dlopen_searchpath.patch
	cd $(PLATFORM); patch -p1 -i ../003-all-libxml_searchname.patch
ifeq ($(OS),android)
	cd $(PLATFORM); patch -p1 -i ../005-android-libmmbd-unversioned-dlopen.patch
	# This branch is DIAGNOSTIC ONLY. No installed Kodi production core is changed.
	# Stop if the unpacked, pre-instrumented libbluray 1.5.0 source differs.
	cd $(PLATFORM); python3 ../gazelle-aacs-gate-v1.py --source src/libbluray/disc/aacs.c --expected-sha256 74936b808fd5d236af3b6f3f73ef4e711fbf1ea23e3f9dac57051134ded5a3ce --out src/libbluray/disc/aacs.gazelle-stage-v1.c
	cd $(PLATFORM); printf '%s  %s\n' 76c64d58fa109108eda0958cd314df185f2542327f883995ba3a55b653b6357d src/libbluray/disc/aacs.gazelle-stage-v1.c | sha256sum --check -
	cd $(PLATFORM); { printf '%s\n' '#if defined(__ANDROID__)' '#define GAZELLE_AACS_GATE_TRACE 1' '#endif'; cat src/libbluray/disc/aacs.gazelle-stage-v1.c; } > src/libbluray/disc/aacs.gazelle-final-v1.c
	cd $(PLATFORM); mv src/libbluray/disc/aacs.gazelle-final-v1.c src/libbluray/disc/aacs.c
	cd $(PLATFORM); rm src/libbluray/disc/aacs.gazelle-stage-v1.c
	@echo GAZELLE_AACS_GATE_V1_DIAGNOSTIC_SOURCE_STAGED_PRODUCTION_UNCHANGED
endif
ifeq ($(findstring appletv,$(TARGET_PLATFORM)),appletv)
	cd $(PLATFORM); patch -p1 -i ../tvos.patch
endif
ifeq ($(TARGET_PLATFORM),windows)
	cd $(PLATFORM); patch -p1 -i ../004-win-remove-lib-version.patch
endif
	cd $(PLATFORM); $(CONFIGURE)
	touch $@

$(LIBDYLIB): .configured-$(PLATFORM)
	cd $(PLATFORM)/build; $(NATIVEPREFIX)/bin/ninja -v

.installed-$(PLATFORM): $(LIBDYLIB)
	cd $(PLATFORM)/build; $(NATIVEPREFIX)/bin/ninja -v install
	touch $@

clean:
	$(MAKE) -C $(PLATFORM) clean
	rm -f .installed-$(PLATFORM) .configured-$(PLATFORM)

distclean::
	rm -rf $(PLATFORM) .installed-$(PLATFORM) .configured-$(PLATFORM)
