#!/usr/bin/env python3
"""buildpy.py - builds python from source

repo: https://github.com/shakfu/buildpy

features:

- Single script which downloads, builds python from source
- Different build configurations (static, dynamic, framework) possible
- Trims python builds and zips site-packages by default.
- Each PythonConfigXXX inherits from the prior one and inherits all the patches

class structure:

Config
    PythonConfig
        PythonConfig311
            PythonConfig312
                PythonConfig313
                    PythonConfig314

ShellCmd
    Project
    AbstractBuilder
        Builder
            OpensslBuilder
            Bzip2Builder
            XzBuilder
            PythonBuilder
                PythonDebugBuilder

"""

import argparse
import copy
import datetime
import hashlib
import json
import logging
import os
import platform
import shlex
import shutil
import stat
import subprocess
import sys
import tarfile
import zipfile
from fnmatch import fnmatch
from pathlib import Path
from dataclasses import dataclass
from typing import Any, Callable, Optional, Union
from urllib.request import urlretrieve

__version__ = "0.1.1"

# ----------------------------------------------------------------------------
# type aliases

Pathlike = Union[str, Path]
MatchFn = Callable[[Path], bool]
ActionFn = Callable[[Path], None]


# ----------------------------------------------------------------------------
# dataclasses


@dataclass
class AnalysisResult:
    """Result of package dependency analysis."""

    stdlib_imports: set[str]
    third_party: set[str]
    required_extensions: set[str]
    needed_but_disabled: set[str]
    potentially_unused: set[str]
    files_analyzed: int


# ----------------------------------------------------------------------------
# env helpers


def getenv(key: str, default: bool = False) -> bool:
    """convert '0','1' env values to bool {True, False}"""
    return bool(int(os.getenv(key, default)))


def setenv(key: str, default: str) -> str:
    """get environ variable if it is exists else set default"""
    if key in os.environ:
        return os.getenv(key, default) or default
    else:
        os.environ[key] = default
        return default


# ----------------------------------------------------------------------------
# constants

PYTHON = sys.executable
PLATFORM = platform.system()
ARCH = platform.machine()
PY_VER_MINOR = sys.version_info.minor
DEFAULT_PY_VERSION = "3.13.11"
DEFAULT_PY_VERSIONS = {
    "3.14": "3.14.2",
    "3.13": "3.13.11",
    "3.12": "3.12.12",
    "3.11": "3.11.14",
}

# ----------------------------------------------------------------------------
# envar options

DEBUG = getenv("DEBUG", default=True)
COLOR = getenv("COLOR", default=True)

# ----------------------------------------------------------------------------
# platform detection utilities


class PlatformInfo:
    """Centralized platform detection and configuration"""

    def __init__(self) -> None:
        self.system = platform.system()
        self.machine = platform.machine()

    @property
    def is_darwin(self) -> bool:
        """Check if running on macOS"""
        return self.system == "Darwin"

    @property
    def is_linux(self) -> bool:
        """Check if running on Linux"""
        return self.system == "Linux"

    @property
    def is_windows(self) -> bool:
        """Check if running on Windows"""
        return self.system == "Windows"

    @property
    def is_unix(self) -> bool:
        """Check if running on Unix-like system"""
        return self.is_darwin or self.is_linux

    def get_build_types(self) -> list[str]:
        """Get available build types for current platform"""
        if self.is_darwin:
            return [
                "local",
                "shared-ext",
                "static-ext",
                "framework-ext",
                "framework-pkg",
            ]
        elif self.is_windows:
            return ["local", "windows-pkg"]
        elif self.is_linux:
            return [
                "local",
                "shared-ext",
                "static-ext",
            ]
        return ["local"]

    def setup_environment(self) -> None:
        """Setup platform-specific environment variables"""
        if self.is_darwin:
            setenv("MACOSX_DEPLOYMENT_TARGET", "12.6")


# Global platform info instance
PLATFORM_INFO = PlatformInfo()
PLATFORM_INFO.setup_environment()

# Backward compatibility
BUILD_TYPES = PLATFORM_INFO.get_build_types()
if PLATFORM_INFO.is_darwin:
    MACOSX_DEPLOYMENT_TARGET = os.getenv("MACOSX_DEPLOYMENT_TARGET", "12.6")

# ----------------------------------------------------------------------------
# logging config


class CustomFormatter(logging.Formatter):
    """custom logging formatting class"""

    white = "\x1b[97;20m"
    grey = "\x1b[38;20m"
    green = "\x1b[32;20m"
    cyan = "\x1b[36;20m"
    yellow = "\x1b[33;20m"
    red = "\x1b[31;20m"
    bold_red = "\x1b[31;1m"
    reset = "\x1b[0m"
    fmt = "%(delta)s - %(levelname)s - %(name)s.%(funcName)s - %(message)s"
    cfmt = (
        f"{white}%(delta)s{reset} - "
        f"{{}}%(levelname)s{{}} - "
        f"{white}%(name)s.%(funcName)s{reset} - "
        f"{grey}%(message)s{reset}"
    )

    FORMATS = {
        logging.DEBUG: cfmt.format(grey, reset),
        logging.INFO: cfmt.format(green, reset),
        logging.WARNING: cfmt.format(yellow, reset),
        logging.ERROR: cfmt.format(red, reset),
        logging.CRITICAL: cfmt.format(bold_red, reset),
    }

    def __init__(self, use_color: bool = COLOR) -> None:
        self.use_color = use_color

    def format(self, record: logging.LogRecord) -> str:
        """custom logger formatting method"""
        if not self.use_color:
            log_fmt: str = self.fmt
        else:
            log_fmt = self.FORMATS.get(record.levelno, self.fmt)
        if PY_VER_MINOR > 10:
            duration = datetime.datetime.fromtimestamp(
                record.relativeCreated / 1000, datetime.UTC
            )
        else:
            duration = datetime.datetime.fromtimestamp(record.relativeCreated / 1000)
        record.delta = duration.strftime("%H:%M:%S")
        formatter = logging.Formatter(log_fmt)
        return formatter.format(record)


strm_handler = logging.StreamHandler()
strm_handler.setFormatter(CustomFormatter())
# file_handler = logging.FileHandler("log.txt", mode='w')
# file_handler.setFormatter(CustomFormatter(use_color=False))
logging.basicConfig(
    level=logging.DEBUG if DEBUG else logging.INFO,
    handlers=[strm_handler],
    # handlers=[strm_handler, file_handler],
)


# ----------------------------------------------------------------------------
# config classes

BASE_CONFIG = {
    "header": [
        "DESTLIB=$(LIBDEST)",
        "MACHDESTLIB=$(BINLIBDEST)",
        "DESTPATH=",
        "SITEPATH=",
        "TESTPATH=",
        "COREPYTHONPATH=$(DESTPATH)$(SITEPATH)$(TESTPATH)",
        "PYTHONPATH=$(COREPYTHONPATH)",
        "OPENSSL=$(srcdir)/../../install/openssl",
        "BZIP2=$(srcdir)/../../install/bzip2",
        "LZMA=$(srcdir)/../../install/xz",
    ],
    "extensions": {
        "_abc": ["_abc.c"],
        "_asyncio": ["_asynciomodule.c"],
        "_bisect": ["_bisectmodule.c"],
        "_blake2": [
            "_blake2/blake2module.c",
            "_blake2/blake2b_impl.c",
            "_blake2/blake2s_impl.c",
        ],
        "_bz2": [
            "_bz2module.c",
            "-I$(BZIP2)/include",
            "-L$(BZIP2)/lib",
            "$(BZIP2)/lib/libbz2.a",
        ],
        "_codecs": ["_codecsmodule.c"],
        "_codecs_cn": ["cjkcodecs/_codecs_cn.c"],
        "_codecs_hk": ["cjkcodecs/_codecs_hk.c"],
        "_codecs_iso2022": ["cjkcodecs/_codecs_iso2022.c"],
        "_codecs_jp": ["cjkcodecs/_codecs_jp.c"],
        "_codecs_kr": ["cjkcodecs/_codecs_kr.c"],
        "_codecs_tw": ["cjkcodecs/_codecs_tw.c"],
        "_collections": ["_collectionsmodule.c"],
        "_contextvars": ["_contextvarsmodule.c"],
        "_crypt": ["_cryptmodule.c", "-lcrypt"],
        "_csv": ["_csv.c"],
        "_ctypes": [
            "_ctypes/_ctypes.c",
            "_ctypes/callbacks.c",
            "_ctypes/callproc.c",
            "_ctypes/stgdict.c",
            "_ctypes/cfield.c",
            "-ldl",
            "-lffi",
            "-DHAVE_FFI_PREP_CIF_VAR",
            "-DHAVE_FFI_PREP_CLOSURE_LOC",
            "-DHAVE_FFI_CLOSURE_ALLOC",
        ],
        "_curses": ["-lncurses", "-lncursesw", "-ltermcap", "_cursesmodule.c"],
        "_curses_panel": ["-lpanel", "-lncurses", "_curses_panel.c"],
        "_datetime": ["_datetimemodule.c"],
        "_dbm": ["_dbmmodule.c", "-lgdbm_compat", "-DUSE_GDBM_COMPAT"],
        "_decimal": ["_decimal/_decimal.c", "-DCONFIG_64=1"],
        "_elementtree": ["_elementtree.c"],
        "_functools": [
            "-DPy_BUILD_CORE_BUILTIN",
            "-I$(srcdir)/Include/internal",
            "_functoolsmodule.c",
        ],
        "_gdbm": ["_gdbmmodule.c", "-lgdbm"],
        "_hashlib": [
            "_hashopenssl.c",
            "-I$(OPENSSL)/include",
            "-L$(OPENSSL)/lib",
            "$(OPENSSL)/lib/libcrypto.a",
        ],
        "_heapq": ["_heapqmodule.c"],
        "_io": [
            "_io/_iomodule.c",
            "_io/iobase.c",
            "_io/fileio.c",
            "_io/bytesio.c",
            "_io/bufferedio.c",
            "_io/textio.c",
            "_io/stringio.c",
        ],
        "_json": ["_json.c"],
        "_locale": ["-DPy_BUILD_CORE_BUILTIN", "_localemodule.c"],
        "_lsprof": ["_lsprof.c", "rotatingtree.c"],
        "_lzma": [
            "_lzmamodule.c",
            "-I$(LZMA)/include",
            "-L$(LZMA)/lib",
            "$(LZMA)/lib/liblzma.a",
        ],
        "_md5": ["md5module.c"],
        "_multibytecodec": ["cjkcodecs/multibytecodec.c"],
        "_multiprocessing": [
            "_multiprocessing/multiprocessing.c",
            "_multiprocessing/semaphore.c",
        ],
        "_opcode": ["_opcode.c"],
        "_operator": ["_operator.c"],
        "_pickle": ["_pickle.c"],
        "_posixshmem": ["_multiprocessing/posixshmem.c"],
        "_posixsubprocess": ["_posixsubprocess.c"],
        "_queue": ["_queuemodule.c"],
        "_random": ["_randommodule.c"],
        "_scproxy": ["_scproxy.c"],
        "_sha1": ["sha1module.c"],
        "_sha256": ["sha256module.c"],
        "_sha3": ["_sha3/sha3module.c"],
        "_sha512": ["sha512module.c"],
        "_signal": [
            "-DPy_BUILD_CORE_BUILTIN",
            "-I$(srcdir)/Include/internal",
            "signalmodule.c",
        ],
        "_socket": ["socketmodule.c"],
        "_sqlite3": [
            "_sqlite/blob.c",
            "_sqlite/connection.c",
            "_sqlite/cursor.c",
            "_sqlite/microprotocols.c",
            "_sqlite/module.c",
            "_sqlite/prepare_protocol.c",
            "_sqlite/row.c",
            "_sqlite/statement.c",
            "_sqlite/util.c",
        ],
        "_sre": ["_sre/sre.c", "-DPy_BUILD_CORE_BUILTIN"],
        "_ssl": [
            "_ssl.c",
            "-I$(OPENSSL)/include",
            "-L$(OPENSSL)/lib",
            "$(OPENSSL)/lib/libcrypto.a",
            "$(OPENSSL)/lib/libssl.a",
        ],
        "_stat": ["_stat.c"],
        "_statistics": ["_statisticsmodule.c"],
        "_struct": ["_struct.c"],
        "_symtable": ["symtablemodule.c"],
        "_thread": [
            "-DPy_BUILD_CORE_BUILTIN",
            "-I$(srcdir)/Include/internal",
            "_threadmodule.c",
        ],
        "_tracemalloc": ["_tracemalloc.c"],
        "_typing": ["_typingmodule.c"],
        "_uuid": ["_uuidmodule.c"],
        "_weakref": ["_weakref.c"],
        "_zoneinfo": ["_zoneinfo.c"],
        "array": ["arraymodule.c"],
        "atexit": ["atexitmodule.c"],
        "binascii": ["binascii.c"],
        "cmath": ["cmathmodule.c"],
        "errno": ["errnomodule.c"],
        "faulthandler": ["faulthandler.c"],
        "fcntl": ["fcntlmodule.c"],
        "grp": ["grpmodule.c"],
        "itertools": ["itertoolsmodule.c"],
        "math": ["mathmodule.c"],
        "mmap": ["mmapmodule.c"],
        "ossaudiodev": ["ossaudiodev.c"],
        "posix": [
            "-DPy_BUILD_CORE_BUILTIN",
            "-I$(srcdir)/Include/internal",
            "posixmodule.c",
        ],
        "pwd": ["pwdmodule.c"],
        "pyexpat": [
            "expat/xmlparse.c",
            "expat/xmlrole.c",
            "expat/xmltok.c",
            "pyexpat.c",
            "-I$(srcdir)/Modules/expat",
            "-DHAVE_EXPAT_CONFIG_H",
            "-DUSE_PYEXPAT_CAPI",
            "-DXML_DEV_URANDOM",
        ],
        "readline": ["readline.c", "-lreadline", "-ltermcap"],
        "resource": ["resource.c"],
        "select": ["selectmodule.c"],
        "spwd": ["spwdmodule.c"],
        "syslog": ["syslogmodule.c"],
        "termios": ["termios.c"],
        "time": [
            "-DPy_BUILD_CORE_BUILTIN",
            "-I$(srcdir)/Include/internal",
            "timemodule.c",
        ],
        "unicodedata": ["unicodedata.c"],
        "zlib": ["zlibmodule.c", "-lz"],
    },
    "core": [
        "_abc",
        "_codecs",
        "_collections",
        "_functools",
        "_io",
        "_locale",
        "_operator",
        "_signal",
        "_sre",
        "_stat",
        "_symtable",
        "_thread",
        "_tracemalloc",
        "_weakref",
        "atexit",
        "errno",
        "faulthandler",
        "itertools",
        "posix",
        "pwd",
        "time",
    ],
    "shared": [],
    "static": [
        "_asyncio",
        "_bisect",
        "_blake2",
        "_bz2",
        "_contextvars",
        "_csv",
        "_datetime",
        "_decimal",
        "_elementtree",
        "_hashlib",
        "_heapq",
        "_json",
        "_lsprof",
        "_lzma",
        "_md5",
        "_multibytecodec",
        "_multiprocessing",
        "_opcode",
        "_pickle",
        "_posixshmem",
        "_posixsubprocess",
        "_queue",
        "_random",
        "_sha1",
        "_sha256",
        "_sha3",
        "_sha512",
        "_socket",
        "_sqlite3",
        "_ssl",
        "_statistics",
        "_struct",
        "_typing",
        "_uuid",
        "_zoneinfo",
        "array",
        "binascii",
        "cmath",
        "fcntl",
        "grp",
        "math",
        "mmap",
        "pyexpat",
        "readline",
        "select",
        "unicodedata",
        "zlib",
    ],
    "disabled": [
        "_codecs_cn",
        "_codecs_hk",
        "_codecs_iso2022",
        "_codecs_jp",
        "_codecs_kr",
        "_codecs_tw",
        "_crypt",
        "_ctypes",
        "_curses",
        "_curses_panel",
        "_dbm",
        "_scproxy",
        "_tkinter",
        "_xxsubinterpreters",
        "audioop",
        "nis",
        "ossaudiodev",
        "resource",
        "spwd",
        "syslog",
        "termios",
        "xxlimited",
        "xxlimited_35",
    ],
}


class Config:
    """Abstract configuration class"""

    version: str
    log: logging.Logger

    def __init__(self, cfg: dict[str, Any]) -> None:
        self.cfg: dict[str, Any] = copy.deepcopy(cfg)
        self.out = ["# -*- makefile -*-"] + self.cfg["header"] + ["\n# core\n"]
        self.log = logging.getLogger(self.__class__.__name__)
        self.install_name_id: Optional[str] = None
        self.patch()

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} '{self.version}'>"

    def patch(self) -> None:
        """patch cfg attribute"""

    def move_entries(self, src: str, dst: str, *names: str) -> None:
        """generic entry mover"""
        for name in names:
            self.log.info("%s -> %s: %s", src, dst, name)
            self.cfg[src].remove(name)
            self.cfg[dst].append(name)

    def enable_static(self, *names: str) -> None:
        """move disabled entries to static"""
        self.move_entries("disabled", "static", *names)

    def enable_shared(self, *names: str) -> None:
        """move disabled entries to shared"""
        self.move_entries("disabled", "shared", *names)

    def disable_static(self, *names: str) -> None:
        """move static entries to disabled"""
        self.move_entries("static", "disabled", *names)

    def disable_shared(self, *names: str) -> None:
        """move shared entries to disabled"""
        self.move_entries("shared", "disabled", *names)

    def move_static_to_shared(self, *names: str) -> None:
        """move static entries to shared"""
        self.move_entries("static", "shared", *names)

    def move_shared_to_static(self, *names: str) -> None:
        """move shared entries to static"""
        self.move_entries("shared", "static", *names)

    def write(self, method: str, to: Pathlike) -> None:
        """write configuration method to a file"""

        def _add_section(name: str) -> None:
            if self.cfg[name]:
                self.out.append(f"\n*{name}*\n")
                for i in sorted(self.cfg[name]):
                    if name == "disabled":
                        line = [i]
                    else:
                        ext = self.cfg["extensions"][i]
                        line = [i] + ext
                    self.out.append(" ".join(line))

        self.log.info("write method '%s' to %s", method, to)
        getattr(self, method)()
        for i in self.cfg["core"]:
            ext = self.cfg["extensions"][i]
            line = [i] + ext
            self.out.append(" ".join(line))
        for section in ["shared", "static", "disabled"]:
            _add_section(section)

        with open(to, "w", encoding="utf8") as f:
            self.out.append("# end \n")
            f.write("\n".join(self.out))

    def write_json(self, method: str, to: Pathlike) -> None:
        """Write configuration to JSON file"""
        self.log.info("write method '%s' to json: %s", method, to)
        getattr(self, method)()
        with open(to, "w") as f:
            json.dump(self.cfg, f, indent=4)


class PythonConfig(Config):
    """Base configuration class for all Python versions"""

    version: str

    def __init__(self, cfg: dict[str, Any], build_type: Optional[str] = None) -> None:
        super().__init__(cfg)
        # Set default install_name_id for framework builds
        if build_type == "framework":
            self.install_name_id = f"@rpath/Python.framework/Versions/{self.ver}/Python"

    @property
    def ver(self) -> str:
        """short python version: 3.11"""
        return ".".join(self.version.split(".")[:2])

    def static_max(self) -> None:
        """static build variant max-size"""

    def static_mid(self) -> None:
        """static build variant mid-size"""
        self.disable_static("_decimal")
        if PLATFORM == "Linux":
            self.cfg["extensions"]["_ssl"] = [
                "_ssl.c",
                "-I$(OPENSSL)/include",
                "-L$(OPENSSL)/lib",
                "-l:libssl.a -Wl,--exclude-libs,libssl.a",
                "-l:libcrypto.a -Wl,--exclude-libs,libcrypto.a",
            ]
            self.cfg["extensions"]["_hashlib"] = [
                "_hashopenssl.c",
                "-I$(OPENSSL)/include",
                "-L$(OPENSSL)/lib",
                "-l:libcrypto.a -Wl,--exclude-libs,libcrypto.a",
            ]

    def static_tiny(self) -> None:
        """static build variant tiny-size"""
        self.disable_static(
            "_bz2",
            "_decimal",
            "_csv",
            "_json",
            "_lzma",
            "_scproxy",
            "_sqlite3",
            "_ssl",
            "pyexpat",
            # "readline", # already disabled by default
        )

    def static_bootstrap(self) -> None:
        """static build variant bootstrap-size"""
        for i in self.cfg["static"]:
            self.cfg["disabled"].append(i)
        self.cfg["static"] = self.cfg["core"].copy()
        self.cfg["core"] = []

    def shared_max(self) -> None:
        """shared build variant max-size"""
        self.cfg["disabled"].remove("_ctypes")
        self.move_static_to_shared("_decimal", "_ssl", "_hashlib")

    def shared_mid(self) -> None:
        """shared build variant mid-size"""
        self.disable_static("_decimal", "_ssl", "_hashlib")

    def shared_vanilla(self) -> None:
        """shared build variant with most modules as shared extensions.

        This configuration moves most static modules to shared, enabling
        post-build removal of unused extensions. Use with --auto-reduce
        for automatic size optimization based on dependency analysis.

        Some modules must remain static because they reference internal
        Python symbols (Py_BUILD_CORE_BUILTIN) or private type objects.
        """
        # Modules that MUST remain static - they reference internal Python
        # symbols that aren't exported in shared builds
        must_stay_static = {
            # Modules with Py_BUILD_CORE_BUILTIN flag
            "_functools",
            "_locale",
            "_signal",
            "_sre",
            "_thread",
            "posix",
            "time",
            # Modules referencing internal type objects
            "_typing",  # references __PyTypeAlias_Type
        }

        # Enable all disabled modules that can be built
        for mod in [
            "_ctypes",
            "_curses",
            "_curses_panel",
            "_dbm",
            "_scproxy",
            "_tkinter",
            "resource",
            "syslog",
            "termios",
        ]:
            if mod in self.cfg["disabled"]:
                self.cfg["disabled"].remove(mod)

        # Move static modules to shared (except those that must stay static)
        static_mods = self.cfg["static"].copy()
        for mod in static_mods:
            if mod not in must_stay_static:
                self.move_static_to_shared(mod)

    def framework_max(self) -> None:
        """framework build variant max-size"""
        self.shared_max()
        self.move_static_to_shared(
            "_bz2",
            "_lzma",
            # "readline",
            "_sqlite3",
            "_scproxy",
            "zlib",
            "binascii",
        )

    def framework_mid(self) -> None:
        """framework build variant mid-size"""
        self.framework_max()
        self.disable_shared("_decimal", "_ssl", "_hashlib")


class PythonConfig311(PythonConfig):
    """configuration class to build python 3.11"""

    version: str = "3.11.14"

    def patch(self) -> None:
        """patch cfg attribute"""
        if PLATFORM == "Darwin":
            self.enable_static("_scproxy")
        elif PLATFORM == "Linux":
            self.enable_static("ossaudiodev")


class PythonConfig312(PythonConfig311):
    """configuration class to build python 3.12"""

    version = "3.12.10"

    def patch(self) -> None:
        """patch cfg attribute"""

        super().patch()

        self.cfg["extensions"].update(
            {
                "_md5": [
                    "md5module.c",
                    "-I$(srcdir)/Modules/_hacl/include",
                    "_hacl/Hacl_Hash_MD5.c",
                    "-D_BSD_SOURCE",
                    "-D_DEFAULT_SOURCE",
                ],
                "_sha1": [
                    "sha1module.c",
                    "-I$(srcdir)/Modules/_hacl/include",
                    "_hacl/Hacl_Hash_SHA1.c",
                    "-D_BSD_SOURCE",
                    "-D_DEFAULT_SOURCE",
                ],
                "_sha2": [
                    "sha2module.c",
                    "-I$(srcdir)/Modules/_hacl/include",
                    "_hacl/Hacl_Hash_SHA2.c",
                    "-D_BSD_SOURCE",
                    "-D_DEFAULT_SOURCE",
                    # "Modules/_hacl/libHacl_Hash_SHA2.a",
                ],
                "_sha3": [
                    "sha3module.c",
                    "-I$(srcdir)/Modules/_hacl/include",
                    "_hacl/Hacl_Hash_SHA3.c",
                    "-D_BSD_SOURCE",
                    "-D_DEFAULT_SOURCE",
                ],
            }
        )
        del self.cfg["extensions"]["_sha256"]
        del self.cfg["extensions"]["_sha512"]
        self.cfg["static"].append("_sha2")
        self.cfg["static"].remove("_sha256")
        self.cfg["static"].remove("_sha512")
        self.cfg["disabled"].append("_xxinterpchannels")


class PythonConfig313(PythonConfig312):
    """configuration class to build python 3.13"""

    version = "3.13.9"

    def patch(self) -> None:
        """patch cfg attribute"""

        super().patch()

        self.cfg["extensions"].update(
            {
                "_interpchannels": ["_interpchannelsmodule.c"],
                "_interpqueues": ["_interpqueuesmodule.c"],
                "_interpreters": ["_interpretersmodule.c"],
                "_sysconfig": ["_sysconfig.c"],
                "_testexternalinspection": ["_testexternalinspection.c"],
            }
        )

        del self.cfg["extensions"]["_crypt"]
        del self.cfg["extensions"]["ossaudiodev"]
        del self.cfg["extensions"]["spwd"]

        self.cfg["static"].append("_interpchannels")
        self.cfg["static"].append("_interpqueues")
        self.cfg["static"].append("_interpreters")
        self.cfg["static"].append("_sysconfig")

        self.cfg["disabled"].remove("_crypt")
        self.cfg["disabled"].remove("_xxsubinterpreters")
        self.cfg["disabled"].remove("audioop")
        self.cfg["disabled"].remove("nis")
        self.cfg["disabled"].remove("ossaudiodev")
        self.cfg["disabled"].remove("spwd")

        self.cfg["disabled"].append("_testexternalinspection")


class PythonConfig314(PythonConfig313):
    """configuration class to build python 3.14"""

    version = "3.14.0"

    def patch(self) -> None:
        """patch cfg attribute"""

        super().patch()

        # Add new modules in 3.14
        self.cfg["extensions"].update(
            {
                "_types": ["_typesmodule.c"],
                "_hmac": ["hmacmodule.c"],
                "_remote_debugging": ["_remote_debugging_module.c"],
                "_zstd": ["_zstd/_zstdmodule.c", "-lzstd", "-I$(srcdir)/Modules/_zstd"],
            }
        )

        # Simplify hash module configurations (no longer use HACL-specific flags)
        self.cfg["extensions"]["_blake2"] = ["blake2module.c"]
        self.cfg["extensions"]["_md5"] = ["md5module.c"]
        self.cfg["extensions"]["_sha1"] = ["sha1module.c"]
        # Note: _sha2 replaces separate _sha256/_sha512 in some contexts
        self.cfg["extensions"]["_sha2"] = ["sha2module.c"]
        self.cfg["extensions"]["_sha3"] = ["sha3module.c"]

        # Remove _contextvars (now built-in to core)
        if "_contextvars" in self.cfg["extensions"]:
            del self.cfg["extensions"]["_contextvars"]
        if "_contextvars" in self.cfg["static"]:
            self.cfg["static"].remove("_contextvars")

        # Remove _testexternalinspection (no longer in 3.14)
        if "_testexternalinspection" in self.cfg["extensions"]:
            del self.cfg["extensions"]["_testexternalinspection"]
        if "_testexternalinspection" in self.cfg["disabled"]:
            self.cfg["disabled"].remove("_testexternalinspection")

        # Add new modules to static build by default
        self.cfg["static"].append("_types")
        self.cfg["static"].append("_hmac")

        # Disable _remote_debugging and _zstd by default (optional modules)
        self.cfg["disabled"].append("_remote_debugging")
        self.cfg["disabled"].append("_zstd")

        # Remove from 'static'
        self.cfg["static"].remove("_sha1")
        self.cfg["static"].remove("_sha2")
        self.cfg["static"].remove("_sha3")
        self.cfg["static"].remove("_hmac")


# ----------------------------------------------------------------------------
# custom exceptions


class BuildError(Exception):
    """Base exception for build errors"""

    pass


class CommandError(BuildError):
    """Exception for command execution errors"""

    pass


class DownloadError(BuildError):
    """Exception for download errors"""

    pass


class ExtractionError(BuildError):
    """Exception for extraction errors"""

    pass


class ValidationError(BuildError):
    """Exception for validation errors"""

    pass


# ----------------------------------------------------------------------------
# utility classes


class ShellCmd:
    """Provides platform agnostic file/folder handling."""

    log: logging.Logger

    def cmd(self, shellcmd: Union[str, list[str]], cwd: Pathlike = ".") -> None:
        """Run shell command within working directory

        Args:
            shellcmd: Command as string (will be split safely) or list of args
            cwd: Working directory for command execution

        Raises:
            CommandError: If command execution fails
        """
        self.log.info(shellcmd if isinstance(shellcmd, str) else " ".join(shellcmd))
        try:
            if isinstance(shellcmd, str):
                # Only use shell=True for commands that genuinely need shell features
                # like pipes, redirects, etc. Otherwise split safely
                if any(
                    char in shellcmd for char in ["|", ">", "<", "&", ";", "&&", "||"]
                ):
                    subprocess.check_call(shellcmd, shell=True, cwd=str(cwd))
                else:
                    subprocess.check_call(shlex.split(shellcmd), cwd=str(cwd))
            else:
                subprocess.check_call(shellcmd, cwd=str(cwd))
        except subprocess.CalledProcessError as e:
            self.log.critical("Command failed: %s", e, exc_info=True)
            raise CommandError(f"Command failed: {shellcmd}") from e

    def download(
        self,
        url: str,
        tofolder: Optional[Pathlike] = None,
        checksum: Optional[str] = None,
        checksum_algo: str = "sha256",
    ) -> Pathlike:
        """Download a file from a url to an optional folder with checksum validation

        Args:
            url: URL to download from
            tofolder: Optional destination folder
            checksum: Optional checksum to validate download
            checksum_algo: Hash algorithm (sha256, sha512, md5)

        Returns:
            Path to downloaded file

        Raises:
            DownloadError: If download or validation fails
        """
        _path = Path(os.path.basename(url))
        if tofolder:
            _path = Path(tofolder).joinpath(_path)
            if _path.exists():
                if checksum:
                    self.log.info("Validating cached file...")
                    # Validate existing file
                    if not self._validate_checksum(_path, checksum, checksum_algo):
                        self.log.warning(
                            "Existing file checksum mismatch, re-downloading"
                        )
                        _path.unlink()
                    else:
                        self.log.debug("Using cached file: %s", _path)
                        return _path
                else:
                    self.log.debug("Using cached file: %s", _path)
                    return _path

        try:
            self.log.info("Downloading %s...", os.path.basename(url))
            filename, _ = urlretrieve(url, filename=_path)
            self.log.info("Download complete: %s", os.path.basename(str(filename)))

            if checksum:
                self.log.info("Verifying checksum...")
                if not self._validate_checksum(_path, checksum, checksum_algo):
                    _path.unlink()
                    raise DownloadError(f"Checksum validation failed for {url}")
                self.log.info("Checksum verified")

            return Path(filename)
        except Exception as e:
            if _path.exists():
                _path.unlink()
            raise DownloadError(f"Failed to download {url}: {e}") from e

    def _validate_checksum(
        self, filepath: Path, expected: str, algo: str = "sha256"
    ) -> bool:
        """Validate file checksum

        Args:
            filepath: Path to file
            expected: Expected checksum value
            algo: Hash algorithm

        Returns:
            True if checksum matches, False otherwise
        """
        hash_func = hashlib.new(algo)
        with open(filepath, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                hash_func.update(chunk)
        actual = hash_func.hexdigest()
        return bool(actual.lower() == expected.lower())

    def extract(self, archive: Pathlike, tofolder: Pathlike = ".") -> None:
        """Extract archive with security measures

        Args:
            archive: Path to archive file
            tofolder: Destination folder

        Raises:
            ExtractionError: If extraction fails or file type unsupported
        """
        if tarfile.is_tarfile(archive):
            try:
                with tarfile.open(archive) as f:
                    self.log.info("Extracting %s", os.path.basename(str(archive)))
                    if sys.version_info.minor >= 12:
                        f.extractall(tofolder, filter="data")
                    else:
                        # Backport safe extraction for older Python versions
                        self._safe_extract_tar(f, tofolder)
            except Exception as e:
                raise ExtractionError(f"Failed to extract {archive}: {e}") from e
        elif zipfile.is_zipfile(archive):
            try:
                self.log.info("Extracting %s", os.path.basename(str(archive)))
                with zipfile.ZipFile(archive) as f:
                    f.extractall(tofolder)
            except Exception as e:
                raise ExtractionError(f"Failed to extract {archive}: {e}") from e
        else:
            raise ExtractionError(f"Unsupported archive type: {archive}")

    def _safe_extract_tar(self, tar: tarfile.TarFile, path: Pathlike) -> None:
        """Safely extract tarfile for Python < 3.12 (CVE-2007-4559 mitigation)

        Args:
            tar: Open TarFile object
            path: Destination path
        """
        dest_path = Path(path).resolve()

        for member in tar.getmembers():
            member_path = (dest_path / member.name).resolve()

            # Check for path traversal
            if not str(member_path).startswith(str(dest_path)):
                raise ExtractionError(f"Path traversal detected: {member.name}")

            # Check for dangerous file types
            if member.issym() or member.islnk():
                link_target = (
                    Path(member.linkname).resolve()
                    if member.issym()
                    else Path(member.linkname)
                )
                if member.issym() and not str(link_target).startswith(str(dest_path)):
                    self.log.warning(
                        "Skipping suspicious symlink: %s -> %s",
                        member.name,
                        member.linkname,
                    )
                    continue

        # If all checks pass, extract
        tar.extractall(path)

    def fail(self, msg: str, *args: str) -> str:
        """Raise BuildError with formatted message

        Args:
            msg: Error message format string
            *args: Format arguments

        Raises:
            BuildError: Always raised with formatted message

        Returns:
            Never returns (always raises), but typed as str for property compatibility
        """
        formatted_msg = msg % args if args else msg
        self.log.critical(formatted_msg)
        raise BuildError(formatted_msg)

    def git_clone(
        self,
        url: str,
        branch: Optional[str] = None,
        directory: Optional[Pathlike] = None,
        recurse: bool = False,
        cwd: Pathlike = ".",
    ) -> None:
        """git clone a repository source tree from a url

        Args:
            url: Git repository URL
            branch: Optional branch/tag to checkout
            directory: Optional destination directory
            recurse: Whether to recurse submodules
            cwd: Working directory

        Raises:
            ValidationError: If URL is invalid
            CommandError: If git clone fails
        """
        # Basic URL validation
        if not url.startswith(("https://", "http://", "git://", "ssh://", "git@")):
            raise ValidationError(f"Invalid git URL: {url}")

        _cmds = ["git", "clone", "--depth", "1"]
        if branch:
            _cmds.extend(["--branch", branch])
        if recurse:
            _cmds.extend(["--recurse-submodules", "--shallow-submodules"])
        _cmds.append(url)
        if directory:
            _cmds.append(str(directory))
        self.cmd(_cmds, cwd=cwd)

    def getenv(self, key: str, default: bool = False) -> bool:
        """convert '0','1' env values to bool {True, False}"""
        self.log.info("checking env variable: %s", key)
        return bool(int(os.getenv(key, default)))

    def chdir(self, path: Pathlike) -> None:
        """Change current workding directory to path"""
        self.log.info("changing working dir to: %s", path)
        os.chdir(path)

    def chmod(self, path: Pathlike, perm: int = 0o777) -> None:
        """Change permission of file"""
        self.log.info("change permission of %s to %s", path, perm)
        os.chmod(path, perm)

    def get(self, shellcmd: str, cwd: Pathlike = ".", shell: bool = False) -> str:
        """get output of shellcmd"""
        shellcmd_list: Union[str, list[str]] = shellcmd
        if not shell:
            shellcmd_list = shellcmd.split()
        return subprocess.check_output(
            shellcmd_list, encoding="utf8", shell=shell, cwd=str(cwd)
        ).strip()

    def makedirs(self, path: Pathlike, mode: int = 511, exist_ok: bool = True) -> None:
        """Recursive directory creation function"""
        self.log.debug("Making directory: %s", path)
        os.makedirs(path, mode, exist_ok)

    def move(self, src: Pathlike, dst: Pathlike) -> None:
        """Move from src path to dst path."""
        self.log.debug("Moving %s to %s", src, dst)
        shutil.move(src, dst)

    def glob_move(self, src: Pathlike, patterns: str, dst: Pathlike) -> None:
        """Move with glob patterns"""
        src_path = Path(src)
        targets = src_path.glob(patterns)
        for t in targets:
            self.move(t, dst)

    def copy(self, src: Pathlike, dst: Pathlike) -> None:
        """copy file or folders -- tries to be behave like `cp -rf`"""
        self.log.info("copy %s to %s", src, dst)
        src, dst = Path(src), Path(dst)
        if src.is_dir():
            shutil.copytree(src, dst)
        else:
            shutil.copy2(src, dst)

    def remove(self, path: Pathlike, silent: bool = False) -> None:
        """Remove file or folder."""
        from typing import Any

        # handle windows error on read-only files
        def remove_readonly(func: Callable[..., Any], path: str, exc_info: Any) -> None:
            "Clear the readonly bit and reattempt the removal"
            if PY_VER_MINOR < 11:
                if func not in (os.unlink, os.rmdir) or exc_info[1].winerror != 5:
                    raise exc_info[1]
            else:
                if func not in (os.unlink, os.rmdir) or exc_info.winerror != 5:
                    raise exc_info
            os.chmod(path, stat.S_IWRITE)
            func(path)

        path = Path(path)
        if path.is_dir():
            if not silent:
                self.log.debug("Removing folder: %s", path)
            if PY_VER_MINOR < 11:
                shutil.rmtree(path, ignore_errors=not DEBUG, onerror=remove_readonly)
            else:
                shutil.rmtree(path, ignore_errors=not DEBUG, onexc=remove_readonly)
        else:
            if not silent:
                self.log.debug("Removing file: %s", path)
            try:
                path.unlink()
            except FileNotFoundError:
                if not silent:
                    self.log.debug("File not found: %s", path)

    def walk(
        self,
        root: Pathlike,
        match_func: MatchFn,
        action_func: ActionFn,
        skip_patterns: list[str],
    ) -> None:
        """general recursive walk from root path with match and action functions"""
        for root_, dirs, filenames in os.walk(root):
            _root = Path(root_)
            if skip_patterns:
                for skip_pat in skip_patterns:
                    if skip_pat in dirs:
                        dirs.remove(skip_pat)
            for _dir in dirs:
                current = _root / _dir
                if match_func(current):
                    action_func(current)

            for _file in filenames:
                current = _root / _file
                if match_func(current):
                    action_func(current)

    def glob_remove(
        self, root: Pathlike, patterns: list[str], skip_dirs: list[str]
    ) -> None:
        """applies recursive glob remove using a list of patterns"""

        def match(entry: Path) -> bool:
            # return any(fnmatch(entry, p) for p in patterns)
            return any(fnmatch(entry.name, p) for p in patterns)

        def remove(entry: Path) -> None:
            self.remove(entry)

        self.walk(root, match_func=match, action_func=remove, skip_patterns=skip_dirs)

    def pip_install(
        self,
        *pkgs: str,
        reqs: Optional[str] = None,
        upgrade: bool = False,
        pip: Optional[str] = None,
    ) -> None:
        """Install python packages using pip"""
        _cmds = []
        if pip:
            _cmds.append(pip)
        else:
            _cmds.append("pip3")
        _cmds.append("install")
        if reqs:
            _cmds.append(f"-r {reqs}")
        else:
            if upgrade:
                _cmds.append("--upgrade")
            _cmds.extend(pkgs)
        self.cmd(" ".join(_cmds))

    def apt_install(self, *pkgs: str, update: bool = False) -> None:
        """install debian packages using apt"""
        _cmds: list[str] = []
        _cmds.append("sudo apt install")
        if update:
            _cmds.append("--upgrade")
        _cmds.extend(pkgs)
        self.cmd(" ".join(_cmds))

    def brew_install(self, *pkgs: str, update: bool = False) -> None:
        """install using homebrew"""
        _pkgs = " ".join(pkgs)
        if update:
            self.cmd("brew update")
        self.cmd(f"brew install {_pkgs}")

    def cmake_config(
        self, src_dir: Pathlike, build_dir: Pathlike, *scripts: Pathlike, **options: str
    ) -> None:
        """activate cmake configuration / generation stage"""
        _cmds = [f"cmake -S {src_dir} -B {build_dir}"]
        if scripts:
            _cmds.append(" ".join(f"-C {path}" for path in scripts))
        if options:
            _cmds.append(" ".join(f"-D{k}={v}" for k, v in options.items()))
        self.cmd(" ".join(_cmds))

    def cmake_build(self, build_dir: Pathlike, release: bool = False) -> None:
        """activate cmake build stage"""
        _cmd = f"cmake --build {build_dir}"
        if release:
            _cmd += " --config Release"
        self.cmd(_cmd)

    def cmake_install(self, build_dir: Pathlike, prefix: Optional[str] = None) -> None:
        """activate cmake install stage"""
        _cmds = ["cmake --install", str(build_dir)]
        if prefix:
            _cmds.append(f"--prefix {prefix}")
        self.cmd(" ".join(_cmds))


# ----------------------------------------------------------------------------
# main classes


class Project(ShellCmd):
    """Utility class to hold project directory structure"""

    def __init__(self) -> None:
        self.root = Path.cwd()
        self.build = self.root / "build"
        self.support = self.root / "support"
        self.downloads = self.build / "downloads"
        self.src = self.build / "src"
        self.install = self.build / "install"
        self.bin = self.build / "bin"
        self.lib = self.build / "lib"
        self.lib_static = self.build / "lib" / "static"
        self.log = logging.getLogger(self.__class__.__name__)

    def setup(self) -> None:
        """create main project directories"""
        self.build.mkdir(exist_ok=True)
        self.downloads.mkdir(exist_ok=True)
        self.install.mkdir(exist_ok=True)
        self.src.mkdir(exist_ok=True)

    def reset(self) -> None:
        """prepare project for a rebuild"""
        self.remove(self.src)
        self.remove(self.install / "python")


class AbstractBuilder(ShellCmd):
    """Abstract builder class with additional methods common to subclasses."""

    name: str
    version: str
    repo_url: str
    download_archive_template: str
    download_url_template: str
    lib_products: list[str]
    depends_on: list[type["Builder"]]

    def __init__(
        self, version: Optional[str] = None, project: Optional[Project] = None
    ) -> None:
        self.version = version or self.version
        self.project = project or Project()
        self.log = logging.getLogger(self.__class__.__name__)

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} '{self.name}-{self.version}'>"

    @property
    def ver(self) -> str:
        """short python version: 3.11"""
        return ".".join(self.version.split(".")[:2])

    @property
    def ver_major(self) -> str:
        """major compoent of semantic version: 3 in 3.11.7"""
        return self.version.split(".")[0]

    @property
    def ver_minor(self) -> str:
        """minor compoent of semantic version: 11 in 3.11.7"""
        return self.version.split(".")[1]

    @property
    def ver_patch(self) -> str:
        """patch compoent of semantic version: 7 in 3.11.7"""
        return self.version.split(".")[2]

    @property
    def ver_nodot(self) -> str:
        """concat major and minor version components: 311 in 3.11.7"""
        return self.ver.replace(".", "")

    @property
    def name_version(self) -> str:
        """return name-<fullversion>: e.g. Python-3.11.7"""
        return f"{self.name}-{self.version}"

    @property
    def name_ver(self) -> str:
        """return name.lower-<ver>: e.g. python3.11"""
        return f"{self.name.lower()}{self.ver}"

    @property
    def name_ver_nodot(self) -> str:
        """return name.lower-<ver_nodot>: e.g. python311"""
        return f"{self.name.lower()}{self.ver_nodot}"

    @property
    def download_archive(self) -> str:
        """return filename of archive to be downloaded"""
        return self.download_archive_template.format(ver=self.version)

    @property
    def download_url(self) -> str:
        """return download url with version interpolated"""
        return self.download_url_template.format(
            archive=self.download_archive, ver=self.version
        )

    @property
    def downloaded_archive(self) -> Path:
        """return path to downloaded archive"""
        return self.project.downloads / self.download_archive

    @property
    def archive_is_downloaded(self) -> bool:
        """return true if archive is downloaded"""
        return self.downloaded_archive.exists()

    @property
    def repo_branch(self) -> str:
        """return repo branch"""
        return self.name.lower()

    @property
    def src_dir(self) -> Path:
        """return extracted source folder of build target"""
        return self.project.src / self.name_version

    @property
    def build_dir(self) -> Path:
        """return 'build' folder src dir of build target"""
        return self.src_dir / "build"

    @property
    def executable_name(self) -> str:
        """executable name of buld target"""
        name = self.name.lower()
        if PLATFORM == "Windows":
            name = f"{self.name}.exe"
        return name

    @property
    def executable(self) -> Path:
        """executable path of buld target"""
        return self.project.bin / self.executable_name

    @property
    def libname(self) -> str:
        """library name prefix"""
        return f"lib{self.name}"

    @property
    def staticlib_name(self) -> str:
        """static libname"""
        suffix = ".a"
        if PLATFORM == "Windows":
            suffix = ".lib"
        return f"{self.libname}{suffix}"

    @property
    def dylib_name(self) -> str:
        """dynamic link libname"""
        if PLATFORM == "Darwin":
            return f"{self.libname}.dylib"
        if PLATFORM == "Linux":
            return f"{self.libname}.so"
        if PLATFORM == "Windows":
            return f"{self.libname}.dll"
        return self.fail("platform not supported")

    @property
    def dylib_linkname(self) -> str:
        """symlink to dylib"""
        if PLATFORM == "Darwin":
            return f"{self.libname}.dylib"
        if PLATFORM == "Linux":
            return f"{self.libname}.so"
        return self.fail("platform not supported")

    @property
    def dylib(self) -> Path:
        """dylib path"""
        return self.prefix / "lib" / self.dylib_name

    @property
    def dylib_link(self) -> Path:
        """dylib link path"""
        return self.project.lib / self.dylib_linkname

    @property
    def staticlib(self) -> Path:
        """staticlib path"""
        return self.prefix / "lib" / self.staticlib_name

    @property
    def prefix(self) -> Path:
        """builder prefix path"""
        return self.project.install / self.name.lower()

    def lib_products_exist(self) -> bool:
        """check if all built lib_products already exist"""
        return all((self.prefix / "lib" / lib).exists() for lib in self.lib_products)

    def pre_process(self) -> None:
        """override by subclass if needed"""

    def setup(self) -> None:
        """setup build environment"""

    def configure(self) -> None:
        """configure build"""

    def build(self) -> None:
        """build target"""

    def install(self) -> None:
        """install target"""

    def clean(self) -> None:
        """clean build"""

    def post_process(self) -> None:
        """override by subclass if needed"""

    def process(self) -> None:
        """main builder process"""
        self.pre_process()
        self.setup()
        self.configure()
        self.build()
        self.install()
        self.clean()
        self.post_process()


class Builder(AbstractBuilder):
    """concrete builder class"""

    def setup(self) -> None:
        """setup build environment"""
        self.project.setup()
        if not self.archive_is_downloaded:
            archive = self.download(self.download_url, tofolder=self.project.downloads)
            self.log.info("downloaded %s", archive)
        else:
            archive = self.downloaded_archive
        if not self.lib_products_exist():
            if self.src_dir.exists():
                self.remove(self.src_dir)
            self.extract(archive, tofolder=self.project.src)
            if not self.src_dir.exists():
                raise ExtractionError(f"could not extract from {archive}")


class OpensslBuilder(Builder):
    """ssl builder class"""

    name = "openssl"
    version = "1.1.1w"
    repo_url = "https://github.com/openssl/openssl.git"
    download_archive_template = "openssl-{ver}.tar.gz"
    download_url_template = "https://www.openssl.org/source/old/1.1.1/{archive}"
    depends_on = []
    lib_products = ["libssl.a", "libcrypto.a"]

    def build(self) -> None:
        """main build method"""
        if not self.lib_products_exist():
            self.log.info("Configuring %s...", self.name)
            self.cmd(
                f"./config no-shared no-tests --prefix={self.prefix}", cwd=self.src_dir
            )
            self.log.info("Building %s...", self.name)
            self.cmd("make install_sw", cwd=self.src_dir)
            self.log.info("%s build complete", self.name)


class Bzip2Builder(Builder):
    """bz2 builder class"""

    name = "bzip2"
    version = "1.0.8"
    repo_url = "https://github.com/libarchive/bzip2.git"
    download_archive_template = "bzip2-{ver}.tar.gz"
    download_url_template = "https://sourceware.org/pub/bzip2/{archive}"
    depends_on: list[type["Builder"]] = []
    lib_products = ["libbz2.a"]

    def build(self) -> None:
        """main build method"""
        if not self.lib_products_exist():
            cflags = "-fPIC"
            self.cmd(
                f"make install PREFIX={self.prefix} CFLAGS='{cflags}'",
                cwd=self.src_dir,
            )


class XzBuilder(Builder):
    """lzma builder class"""

    name = "xz"
    version = "5.8.2"
    repo_url = "https://github.com/tukaani-project/xz.git"
    download_archive_template = "xz-{ver}.tar.gz"
    download_url_template = (
        "https://github.com/tukaani-project/xz/releases/download/v{ver}/xz-{ver}.tar.gz"
    )
    depends_on: list[type["Builder"]] = []
    lib_products = ["liblzma.a"]

    def build(self) -> None:
        """main build method"""
        if not self.lib_products_exist():
            configure = self.src_dir / "configure"
            install_sh = self.src_dir / "build-aux" / "install-sh"
            for f in [configure, install_sh]:
                self.chmod(f, 0o755)
            self.cmd(
                " ".join(
                    [
                        "/bin/sh",
                        "configure",
                        "--disable-dependency-tracking",
                        "--disable-xzdec",
                        "--disable-lzmadec",
                        "--disable-nls",
                        "--enable-small",
                        "--disable-shared",
                        f"--prefix={self.prefix}",
                    ]
                ),
                cwd=self.src_dir,
            )
            self.cmd("make && make install", cwd=self.src_dir)


class PythonBuilder(Builder):
    """Builds python locally"""

    name = "Python"
    version = DEFAULT_PY_VERSION
    repo_url = "https://github.com/python/cpython.git"
    download_archive_template = "Python-{ver}.tar.xz"
    download_url_template = "https://www.python.org/ftp/python/{ver}/{archive}"

    config_options: list[str] = [
        # "--disable-ipv6",
        # "--disable-profiling",
        "--disable-test-modules",
        # "--enable-framework",
        # "--enable-framework=INSTALLDIR",
        # "--enable-optimizations",
        # "--enable-shared",
        # "--enable-universalsdk",
        # "--enable-universalsdk=SDKDIR",
        # "--enable-loadable-sqlite-extensions",
        # "--with-lto",
        # "--with-lto=thin",
        # "--with-openssl-rpath=auto",
        # "--with-openssl=DIR",
        # "--with-readline=editline",
        # "--with-system-expat",
        # "--with-system-ffi",
        # "--with-system-libmpdec",
        # "--without-builtin-hashlib-hashes",
        # "--without-doc-strings",
        # "--without-ensurepip",
        # "--without-readline",
        # "--without-static-libpython",
    ]

    required_packages: list[str] = []

    remove_patterns: list[str] = [
        "*.exe",
        "*config-3*",
        "*tcl*",
        "*tdbc*",
        "*tk*",
        "__phello__",
        "__pycache__",
        "_codecs_*.so",
        "_test*",
        "_tk*",
        "_xx*.so",
        "distutils",
        "idlelib",
        "lib2to3",
        "libpython*",
        "LICENSE.txt",
        "pkgconfig",
        "pydoc_data",
        "site-packages",
        "test",
        "Tk*",
        "turtle*",
        "venv",
        "xx*.so",
    ]

    depends_on = [OpensslBuilder, Bzip2Builder, XzBuilder]

    def __init__(
        self,
        version: str = DEFAULT_PY_VERSION,
        project: Optional[Project] = None,
        config: str = "shared_max",
        precompile: bool = True,
        optimize: bool = False,
        optimize_bytecode: int = -1,
        pkgs: Optional[list[str]] = None,
        cfg_opts: Optional[list[str]] = None,
        jobs: int = 1,
        is_package: bool = False,
        install_dir: Optional[Pathlike] = None,
        skip_ziplib: bool = False,
    ):
        super().__init__(version, project)
        self.config = config
        self.precompile = precompile
        self.optimize = optimize
        self.optimize_bytecode = optimize_bytecode
        self.pkgs = pkgs or []
        self.cfg_opts = cfg_opts or []
        self.jobs = jobs
        self.skip_ziplib = skip_ziplib

        # Handle install_dir specification
        # Priority: explicit install_dir > is_package (for backwards compatibility) > default (install)
        if install_dir is not None:
            self._install_dir = Path(install_dir)
        elif is_package:
            self._install_dir = self.project.support
        else:
            self._install_dir = self.project.install

        self.log = logging.getLogger(self.__class__.__name__)

    def get_config(self) -> PythonConfig:
        """get configuration class for required python version"""
        return {
            "3.11": PythonConfig311,
            "3.12": PythonConfig312,
            "3.13": PythonConfig313,
            "3.14": PythonConfig314,
        }[self.ver](BASE_CONFIG, self.build_type)

    @property
    def libname(self) -> str:
        """library name suffix"""
        return f"lib{self.name_ver}"

    @property
    def build_type(self) -> str:
        """build type: 'static', 'shared' or 'framework'"""
        return self.config.split("_")[0]

    @property
    def size_type(self) -> str:
        """size qualifier: 'max', 'mid', 'min', etc.."""
        return self.config.split("_")[1]

    def dry_run(self) -> None:
        """Display build plan without actually building.

        Shows configuration details, modules, dependencies, and build options
        that would be used if the build were to proceed.
        """
        config = self.get_config()
        # Apply the configuration method to populate module lists
        getattr(config, self.config)()

        # Build configure options that would be used
        config_options = self.config_options.copy()
        if self.build_type == "static":
            config_options.append("--disable-shared")
        elif self.build_type == "shared":
            config_options.append("--enable-shared")
        elif self.build_type == "framework":
            config_options.append("--enable-framework")
        if self.optimize:
            config_options.append("--enable-optimizations")
        if not self.pkgs and not self.required_packages:
            config_options.append("--without-ensurepip")
        if self.cfg_opts:
            for cfg_opt in self.cfg_opts:
                cfg_opt = cfg_opt.replace("_", "-")
                cfg_opt = "--" + cfg_opt
                if cfg_opt not in config_options:
                    config_options.append(cfg_opt)

        # Print the build plan
        print("\n" + "=" * 60)
        print("BUILD PLAN (dry-run)")
        print("=" * 60)

        print("\n[Build Target]")
        print(f"  Python version:    {self.version}")
        print(f"  Configuration:     {self.config}")
        print(f"  Build type:        {self.build_type}")
        print(f"  Size type:         {self.size_type}")
        print(f"  Platform:          {PLATFORM} ({ARCH})")

        print("\n[Directories]")
        print(f"  Install directory: {self._install_dir}")
        print(f"  Prefix:            {self.prefix}")
        print(f"  Source directory:  {self.src_dir}")

        print("\n[Build Options]")
        print(f"  Parallel jobs:     {self.jobs}")
        print(f"  Optimize build:    {self.optimize}")
        print(f"  Precompile stdlib: {self.precompile}")
        print(f"  Bytecode opt:      {self.optimize_bytecode}")

        print("\n[Configure Options]")
        for opt in sorted(config_options):
            print(f"  {opt}")

        print("\n[Dependencies]")
        if self.depends_on:
            for dep_class in self.depends_on:
                dep = dep_class()
                print(f"  {dep.name} {dep.version}")
        else:
            print("  (none)")

        print(f"\n[Modules - Core] ({len(config.cfg['core'])})")
        for mod in sorted(config.cfg["core"]):
            print(f"  {mod}")

        print(f"\n[Modules - Static] ({len(config.cfg['static'])})")
        if config.cfg["static"]:
            for mod in sorted(config.cfg["static"]):
                print(f"  {mod}")
        else:
            print("  (none)")

        print(f"\n[Modules - Shared] ({len(config.cfg['shared'])})")
        if config.cfg["shared"]:
            for mod in sorted(config.cfg["shared"]):
                print(f"  {mod}")
        else:
            print("  (none)")

        print(f"\n[Modules - Disabled] ({len(config.cfg['disabled'])})")
        if config.cfg["disabled"]:
            for mod in sorted(config.cfg["disabled"]):
                print(f"  {mod}")
        else:
            print("  (none)")

        if self.pkgs:
            print(f"\n[Packages to Install] ({len(self.pkgs)})")
            for pkg in self.pkgs:
                print(f"  {pkg}")

        print("\n" + "=" * 60)
        print("End of build plan. No changes were made.")
        print("=" * 60 + "\n")

    def size_report(self) -> None:
        """Display size breakdown of a completed build.

        Analyzes the build output directory and reports sizes by component:
        binaries, stdlib, lib-dynload, shared libraries, etc.
        """
        if not self.prefix.exists():
            print(f"\nError: Build directory not found: {self.prefix}")
            print("Run a build first, then use --size-report to analyze it.")
            return

        def format_size(size_bytes: int) -> str:
            """Format size in human-readable units"""
            size: float = float(size_bytes)
            for unit in ["B", "KB", "MB", "GB"]:
                if size < 1024:
                    return f"{size:,.1f} {unit}"
                size /= 1024
            return f"{size:,.1f} TB"

        def get_dir_size(path: Path) -> int:
            """Calculate total size of a directory"""
            total = 0
            if path.is_file():
                return path.stat().st_size
            if path.is_dir():
                for item in path.rglob("*"):
                    if item.is_file():
                        total += item.stat().st_size
            return total

        def get_file_sizes(path: Path) -> dict[str, int]:
            """Get sizes of individual files in a directory"""
            sizes: dict[str, int] = {}
            if path.is_dir():
                for item in path.iterdir():
                    if item.is_file():
                        sizes[item.name] = item.stat().st_size
            return sizes

        # Calculate sizes for each component
        components: dict[str, int] = {}

        # Binaries (bin/)
        bin_dir = self.prefix / "bin"
        if bin_dir.exists():
            components["bin/ (executables)"] = get_dir_size(bin_dir)

        # Main library directory
        lib_dir = self.prefix / "lib"
        if lib_dir.exists():
            # Shared/static libraries at lib/ level
            lib_files_size = 0
            for item in lib_dir.iterdir():
                if item.is_file():
                    lib_files_size += item.stat().st_size
            if lib_files_size > 0:
                components["lib/*.{so,dylib,a} (libraries)"] = lib_files_size

        # Python stdlib (lib/pythonX.Y/)
        stdlib_dir = self.prefix / "lib" / self.name_ver
        if stdlib_dir.exists():
            # Calculate stdlib without lib-dynload
            stdlib_size = 0
            lib_dynload_dir = stdlib_dir / "lib-dynload"

            for item in stdlib_dir.rglob("*"):
                if item.is_file():
                    # Skip lib-dynload, we count it separately
                    try:
                        item.relative_to(lib_dynload_dir)
                    except ValueError:
                        stdlib_size += item.stat().st_size

            components["lib/pythonX.Y/ (stdlib)"] = stdlib_size

            # lib-dynload (dynamically loaded modules)
            if lib_dynload_dir.exists():
                components["lib/pythonX.Y/lib-dynload/"] = get_dir_size(lib_dynload_dir)

        # Check for zipped stdlib
        zip_path = self.prefix / "lib" / f"python{self.ver.replace('.', '')}.zip"
        if zip_path.exists():
            components["pythonXY.zip (zipped stdlib)"] = zip_path.stat().st_size

        # Include directory
        include_dir = self.prefix / "include"
        if include_dir.exists():
            components["include/ (headers)"] = get_dir_size(include_dir)

        # Share directory (usually man pages, etc.)
        share_dir = self.prefix / "share"
        if share_dir.exists():
            components["share/ (docs/man)"] = get_dir_size(share_dir)

        # Framework-specific (macOS)
        if self.build_type == "framework":
            resources_dir = self.prefix / "Resources"
            if resources_dir.exists():
                components["Resources/"] = get_dir_size(resources_dir)

        # Calculate total
        total_size = get_dir_size(self.prefix)

        # Print the report
        print("\n" + "=" * 70)
        print("BUILD SIZE REPORT")
        print("=" * 70)

        print("\n[Build Info]")
        print(f"  Location:      {self.prefix}")
        print(f"  Configuration: {self.config}")
        print(f"  Build type:    {self.build_type}")
        print(f"  Python:        {self.version}")

        print("\n[Size Breakdown]")
        print(f"  {'Component':<40} {'Size':>12} {'%':>8}")
        print(f"  {'-' * 40} {'-' * 12} {'-' * 8}")

        # Sort by size descending
        sorted_components = sorted(components.items(), key=lambda x: x[1], reverse=True)

        for name, size in sorted_components:
            pct = (size / total_size * 100) if total_size > 0 else 0
            print(f"  {name:<40} {format_size(size):>12} {pct:>7.1f}%")

        # Other (unaccounted)
        accounted = sum(components.values())
        other = total_size - accounted
        if other > 0:
            pct = (other / total_size * 100) if total_size > 0 else 0
            print(f"  {'(other)':<40} {format_size(other):>12} {pct:>7.1f}%")

        print(f"  {'-' * 40} {'-' * 12} {'-' * 8}")
        print(f"  {'TOTAL':<40} {format_size(total_size):>12} {'100.0%':>8}")

        # Top 10 largest files
        print("\n[Largest Files]")
        all_files: list[tuple[Path, int]] = []
        for item in self.prefix.rglob("*"):
            if item.is_file():
                all_files.append((item, item.stat().st_size))

        all_files.sort(key=lambda x: x[1], reverse=True)

        print(f"  {'File':<50} {'Size':>12}")
        print(f"  {'-' * 50} {'-' * 12}")
        for filepath, size in all_files[:10]:
            try:
                rel_path = filepath.relative_to(self.prefix)
            except ValueError:
                rel_path = filepath
            name = str(rel_path)
            if len(name) > 48:
                name = "..." + name[-45:]
            print(f"  {name:<50} {format_size(size):>12}")

        print("\n" + "=" * 70 + "\n")

    # Comprehensive list of stdlib module names (top-level)
    # This covers Python 3.11-3.14
    STDLIB_MODULES: set[str] = {
        # Built-in modules (always available)
        "abc",
        "aifc",
        "argparse",
        "array",
        "ast",
        "asyncio",
        "atexit",
        "base64",
        "bdb",
        "binascii",
        "bisect",
        "builtins",
        "bz2",
        "calendar",
        "cgi",
        "cgitb",
        "chunk",
        "cmath",
        "cmd",
        "code",
        "codecs",
        "codeop",
        "collections",
        "colorsys",
        "compileall",
        "concurrent",
        "configparser",
        "contextlib",
        "contextvars",
        "copy",
        "copyreg",
        "cProfile",
        "crypt",
        "csv",
        "ctypes",
        "curses",
        "dataclasses",
        "datetime",
        "dbm",
        "decimal",
        "difflib",
        "dis",
        "doctest",
        "email",
        "encodings",
        "enum",
        "errno",
        "faulthandler",
        "fcntl",
        "filecmp",
        "fileinput",
        "fnmatch",
        "fractions",
        "ftplib",
        "functools",
        "gc",
        "getopt",
        "getpass",
        "gettext",
        "glob",
        "graphlib",
        "grp",
        "gzip",
        "hashlib",
        "heapq",
        "hmac",
        "html",
        "http",
        "idlelib",
        "imaplib",
        "imghdr",
        "importlib",
        "inspect",
        "io",
        "ipaddress",
        "itertools",
        "json",
        "keyword",
        "lib2to3",
        "linecache",
        "locale",
        "logging",
        "lzma",
        "mailbox",
        "mailcap",
        "marshal",
        "math",
        "mimetypes",
        "mmap",
        "modulefinder",
        "multiprocessing",
        "netrc",
        "nis",
        "nntplib",
        "numbers",
        "operator",
        "optparse",
        "os",
        "ossaudiodev",
        "pathlib",
        "pdb",
        "pickle",
        "pickletools",
        "pipes",
        "pkgutil",
        "platform",
        "plistlib",
        "poplib",
        "posix",
        "posixpath",
        "pprint",
        "profile",
        "pstats",
        "pty",
        "pwd",
        "py_compile",
        "pyclbr",
        "pydoc",
        "queue",
        "quopri",
        "random",
        "re",
        "readline",
        "reprlib",
        "resource",
        "rlcompleter",
        "runpy",
        "sched",
        "secrets",
        "select",
        "selectors",
        "shelve",
        "shlex",
        "shutil",
        "signal",
        "site",
        "smtpd",
        "smtplib",
        "sndhdr",
        "socket",
        "socketserver",
        "spwd",
        "sqlite3",
        "ssl",
        "stat",
        "statistics",
        "string",
        "stringprep",
        "struct",
        "subprocess",
        "sunau",
        "symtable",
        "sys",
        "sysconfig",
        "syslog",
        "tabnanny",
        "tarfile",
        "telnetlib",
        "tempfile",
        "termios",
        "test",
        "textwrap",
        "threading",
        "time",
        "timeit",
        "tkinter",
        "token",
        "tokenize",
        "tomllib",
        "trace",
        "traceback",
        "tracemalloc",
        "tty",
        "turtle",
        "turtledemo",
        "types",
        "typing",
        "unicodedata",
        "unittest",
        "urllib",
        "uu",
        "uuid",
        "venv",
        "warnings",
        "wave",
        "weakref",
        "webbrowser",
        "winreg",
        "winsound",
        "wsgiref",
        "xdrlib",
        "xml",
        "xmlrpc",
        "zipapp",
        "zipfile",
        "zipimport",
        "zlib",
        "zoneinfo",
        # Private/internal modules that map to C extensions
        "_abc",
        "_asyncio",
        "_bisect",
        "_blake2",
        "_bz2",
        "_codecs",
        "_collections",
        "_contextvars",
        "_csv",
        "_ctypes",
        "_datetime",
        "_decimal",
        "_elementtree",
        "_functools",
        "_hashlib",
        "_heapq",
        "_io",
        "_json",
        "_locale",
        "_lsprof",
        "_lzma",
        "_md5",
        "_multibytecodec",
        "_multiprocessing",
        "_opcode",
        "_operator",
        "_pickle",
        "_posixshmem",
        "_posixsubprocess",
        "_queue",
        "_random",
        "_sha1",
        "_sha256",
        "_sha512",
        "_sha3",
        "_signal",
        "_socket",
        "_sqlite3",
        "_sre",
        "_ssl",
        "_stat",
        "_statistics",
        "_struct",
        "_symtable",
        "_thread",
        "_tracemalloc",
        "_typing",
        "_uuid",
        "_weakref",
        "_zoneinfo",
    }

    # Map of stdlib modules to the C extension modules they require
    # Includes transitive dependencies (e.g., inspect -> dis -> opcode -> _opcode)
    STDLIB_TO_EXTENSION: dict[str, list[str]] = {
        "hashlib": [
            "_hashlib",
            "_md5",
            "_sha1",
            "_sha256",
            "_sha512",
            "_sha3",
            "_blake2",
        ],
        "ssl": ["_ssl"],
        "sqlite3": ["_sqlite3"],
        "json": ["_json"],
        "pickle": ["_pickle"],
        "datetime": ["_datetime"],
        "decimal": ["_decimal"],
        "ctypes": ["_ctypes"],
        "lzma": ["_lzma"],
        "bz2": ["_bz2"],
        "zlib": ["zlib"],
        "xml": ["_elementtree", "pyexpat"],
        "csv": ["_csv"],
        "asyncio": ["_asyncio"],
        "multiprocessing": ["_multiprocessing", "_posixshmem"],
        "collections": ["_collections"],
        "functools": ["_functools"],
        "itertools": ["itertools"],
        "math": ["math", "cmath"],
        "struct": ["_struct"],
        "array": ["array"],
        "select": ["select"],
        "socket": ["_socket"],
        "unicodedata": ["unicodedata"],
        "binascii": ["binascii"],
        "mmap": ["mmap"],
        "fcntl": ["fcntl"],
        "grp": ["grp"],
        "pwd": ["pwd"],
        "readline": ["readline"],
        "uuid": ["_uuid"],
        "statistics": ["_statistics"],
        "typing": ["_typing"],
        # Transitive dependencies
        "inspect": ["_opcode"],  # inspect -> dis -> opcode -> _opcode
        "dis": ["_opcode"],  # dis -> opcode -> _opcode
        "subprocess": ["_posixsubprocess", "select", "fcntl"],  # POSIX subprocess
        "random": ["_random"],
        "heapq": ["_heapq"],
        "bisect": ["_bisect"],
        "contextvars": ["_contextvars"],
        "zoneinfo": ["_zoneinfo"],
    }

    # Core modules that should never be disabled
    CORE_MODULES: set[str] = {
        "_abc",
        "_io",
        "_sre",
        "_codecs",
        "_collections",
        "_functools",
        "_locale",
        "_operator",
        "_signal",
        "_stat",
        "_symtable",
        "_thread",
        "_tracemalloc",
        "_weakref",
        "atexit",
        "errno",
        "faulthandler",
        "itertools",
        "posix",
        "pwd",
        "time",
        # zlib is required for decompressing the zipped stdlib
        "zlib",
    }

    def _extract_imports(self, source_code: str) -> set[str]:
        """Extract all imported module names from Python source code."""
        import ast

        imports: set[str] = set()
        try:
            tree = ast.parse(source_code)
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        # Get top-level module name
                        imports.add(alias.name.split(".")[0])
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        imports.add(node.module.split(".")[0])
        except SyntaxError:
            pass  # Skip files that can't be parsed
        return imports

    def _analyze_package_deps(self, verbose: bool = True) -> Optional[AnalysisResult]:
        """Analyze stdlib dependencies of packages specified via -i/--install.

        Downloads packages, extracts them, analyzes Python files for imports,
        and returns structured analysis results.

        Args:
            verbose: If True, print progress messages during analysis.

        Returns:
            AnalysisResult with analysis data, or None if no packages specified.
        """
        import tempfile

        if not self.pkgs:
            if verbose:
                print(
                    "\nError: No packages specified. Use -i/--install to specify packages."
                )
                print("Example: buildpy -A -i requests numpy")
            return None

        if verbose:
            print("\n[Packages to Analyze]")
            for pkg in self.pkgs:
                print(f"  - {pkg}")

        # Create temp directory for downloads
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)

            if verbose:
                print("\n[Downloading Packages]")

            # Use pip download to get packages
            # Try multiple pip options: pip3, pip, or python -m pip
            pip_commands = [
                ["pip3", "download", "--no-deps", "-d", str(tmppath)],
                ["pip", "download", "--no-deps", "-d", str(tmppath)],
                [
                    sys.executable,
                    "-m",
                    "pip",
                    "download",
                    "--no-deps",
                    "-d",
                    str(tmppath),
                ],
            ]

            download_success = False
            for pip_cmd in pip_commands:
                try:
                    result = subprocess.run(
                        pip_cmd + list(self.pkgs),
                        capture_output=True,
                        text=True,
                    )
                    if result.returncode == 0:
                        download_success = True
                        break
                except FileNotFoundError:
                    continue
                except Exception:
                    continue

            if not download_success and verbose:
                print("  Warning: Could not download packages (pip not available)")
                print("  Attempting analysis without downloading...")

            # Find all downloaded files
            all_imports: set[str] = set()
            files_analyzed = 0

            for archive in tmppath.glob("*"):
                if verbose:
                    print(f"  Analyzing: {archive.name}")

                # Extract and analyze
                if archive.suffix == ".whl" or archive.name.endswith(".whl"):
                    # Wheel files are zip files
                    try:
                        with zipfile.ZipFile(archive) as zf:
                            for name in zf.namelist():
                                if name.endswith(".py"):
                                    try:
                                        content = zf.read(name).decode(
                                            "utf-8", errors="ignore"
                                        )
                                        imports = self._extract_imports(content)
                                        all_imports.update(imports)
                                        files_analyzed += 1
                                    except Exception:
                                        pass
                    except Exception as e:
                        if verbose:
                            print(f"    Could not analyze {archive.name}: {e}")

                elif archive.suffix == ".gz" and ".tar" in archive.name:
                    # Tarball
                    try:
                        with tarfile.open(archive) as tf:
                            for member in tf.getmembers():
                                if member.name.endswith(".py"):
                                    try:
                                        f = tf.extractfile(member)
                                        if f:
                                            content = f.read().decode(
                                                "utf-8", errors="ignore"
                                            )
                                            imports = self._extract_imports(content)
                                            all_imports.update(imports)
                                            files_analyzed += 1
                                    except Exception:
                                        pass
                    except Exception as e:
                        if verbose:
                            print(f"    Could not analyze {archive.name}: {e}")

            if verbose:
                print(f"\n  Files analyzed: {files_analyzed}")

        # Filter to stdlib modules only
        stdlib_imports = all_imports & self.STDLIB_MODULES
        third_party = all_imports - self.STDLIB_MODULES

        # Get required C extension modules
        required_extensions: set[str] = set()
        for mod in stdlib_imports:
            if mod in self.STDLIB_TO_EXTENSION:
                required_extensions.update(self.STDLIB_TO_EXTENSION[mod])
            # Also check if the import is directly a C extension
            if mod.startswith("_"):
                required_extensions.add(mod)

        # Compare with current config
        config = self.get_config()
        getattr(config, self.config)()

        current_static = set(config.cfg["static"])
        current_shared = set(config.cfg["shared"])
        current_disabled = set(config.cfg["disabled"])
        current_enabled = current_static | current_shared | set(config.cfg["core"])

        # Find modules that could potentially be disabled (excluding core)
        potentially_unused = current_enabled - required_extensions - self.CORE_MODULES

        # Find modules that are needed but disabled
        needed_but_disabled = required_extensions & current_disabled

        return AnalysisResult(
            stdlib_imports=stdlib_imports,
            third_party=third_party,
            required_extensions=required_extensions,
            needed_but_disabled=needed_but_disabled,
            potentially_unused=potentially_unused,
            files_analyzed=files_analyzed,
        )

    def analyze_deps(self) -> None:
        """Analyze stdlib dependencies of packages specified via -i/--install.

        Downloads packages, extracts them, analyzes Python files for imports,
        and reports which stdlib modules are required. Suggests config optimizations.
        """
        print("\n" + "=" * 70)
        print("DEPENDENCY ANALYSIS")
        print("=" * 70)

        result = self._analyze_package_deps(verbose=True)
        if result is None:
            return

        print(f"\n[Stdlib Modules Used] ({len(result.stdlib_imports)})")
        for mod in sorted(result.stdlib_imports):
            ext_note = ""
            if mod in self.STDLIB_TO_EXTENSION:
                ext_note = f" -> {', '.join(self.STDLIB_TO_EXTENSION[mod])}"
            print(f"  {mod}{ext_note}")

        if result.third_party:
            print(f"\n[Third-Party Dependencies] ({len(result.third_party)})")
            for mod in sorted(result.third_party):
                print(f"  {mod}")

        # Get config info for display
        config = self.get_config()
        getattr(config, self.config)()
        current_static = set(config.cfg["static"])
        current_shared = set(config.cfg["shared"])
        current_enabled = current_static | current_shared | set(config.cfg["core"])

        print("\n[Configuration Analysis]")
        print(f"  Current config:     {self.config}")
        print(f"  Enabled modules:    {len(current_enabled)}")
        print(f"  Required by pkgs:   {len(result.required_extensions)}")

        if result.needed_but_disabled:
            print("\n[WARNING: Required modules are DISABLED]")
            for mod in sorted(result.needed_but_disabled):
                print(f"  {mod} - NEEDS TO BE ENABLED")

        if result.potentially_unused:
            print(f"\n[Potentially Unused Modules] ({len(result.potentially_unused)})")
            print("  These modules are enabled but may not be needed:")
            for mod in sorted(result.potentially_unused)[:20]:  # Show first 20
                print(f"  {mod}")
            if len(result.potentially_unused) > 20:
                print(f"  ... and {len(result.potentially_unused) - 20} more")

        # Suggest a minimal config
        print("\n[Recommendations]")
        if result.needed_but_disabled:
            print("  1. Enable these disabled modules for your packages to work:")
            for mod in sorted(result.needed_but_disabled):
                print(f"     --cfg-opts enable_{mod.lstrip('_')}")

        if len(result.potentially_unused) > 10:
            print(f"  2. Consider using a smaller config (e.g., {self.build_type}_min)")
            print("     or create a custom config disabling unused modules")

        if not result.needed_but_disabled and len(result.potentially_unused) <= 5:
            print(
                "  Your current configuration appears well-suited for these packages."
            )

        print("\n" + "=" * 70)
        print("Note: This analysis is based on static import detection.")
        print("Runtime imports (importlib, __import__) may not be detected.")
        print("=" * 70 + "\n")

    def auto_configure(
        self,
        output_path: Optional[Pathlike] = None,
    ) -> Optional[Path]:
        """Generate a reduction manifest based on dependency analysis.

        Instead of modifying Setup.local (which breaks ensurepip), this generates
        a manifest of files to remove post-build. The reduction is applied after
        the build completes, before the stdlib is compressed.

        Args:
            output_path: Path for output manifest. Defaults to reduction-manifest.json

        Returns:
            Path to the generated manifest file, or None if analysis failed.
        """
        print("\n" + "=" * 70)
        print("GENERATING REDUCTION MANIFEST")
        print("=" * 70)

        result = self._analyze_package_deps(verbose=True)
        if result is None:
            return None

        # Build the reduction manifest
        # These are modules that are enabled but not required by the analyzed packages
        extensions_to_remove: list[str] = []
        for mod in result.potentially_unused:
            # Never remove core modules
            if mod in self.CORE_MODULES:
                continue
            extensions_to_remove.append(mod)

        # Map extension modules to their file patterns in lib-dynload/
        # Extension files are typically named: _module.cpython-3XX-platform.so
        extension_patterns: list[str] = []
        for mod in extensions_to_remove:
            # Handle both _module and module naming
            extension_patterns.append(f"{mod}.cpython-*.so")
            extension_patterns.append(f"{mod}.*.so")

        # Identify pure Python stdlib modules that can be removed
        # Map of stdlib imports to their directory/file in lib/pythonX.Y/
        stdlib_module_paths: dict[str, list[str]] = {
            "tkinter": ["tkinter/", "turtle.py", "turtledemo/"],
            "idlelib": ["idlelib/"],
            "test": ["test/"],
            "lib2to3": ["lib2to3/"],
            "ensurepip": [],  # Never remove - needed for pip installation
            "distutils": ["distutils/"],
            "curses": ["curses/"],
            "dbm": ["dbm/"],
            "multiprocessing": ["multiprocessing/"],
            "concurrent": ["concurrent/"],
            "asyncio": ["asyncio/"],
            "email": ["email/"],
            "html": ["html/"],
            "http": ["http/"],
            "json": ["json/"],
            "logging": ["logging/"],
            "unittest": ["unittest/"],
            "urllib": ["urllib/"],
            "xml": ["xml/"],
            "xmlrpc": ["xmlrpc/"],
            "ctypes": ["ctypes/"],
            "sqlite3": ["sqlite3/"],
            "pydoc_data": ["pydoc_data/"],
        }

        # Determine which stdlib paths can be removed
        stdlib_to_remove: list[str] = []
        required_stdlib = result.stdlib_imports | {"ensurepip", "pip", "setuptools"}

        for mod, paths in stdlib_module_paths.items():
            if mod not in required_stdlib and paths:
                stdlib_to_remove.extend(paths)

        # Build the manifest
        warnings_list: list[dict[str, Any]] = []

        # Add warnings for modules that are needed but might be disabled
        if result.needed_but_disabled:
            warnings_list.append(
                {
                    "type": "required_but_disabled",
                    "message": "These modules are required but disabled in current config",
                    "modules": sorted(result.needed_but_disabled),
                }
            )

        manifest: dict[str, Any] = {
            "version": "1.0",
            "python_version": self.version,
            "config": self.config,
            "packages_analyzed": list(self.pkgs) if self.pkgs else [],
            "analysis": {
                "required_extensions": sorted(result.required_extensions),
                "stdlib_imports": sorted(result.stdlib_imports),
                "third_party": sorted(result.third_party),
            },
            "reductions": {
                "extensions_to_remove": sorted(extensions_to_remove),
                "extension_patterns": sorted(set(extension_patterns)),
                "stdlib_to_remove": sorted(set(stdlib_to_remove)),
            },
            "warnings": warnings_list,
        }

        # Determine output path
        if output_path is None:
            output_file = Path.cwd() / "reduction-manifest.json"
        else:
            output_file = Path(output_path)
            output_file.parent.mkdir(parents=True, exist_ok=True)

        # Write the manifest
        with open(output_file, "w") as f:
            json.dump(manifest, f, indent=2)

        # Print summary
        print("\n[Analysis Summary]")
        print(f"  Packages analyzed:     {len(self.pkgs) if self.pkgs else 0}")
        print(f"  Required extensions:   {len(result.required_extensions)}")
        print(f"  Removable extensions:  {len(extensions_to_remove)}")
        print(f"  Removable stdlib dirs: {len(stdlib_to_remove)}")

        if result.needed_but_disabled:
            print("\n[WARNING] Required modules are DISABLED in config:")
            for mod in sorted(result.needed_but_disabled):
                print(f"    {mod}")
            print("  Consider using a config that enables these modules.")

        print(f"\n[Removable Extensions] ({len(extensions_to_remove)})")
        for mod in sorted(extensions_to_remove)[:15]:
            print(f"    {mod}")
        if len(extensions_to_remove) > 15:
            print(f"    ... and {len(extensions_to_remove) - 15} more")

        print(f"\n[Removable Stdlib] ({len(stdlib_to_remove)})")
        for path in sorted(stdlib_to_remove)[:10]:
            print(f"    {path}")
        if len(stdlib_to_remove) > 10:
            print(f"    ... and {len(stdlib_to_remove) - 10} more")

        print("\n[Output]")
        print(f"  Manifest: {output_file}")

        print("\n[Next Steps]")
        print("  1. Build Python without zipping stdlib:")
        print(f"       buildpy -c {self.config} --skip-ziplib")
        print("  2. Apply reductions to the build:")
        print(f"       buildpy --apply-reductions {output_file}")
        print("  3. Compress the reduced stdlib:")
        print("       buildpy --ziplib")
        print("  Or apply to a copy for testing:")
        print(
            f"       buildpy --apply-reductions {output_file} --reduction-copy build/reduced"
        )
        print("       buildpy --ziplib --install-dir build/reduced")

        print("\n" + "=" * 70 + "\n")

        return output_file

    def apply_reductions(
        self,
        manifest_path: Pathlike,
        copy_to: Optional[Pathlike] = None,
    ) -> Optional[Path]:
        """Apply reduction manifest to remove unused files from build.

        This should be called after a successful build but before ziplib
        would be called on a fresh build. For existing builds, this removes
        files from lib-dynload/ and lib/pythonX.Y/.

        Args:
            manifest_path: Path to the reduction manifest JSON file.
            copy_to: If provided, copy the build to this directory first
                     and apply reductions to the copy (safer for testing).

        Returns:
            Path to the reduced build directory, or None on failure.
        """
        manifest_file = Path(manifest_path)
        if not manifest_file.exists():
            print(f"Error: Manifest file not found: {manifest_file}")
            return None

        with open(manifest_file) as f:
            manifest = json.load(f)

        print("\n" + "=" * 70)
        print("APPLYING REDUCTIONS")
        print("=" * 70)

        # Determine target directory
        if copy_to:
            target_prefix = Path(copy_to)
            print("\n[Copying Build]")
            print(f"  Source: {self.prefix}")
            print(f"  Target: {target_prefix}")

            if target_prefix.exists():
                print("  Removing existing target directory...")
                shutil.rmtree(target_prefix)

            shutil.copytree(self.prefix, target_prefix, symlinks=True)
            print("  Copy complete.")
        else:
            target_prefix = self.prefix
            print("\n[Target Build]")
            print(f"  {target_prefix}")

        # Determine lib paths
        lib_dir = target_prefix / "lib" / f"python{self.ver}"
        dynload_dir = lib_dir / "lib-dynload"

        if not lib_dir.exists():
            print(f"Error: Library directory not found: {lib_dir}")
            return None

        # Check if stdlib is already zipped
        zip_name = f"python{self.ver.replace('.', '')}.zip"
        zip_path = target_prefix / "lib" / zip_name
        stdlib_is_zipped = zip_path.exists()

        if stdlib_is_zipped:
            # Check if stdlib directories exist (not just os.py which is kept outside zip)
            # Exclude lib-dynload, site-packages
            stdlib_dirs = [
                d
                for d in lib_dir.iterdir()
                if d.is_dir()
                and d.name not in ("lib-dynload", "site-packages", "__pycache__")
            ]
            if len(stdlib_dirs) == 0:
                print("\n[WARNING] Stdlib appears to be zipped already!")
                print(f"  Found: {zip_path}")
                print("  Stdlib reductions will have no effect on zipped content.")
                print("  Rebuild with --skip-ziplib to apply stdlib reductions.")
                print("  Extension reductions may still work if using shared builds.")

        # Track what we remove
        removed_extensions = 0
        removed_stdlib = 0
        bytes_saved = 0

        # Remove extension modules from lib-dynload
        print("\n[Removing Extensions]")
        if dynload_dir.exists():
            for pattern in manifest["reductions"].get("extension_patterns", []):
                for ext_file in dynload_dir.glob(pattern):
                    if ext_file.is_file():
                        size = ext_file.stat().st_size
                        ext_file.unlink()
                        removed_extensions += 1
                        bytes_saved += size
                        self.log.debug(
                            "Removed extension: %s (%d bytes)", ext_file.name, size
                        )

        print(f"  Removed {removed_extensions} extension files")

        # Remove stdlib directories/files
        print("\n[Removing Stdlib Modules]")
        for rel_path in manifest["reductions"].get("stdlib_to_remove", []):
            target = lib_dir / rel_path
            if target.exists():
                if target.is_dir():
                    dir_size = sum(
                        p.stat().st_size for p in target.rglob("*") if p.is_file()
                    )
                    shutil.rmtree(target)
                    bytes_saved += dir_size
                    removed_stdlib += 1
                    self.log.debug(
                        "Removed directory: %s (%d bytes)", rel_path, dir_size
                    )
                else:
                    size = target.stat().st_size
                    target.unlink()
                    bytes_saved += size
                    removed_stdlib += 1
                    self.log.debug("Removed file: %s (%d bytes)", rel_path, size)

        print(f"  Removed {removed_stdlib} stdlib modules/directories")

        # Summary
        print("\n[Summary]")
        print(f"  Extensions removed: {removed_extensions}")
        print(f"  Stdlib removed:     {removed_stdlib}")
        print(f"  Space saved:        {bytes_saved / 1024 / 1024:.2f} MB")
        print(f"  Reduced build at:   {target_prefix}")

        print("\n[Testing]")
        test_python = target_prefix / "bin" / "python3"
        print(f'  Test with: {test_python} -c "import sys; print(sys.version)"')

        print("\n" + "=" * 70 + "\n")

        return target_prefix

    def auto_reduce(self) -> bool:
        """Automatic workflow: analyze deps, build, reduce, and compress.

        This combines the full reduction workflow into a single operation:
        1. Analyze package dependencies to determine required modules
        2. Build Python with shared_vanilla config (all modules as shared)
        3. Apply reductions to remove unused extensions and stdlib
        4. Compress the reduced stdlib

        Returns:
            True on success, False on failure.
        """
        print("\n" + "=" * 70)
        print("AUTO-REDUCE WORKFLOW")
        print("=" * 70)

        if not self.pkgs:
            print("\nError: --auto-reduce requires packages to analyze.")
            print("       Use -i/--install to specify packages, e.g.:")
            print("       buildpy -i ipython --auto-reduce")
            return False

        # Step 1: Analyze dependencies using shared_vanilla config
        # (since that's what we'll actually build)
        print("\n[Step 1/6] Analyzing package dependencies...")
        original_config = self.config
        self.config = "shared_vanilla"
        result = self._analyze_package_deps(verbose=False)
        self.config = original_config
        if result is None:
            print("Error: Dependency analysis failed.")
            return False

        print(f"  Packages: {', '.join(self.pkgs)}")
        print(f"  Required extensions: {len(result.required_extensions)}")
        print(f"  Potentially unused: {len(result.potentially_unused)}")

        # Generate reduction manifest in memory
        extensions_to_remove: list[str] = []
        for mod in result.potentially_unused:
            if mod not in self.CORE_MODULES:
                extensions_to_remove.append(mod)

        extension_patterns: list[str] = []
        for mod in extensions_to_remove:
            extension_patterns.append(f"{mod}.cpython-*.so")
            extension_patterns.append(f"{mod}.*.so")

        # Determine removable stdlib
        stdlib_module_paths: dict[str, list[str]] = {
            "tkinter": ["tkinter/", "turtle.py", "turtledemo/"],
            "idlelib": ["idlelib/"],
            "test": ["test/"],
            "lib2to3": ["lib2to3/"],
            "distutils": ["distutils/"],
            "curses": ["curses/"],
            "dbm": ["dbm/"],
            "multiprocessing": ["multiprocessing/"],
            "concurrent": ["concurrent/"],
            "asyncio": ["asyncio/"],
            "email": ["email/"],
            "html": ["html/"],
            "http": ["http/"],
            "json": ["json/"],
            "logging": ["logging/"],
            "unittest": ["unittest/"],
            "urllib": ["urllib/"],
            "xml": ["xml/"],
            "xmlrpc": ["xmlrpc/"],
            "ctypes": ["ctypes/"],
            "sqlite3": ["sqlite3/"],
            "pydoc_data": ["pydoc_data/"],
        }

        stdlib_to_remove: list[str] = []
        required_stdlib = result.stdlib_imports | {"ensurepip", "pip", "setuptools"}
        for mod, paths in stdlib_module_paths.items():
            if mod not in required_stdlib and paths:
                stdlib_to_remove.extend(paths)

        manifest: dict[str, Any] = {
            "reductions": {
                "extensions_to_remove": sorted(extensions_to_remove),
                "extension_patterns": sorted(set(extension_patterns)),
                "stdlib_to_remove": sorted(set(stdlib_to_remove)),
            }
        }

        # Step 2: Ensure vanilla build exists (cached) and copy for reduction
        print("\n[Step 2/6] Preparing vanilla build...")

        # Cache location for unreduced vanilla build
        vanilla_cache = self.project.install / "python-shared-vanilla"
        # Reduced build location (final output)
        reduced_prefix = self.project.install / "python-shared-reduced"

        # Build vanilla if not cached
        if not vanilla_cache.exists():
            print("  Building vanilla cache (first time only)...")
            print("  (All modules built as shared extensions)")

            # Switch to shared_vanilla config for the build
            original_config = self.config
            original_install_dir = self._install_dir
            self.config = "shared_vanilla"
            self._install_dir = vanilla_cache

            # Build without zipping and without installing packages
            # (keep self.pkgs so ensurepip is included in the build)
            original_skip_ziplib = self.skip_ziplib
            self.skip_ziplib = True
            self._skip_pkg_install = True

            try:
                self.process()
            except Exception as e:
                print(f"\nError during build: {e}")
                return False
            finally:
                self.config = original_config
                self._install_dir = original_install_dir
                self.skip_ziplib = original_skip_ziplib
                self._skip_pkg_install = False
        else:
            print(f"  Using cached vanilla build: {vanilla_cache}")

        # Copy vanilla cache to reduced location
        print(f"  Copying to: {reduced_prefix}")
        if reduced_prefix.exists():
            shutil.rmtree(reduced_prefix)
        shutil.copytree(vanilla_cache, reduced_prefix, symlinks=True)

        lib_dir = reduced_prefix / "lib" / f"python{self.ver}"
        site_packages = lib_dir / "site-packages"
        dynload_dir = lib_dir / "lib-dynload"

        # Install packages BEFORE reductions (while all modules available)
        # Then move them to temp so they're not zipped (extensions can't be in zips)
        pkg_temp_dir: Path | None = None
        if self.pkgs:
            print("\n[Step 3/6] Installing packages...")
            print(f"  Packages: {', '.join(self.pkgs)}")
            original_install_dir = self._install_dir
            self._install_dir = reduced_prefix
            try:
                self.install_pkgs()
            finally:
                self._install_dir = original_install_dir

            # Move installed packages to temp (preserve for after zipping)
            print("  Moving packages to temp (extensions can't be in zips)...")
            pkg_temp_dir = self.project.build / "pkg_temp"
            if pkg_temp_dir.exists():
                shutil.rmtree(pkg_temp_dir)
            if site_packages.exists():
                shutil.move(str(site_packages), str(pkg_temp_dir))
                print(f"  Moved to: {pkg_temp_dir}")
            else:
                print(f"  WARNING: site-packages not found at {site_packages}")
                pkg_temp_dir = None
            # Recreate empty site-packages for zipping
            site_packages.mkdir(exist_ok=True)

        # Step 4: Apply reductions to the copy
        print("\n[Step 4/6] Applying reductions...")

        removed_extensions = 0
        removed_stdlib = 0
        bytes_saved = 0

        # Remove extension modules
        if dynload_dir.exists():
            for pattern in manifest["reductions"].get("extension_patterns", []):
                for ext_file in dynload_dir.glob(pattern):
                    if ext_file.is_file():
                        size = ext_file.stat().st_size
                        ext_file.unlink()
                        removed_extensions += 1
                        bytes_saved += size

        print(f"  Extensions removed: {removed_extensions}")

        # Remove stdlib modules
        for rel_path in manifest["reductions"].get("stdlib_to_remove", []):
            target = lib_dir / rel_path
            if target.exists():
                if target.is_dir():
                    dir_size = sum(
                        p.stat().st_size for p in target.rglob("*") if p.is_file()
                    )
                    shutil.rmtree(target)
                    bytes_saved += dir_size
                    removed_stdlib += 1
                else:
                    size = target.stat().st_size
                    target.unlink()
                    bytes_saved += size
                    removed_stdlib += 1

        print(f"  Stdlib removed: {removed_stdlib}")
        print(f"  Space saved: {bytes_saved / 1024 / 1024:.2f} MB")

        # Step 5: Compress stdlib
        print("\n[Step 5/6] Compressing stdlib...")
        # Temporarily switch install_dir to reduced_prefix for ziplib
        original_install_dir = self._install_dir
        self._install_dir = reduced_prefix
        try:
            self.ziplib()
        finally:
            self._install_dir = original_install_dir

        # Step 6: Restore packages to site-packages (outside the zip)
        if pkg_temp_dir and pkg_temp_dir.exists():
            print("\n[Step 6/6] Restoring packages to site-packages...")
            print(f"  Source: {pkg_temp_dir}")
            # Remove the empty site-packages created by ziplib
            final_site_packages = lib_dir / "site-packages"
            if final_site_packages.exists():
                shutil.rmtree(final_site_packages)
            # Copy packages back (excluding pip/ensurepip cruft)
            shutil.copytree(pkg_temp_dir, final_site_packages, symlinks=True)
            # Clean up temp
            shutil.rmtree(pkg_temp_dir)
            # Remove pip and setuptools from site-packages (not needed at runtime)
            for pattern in [
                "pip",
                "pip-*",
                "setuptools",
                "setuptools-*",
                "_distutils_hack",
            ]:
                for item in final_site_packages.glob(pattern):
                    if item.is_dir():
                        shutil.rmtree(item)
                    else:
                        item.unlink()
            # List what was restored
            restored = [
                p.name
                for p in final_site_packages.iterdir()
                if not p.name.startswith(".")
            ]
            print(f"  Packages restored: {', '.join(restored)}")
        elif self.pkgs:
            print("\n[Step 6/6] WARNING: No packages to restore (pkg_temp missing)")

        # Summary
        print("\n" + "=" * 70)
        print("AUTO-REDUCE COMPLETE")
        print("=" * 70)
        print(f"\n  Python version:     {self.version}")
        print(f"  Packages analyzed:  {', '.join(self.pkgs)}")
        print(f"  Extensions removed: {removed_extensions}")
        print(f"  Stdlib removed:     {removed_stdlib}")
        print(f"  Space saved:        {bytes_saved / 1024 / 1024:.2f} MB")
        print(f"  Vanilla cache:      {vanilla_cache}")
        print(f"  Reduced build:      {reduced_prefix}")

        # Verify the build works by importing installed packages
        print("\n[Verification]")
        test_python = reduced_prefix / "bin" / "python3"
        verification_passed = True

        if self.pkgs:
            for pkg in self.pkgs:
                # Get the import name (some packages have different import names)
                import_name = pkg.split("[")[0].replace("-", "_").lower()
                try:
                    import_result = subprocess.run(
                        [str(test_python), "-c", f"import {import_name}"],
                        capture_output=True,
                        text=True,
                        timeout=30,
                    )
                    if import_result.returncode == 0:
                        print(f"  import {import_name}: OK")
                    else:
                        print(f"  import {import_name}: FAILED")
                        print(f"    {import_result.stderr.strip().split(chr(10))[-1]}")
                        verification_passed = False
                except subprocess.TimeoutExpired:
                    print(f"  import {import_name}: TIMEOUT")
                    verification_passed = False
                except Exception as e:
                    print(f"  import {import_name}: ERROR ({e})")
                    verification_passed = False

        if not verification_passed:
            print(
                "\n  WARNING: Some imports failed. The build may be missing required modules."
            )

        print("\n" + "=" * 70 + "\n")
        return verification_passed

    def _compute_loader_path(self, dylib_path: Path) -> str:
        """Compute @loader_path for install_name_tool based on install_dir

        @loader_path refers to the directory containing the loading binary (the embedding app).
        We need to compute the path from a typical embedding location to the framework dylib.

        Standard patterns:
        - install_dir = project.install: embedding app in install/Resources/
          -> @loader_path/../Python.framework/Versions/{ver}/Python
        - install_dir = project.support: embedding app in project root (4 levels up from support)
          -> @loader_path/support/Python.framework/Versions/{ver}/Python

        Args:
            dylib_path: The path to the dylib whose install_name_id we're setting

        Returns:
            A string suitable for use with install_name_tool (e.g., "@loader_path/../../...")
        """
        try:
            # Compute relative path from project.root to install_dir
            rel_from_root = self._install_dir.relative_to(self.project.root)

            if self._install_dir == self.project.install:
                # Standard install: embedding app assumed to be in install/Resources/
                # Path: Resources -> .. -> Python.framework/...
                return f"@loader_path/../Python.framework/Versions/{self.ver}/Python"
            elif self._install_dir == self.project.support:
                # Support directory: embedding app assumed to be in project root
                # Path: root -> support -> Python.framework/...
                return f"@loader_path/{rel_from_root}/Python.framework/Versions/{self.ver}/Python"
            else:
                # Custom install_dir: compute from project root
                # Assume embedding app is in project root
                return f"@loader_path/{rel_from_root}/Python.framework/Versions/{self.ver}/Python"
        except (ValueError, AttributeError) as e:
            # If we can't compute relative path, fall back to absolute path
            self.log.warning(
                "Could not compute relative loader_path: %s, using absolute path", e
            )
            return str(
                self._install_dir
                / "Python.framework"
                / "Versions"
                / self.ver
                / "Python"
            )

    @property
    def prefix(self) -> Path:
        """python builder prefix path"""
        if PLATFORM == "Darwin" and self.build_type == "framework":
            return self._install_dir / "Python.framework" / "Versions" / self.ver
        # If _install_dir was explicitly set (different from default), use it directly
        if self._install_dir != self.project.install:
            return self._install_dir
        name = self.name.lower() + "-" + self.build_type
        return self.project.install / name

    @property
    def executable(self) -> Path:
        """path to python3 executable"""
        return self.prefix / "bin" / "python3"

    @property
    def python(self) -> Path:
        """path to python3 executable"""
        return self.executable

    @property
    def pip(self) -> Path:
        """path to pip3 executable"""
        return self.prefix / "bin" / "pip3"

    def pre_process(self) -> None:
        """override by subclass if needed"""

    def setup(self) -> None:
        """setup build environment"""
        self.project.setup()
        if not self.archive_is_downloaded:
            archive = self.download(self.download_url, tofolder=self.project.downloads)
            self.log.info("downloaded %s", archive)
        else:
            archive = self.downloaded_archive
        if self.src_dir.exists():
            self.remove(self.src_dir)
        self.extract(archive, tofolder=self.project.src)
        if not self.src_dir.exists():
            raise ExtractionError(f"could not extract from {archive}")

    def configure(self) -> None:
        """configure build"""
        self.log.info(
            "Configuring Python %s (%s build)...", self.version, self.build_type
        )
        config = self.get_config()
        prefix = self.prefix

        if self.build_type == "shared":
            self.config_options.extend(
                ["--enable-shared", "--without-static-libpython"]
            )
        elif self.build_type == "framework":
            self.config_options.append(f"--enable-framework={self._install_dir}")
        elif self.build_type != "static":
            self.fail(f"{self.build_type} not recognized build type")

        if self.optimize:
            self.config_options.append("--enable-optimizations")

        if not self.pkgs and not self.required_packages:
            self.config_options.append("--without-ensurepip")
            self.remove_patterns.append("ensurepip")
        else:
            self.pkgs.extend(self.required_packages)

        if self.cfg_opts:
            for cfg_opt in self.cfg_opts:
                cfg_opt = cfg_opt.replace("_", "-")
                cfg_opt = "--" + cfg_opt
                if cfg_opt not in self.config_options:
                    self.config_options.append(cfg_opt)

        config.write(self.config, to=self.src_dir / "Modules" / "Setup.local")
        config_opts = " ".join(self.config_options)
        self.cmd(f"./configure --prefix={prefix} {config_opts}", cwd=self.src_dir)

    def build(self) -> None:
        """main build process"""
        self.log.info("Building Python %s (using %d jobs)...", self.version, self.jobs)
        self.cmd(f"make -j{self.jobs}", cwd=self.src_dir)
        self.log.info("Python %s build complete", self.version)

    def install(self) -> None:
        """install to prefix"""
        if self.prefix.exists():
            self.remove(self.prefix)
        self.cmd("make install", cwd=self.src_dir)

    def clean(self) -> None:
        """clean installed build"""
        self.glob_remove(
            self.prefix / "lib" / self.name_ver,
            self.remove_patterns,
            skip_dirs=[".git"],
        )

        bins = [
            "2to3",
            "idle3",
            f"idle{self.ver}",
            "pydoc3",
            f"pydoc{self.ver}",
            f"2to3-{self.ver}",
        ]
        for executable in bins:
            self.remove(self.prefix / "bin" / executable)

    def _get_lib_src_dir(self) -> Path:
        """Get the library source directory to zip (platform-specific)"""
        return self.prefix / "lib" / self.name_ver

    def _precompile_lib(self, src: Path) -> None:
        """Precompile library to bytecode and remove .py files"""
        self.cmd(
            f"{self.executable} -m compileall -f -b -o {self.optimize_bytecode} {src}",
            cwd=src.parent,
        )
        self.walk(
            src,
            match_func=lambda f: str(f).endswith(".py"),
            action_func=lambda f: self.remove(f),
            skip_patterns=[],
        )

    def _preserve_os_module(self, src: Path, is_compiled: bool) -> None:
        """Move os module to temp location before zipping"""
        if is_compiled:
            self.move(src / "os.pyc", self.project.build / "os.pyc")
        else:
            self.move(src / "os.py", self.project.build / "os.py")

    def _restore_os_module(self, src: Path, is_compiled: bool) -> None:
        """Restore os module after zipping"""
        if is_compiled:
            self.move(self.project.build / "os.pyc", src / "os.pyc")
        else:
            self.move(self.project.build / "os.py", src / "os.py")

    def _handle_lib_dynload(self, src: Path, preserve: bool = True) -> None:
        """Handle lib-dynload directory (Unix-specific)"""
        if preserve:
            # Move lib-dynload out before zipping
            self.move(src / "lib-dynload", self.project.build / "lib-dynload")
        else:
            # Restore lib-dynload after zipping
            self.move(self.project.build / "lib-dynload", src / "lib-dynload")

    def _get_zip_path(self) -> Path:
        """Get the path for the zip archive (platform-specific)"""
        return self.prefix / "lib" / f"python{self.ver_nodot}"

    def _cleanup_after_zip(self, src: Path) -> None:
        """Cleanup and recreate directory structure after zipping"""
        site_packages = src / "site-packages"
        self.remove(self.prefix / "lib" / "pkgconfig")
        src.mkdir()
        site_packages.mkdir()

    def ziplib(self) -> None:
        """Zip python library with optional precompilation

        Precompiles to bytecode by default to save compilation time, and drops .py
        source files to save space. Note that only same version interpreter can compile
        bytecode. Also can specify optimization levels of bytecode precompilation:
            -1 is system default optimization
            0 off
            1 drops asserts and __debug__ blocks
            2 same as 1 and discards docstrings (saves ~588K of compressed space)
        """
        src = self._get_lib_src_dir()
        should_compile = self.precompile or getenv("PRECOMPILE")

        # Platform-specific lib-dynload handling
        self._handle_lib_dynload(src, preserve=True)

        # Precompile if requested
        if should_compile:
            self._precompile_lib(src)
            self._preserve_os_module(src, is_compiled=True)
        else:
            self._preserve_os_module(src, is_compiled=False)

        # Create zip archive
        zip_path = self._get_zip_path()
        shutil.make_archive(str(zip_path), "zip", str(src))
        self.remove(src)

        # Cleanup and restore structure
        self._cleanup_after_zip(src)
        self._handle_lib_dynload(src, preserve=False)
        self._restore_os_module(src, is_compiled=should_compile)

    def install_pkgs(self) -> None:
        """install python packages"""
        pkgs = " ".join(self.pkgs)
        self.cmd(f"{self.python} -m ensurepip")
        self.cmd(f"{self.pip} install {pkgs}")

    def make_relocatable(self) -> None:
        """fix dylib/exe @rpath shared buildtype in macos"""
        if PLATFORM == "Darwin":
            if self.build_type == "shared":
                dylib = self.prefix / "lib" / self.dylib_name
                self.chmod(dylib)
                self.cmd(
                    f"install_name_tool -id @loader_path/../Resources/lib/{self.dylib_name} {dylib}"
                )
                to = f"@executable_path/../lib/{self.dylib_name}"
                exe = self.prefix / "bin" / self.name_ver
                self.cmd(f"install_name_tool -change {dylib} {to} {exe}")
            elif self.build_type == "framework":
                dylib = self.prefix / self.name
                self.chmod(dylib)

                # Use install_name_id from config if set, otherwise compute from install_dir
                config = self.get_config()
                if config.install_name_id:
                    _id = config.install_name_id
                else:
                    # Compute loader_path dynamically based on install_dir
                    _id = self._compute_loader_path(dylib)

                self.cmd(f"install_name_tool -id {_id} {dylib}")
                # changing executable
                to = "@executable_path/../Python"
                exe = self.prefix / "bin" / self.name_ver
                self.cmd(f"install_name_tool -change {dylib} {to} {exe}")
                # changing app
                to = "@executable_path/../../../../Python"
                app = (
                    self.prefix
                    / "Resources"
                    / "Python.app"
                    / "Contents"
                    / "MacOS"
                    / "Python"
                )
                self.cmd(f"install_name_tool -change {dylib} {to} {app}")
        elif PLATFORM == "Linux":
            if self.build_type == "shared":
                exe = self.prefix / "bin" / self.name_ver
                self.cmd(f"patchelf --set-rpath '$ORIGIN'/../lib {exe}")

    def validate_build(self) -> bool:
        """Validate built Python with smoke tests

        Returns:
            True if validation passes, False otherwise
        """
        if not self.executable.exists():
            self.log.error("Python executable not found: %s", self.executable)
            return False

        try:
            # Test 1: Check version
            version_output = self.get(f"{self.executable} --version")
            self.log.info("Python version: %s", version_output)

        except Exception as e:
            self.log.error("Build validation failed: %s", e)
            return False

        return True

    def post_process(self) -> None:
        """override by subclass if needed"""
        if self.build_type in ["shared", "framework"]:
            self.make_relocatable()

        # Validate the build
        if not self.validate_build():
            self.log.warning("Build validation failed, but continuing")

        self.log.info("%s DONE", self.config)

    def _get_build_cache_key(self) -> str:
        """Generate cache key for build artifact"""
        import hashlib

        # Include version, build type, and config in cache key
        key_data = f"{self.version}:{self.build_type}:{self.config}"
        return hashlib.md5(key_data.encode()).hexdigest()[:8]

    def _is_build_cached(self) -> bool:
        """Check if build artifacts are cached and valid"""
        # Check if primary artifacts exist
        if self.build_type == "static":
            if not self.staticlib.exists():
                return False
        else:
            if not self.dylib.exists():
                return False

        # Check if executable exists
        if not self.executable.exists():
            return False

        # All required artifacts exist
        self.log.info(
            "Found cached build for Python %s (%s)", self.version, self.build_type
        )
        return True

    def can_run(self) -> bool:
        """check if a run is merited"""
        # Check if dependencies are built
        for dep_class in self.depends_on:
            dep = dep_class()
            if not dep.lib_products_exist():
                self.log.debug("Dependency %s not built", dep.name)
                return True

        # Check if our build is cached
        if self._is_build_cached():
            return False

        self.log.debug("Build artifacts not found or incomplete")
        return True

    def process(self) -> None:
        """main builder process"""
        if not self.can_run():
            self.log.info("everything built: skipping run")
            return

        self.log.info("found unbuilt dependencies, proceeding with run")
        # run build process
        for dependency_class in self.depends_on:
            dependency_class().process()
        self.pre_process()
        self.setup()
        self.configure()
        self.build()
        self.install()
        self.clean()
        if self.skip_ziplib:
            self.log.info("skipping ziplib (--skip-ziplib specified)")
        else:
            self.ziplib()
        if self.pkgs and not getattr(self, "_skip_pkg_install", False):
            self.install_pkgs()
        self.post_process()


class PythonDebugBuilder(PythonBuilder):
    """Builds debug python locally"""

    name = "python"

    config_options = [
        "--disable-test-modules",
        "--without-static-libpython",
        "--with-pydebug",
        # "--with-trace-refs",
        # "--with-valgrind",
        # "--with-address-sanitizer",
        # "--with-memory-sanitizer",
        # "--with-undefined-behavior-sanitizer",
    ]

    required_packages = []


class WindowsEmbeddablePythonBuilder(Builder):
    """Downloads embeddable windows python"""

    name = "Python"
    version = DEFAULT_PY_VERSION
    repo_url = "https://github.com/python/cpython.git"

    download_archive_template = "python-{ver}-embed-amd64.zip"
    download_url_template = "https://www.python.org/ftp/python/{ver}/{archive}"
    depends_on: list[type["Builder"]] = []
    lib_products: list[str] = []

    @property
    def install_dir(self) -> Path:
        """return folder where binaries are installed"""
        return self.project.support

    def setup(self) -> None:
        """setup build environment"""
        if self.project.support.exists():
            self.remove(self.project.support)
        self.project.setup()
        self.makedirs(self.project.support)
        archive = self.download(self.download_url, tofolder=self.project.downloads)
        self.extract(archive, tofolder=self.install_dir)


class WindowsPythonBuilder(PythonBuilder):
    """class for building python from source on windows"""

    config_options: list[str] = [
        # "--disable-gil",
        # "--no-ctypes",
        # "--no-ssl",
        "--no-tkinter",
    ]

    remove_patterns: list[str] = [
        "*.pdb",
        "*.exp",
        "_test*",
        "xx*",
        "py.exe",
        "pyw.exe",
        "pythonw.exe",
        "venvlauncher.exe",
        "venvwlauncher.exe",
        "_ctypes_test*",
        "LICENSE.txt",
        "*tcl*",
        "*tdbc*",
        "*tk*",
        "__phello__",
        "__pycache__",
        "_tk*",
        "ensurepip",
        "idlelib",
        "LICENSE.txt",
        "pydoc*",
        "test",
        "Tk*",
        "turtle*",
        "venv",
    ]

    depends_on = []

    def _get_lib_src_dir(self) -> Path:
        """Windows uses 'Lib' instead of 'lib/pythonX.Y'"""
        return self.prefix / "Lib"

    def _precompile_lib(self, src: Path) -> None:
        """Windows-specific precompilation (different path handling)"""
        self.cmd(
            f"{self.executable} -m compileall -f -b -o {self.optimize_bytecode} Lib",
            cwd=self.prefix,
        )
        self.walk(
            src,
            match_func=lambda f: str(f).endswith(".py"),
            action_func=lambda f: self.remove(f),
            skip_patterns=[],
        )

    def _handle_lib_dynload(self, src: Path, preserve: bool = True) -> None:
        """Windows doesn't have lib-dynload directory"""
        pass

    def _preserve_os_module(self, src: Path, is_compiled: bool) -> None:
        """Windows doesn't preserve os module separately"""
        pass

    def _restore_os_module(self, src: Path, is_compiled: bool) -> None:
        """Windows doesn't restore os module"""
        pass

    def _cleanup_after_zip(self, src: Path) -> None:
        """Windows doesn't need cleanup after zip"""
        pass

    def _get_zip_path(self) -> Path:
        """Windows zip path uses different location"""
        return self.prefix / self.name_ver_nodot

    @property
    def build_type(self) -> str:
        """build type: 'static', 'shared' or 'framework'"""
        return self.config.split("_")[0]

    @property
    def size_type(self) -> str:
        """size qualifier: 'max', 'mid', 'min', etc.."""
        return self.config.split("_")[1]

    @property
    def prefix(self) -> Path:
        """python builder prefix path"""
        # Use the configured install_dir from parent class
        return self._install_dir

    @property
    def libname(self) -> str:
        """library name suffix"""
        return f"{self.name_ver_nodot}"

    @property
    def dylib(self) -> Path:
        """dylib path"""
        return self.prefix / self.dylib_name

    @property
    def executable(self) -> Path:
        """executable path of buld target"""
        return self.prefix / "python.exe"

    @property
    def pip(self) -> Path:
        """path to pip3 executable"""
        return self.prefix / "pip.exe"

    @property
    def pth(self) -> str:
        """syspath modifier"""
        return f"{self.name_ver_nodot}._pth"

    @property
    def binary_dir(self) -> Path:
        """path to folder in python source where windows binaries are built"""
        return self.src_dir / "PCbuild" / "amd64"

    @property
    def pyconfig_h(self) -> Path:
        """path to generated pyconfig.h header"""
        _path = self.binary_dir / "pyconfig.h"
        if _path.exists():
            return _path
        raise IOError("pyconfig.h not found")

    def pre_process(self) -> None:
        """override by subclass if needed"""

    def can_run(self) -> bool:
        """return true if a build or re-build is merited"""
        return not self.dylib.exists()

    def setup(self) -> None:
        """setup build environment"""
        self.project.setup()
        if not self.archive_is_downloaded:
            archive = self.download(self.download_url, tofolder=self.project.downloads)
            self.log.info("downloaded %s", archive)
        else:
            archive = self.downloaded_archive
        if self.src_dir.exists():
            self.remove(self.src_dir)
        self.extract(archive, tofolder=self.project.src)
        if not self.src_dir.exists():
            raise ExtractionError(f"could not extract from {archive}")

    def configure(self) -> None:
        """configure build"""

    def build(self) -> None:
        """main build process"""
        self.cmd("PCbuild\\build.bat -e --no-tkinter", cwd=self.src_dir)

    def install(self) -> None:
        """install to prefix"""
        if not self.binary_dir.exists():
            raise IOError("Build error")
        if self.prefix.exists():
            self.remove(self.prefix)
        self.copy(self.binary_dir, self.prefix)
        self.copy(self.src_dir / "Include", self.prefix / "include")
        self.move(self.prefix / "pyconfig.h", self.prefix / "include")
        self.copy(self.src_dir / "Lib", self.prefix / "Lib")
        self.move(self.prefix / "Lib" / "site-packages", self.prefix)
        self.makedirs(self.prefix / "libs")
        self.glob_move(self.prefix, "*.lib", self.prefix / "libs")
        with open(self.prefix / self.pth, "w") as f:
            print("Lib", file=f)
            print(f"{self.name_ver_nodot}.zip", file=f)
            print("site-packages", file=f)
            print(".", file=f)

    def clean(self) -> None:
        """clean installed build"""
        self.remove(self.prefix / "pybuilddir.txt")
        self.glob_remove(
            self.prefix,
            self.remove_patterns,
            skip_dirs=[".git"],
        )

    def install_pkgs(self) -> None:
        """install python packages (disabled for Windows builder)"""
        pass

    def post_process(self) -> None:
        """override by subclass if needed"""
        self.log.info("%s DONE", self.config)

    def process(self) -> None:
        """main builder process"""
        if not self.can_run():
            self.log.info("everything built: skipping run")
            return

        self.pre_process()
        self.setup()
        self.configure()
        self.build()
        self.install()
        self.clean()
        self.ziplib()
        self.post_process()


def main() -> None:
    """commandline api entrypoint"""

    parser = argparse.ArgumentParser(
        prog="buildpy.py",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="A python builder",
    )
    opt = parser.add_argument

    # fmt: off
    opt("-a", "--cfg-opts", help="add config options", type=str, nargs="+", metavar="CFG")
    opt("-b", "--optimize-bytecode", help="set optimization levels -1 .. 2 (default: %(default)s)", type=int, default=-1)
    opt("-c", "--config", default="shared_mid", help="build configuration (default: %(default)s)", metavar="NAME")
    opt("-d", "--debug", help="build debug python", action="store_true")
    opt("-n", "--dry-run", help="show build plan without building", action="store_true")
    opt("-e", "--embeddable-pkg", help="install python embeddable package", action="store_true")
    opt("-i", "--install", help="install python pkgs", type=str, nargs="+", metavar="PKG")
    opt("-m", "--package", help="package build", action="store_true")
    opt("-o", "--optimize", help="enable optimization during build",  action="store_true")
    opt("-p", "--precompile", help="precompile stdlib to bytecode", action="store_true")
    opt("-r", "--reset", help="reset build", action="store_true")
    opt("-v", "--version", default=DEFAULT_PY_VERSION, help="python version (default: %(default)s)")
    opt("-w", "--write", help="write configuration", action="store_true")
    opt("-j", "--jobs", help="# of build jobs (default: %(default)s)", type=int, default=4)
    opt("-s", "--json", help="serialize config to json file", action="store_true")
    opt("-t", "--type", help="build based on build type")
    opt("-S", "--size-report", help="show size breakdown of build", action="store_true")
    opt("-A", "--analyze-deps", help="analyze stdlib dependencies of packages", action="store_true")
    opt("--auto-reduce", action="store_true",
        help="automatic workflow: analyze deps, build with shared_vanilla, apply reductions, zip stdlib")
    opt("--auto-config", action="store_true",
        help="generate reduction manifest based on dependency analysis")
    opt("--auto-config-output", type=str, metavar="PATH",
        help="output path for reduction manifest (default: reduction-manifest.json)")
    opt("--apply-reductions", type=str, metavar="MANIFEST",
        help="apply reduction manifest to remove unused files from build")
    opt("--reduction-copy", type=str, metavar="DIR",
        help="copy build to DIR before applying reductions (safer for testing)")
    opt("--skip-ziplib", action="store_true",
        help="skip stdlib compression (use with --apply-reductions workflow)")
    opt("--ziplib", action="store_true",
        help="compress stdlib of existing build (after --apply-reductions)")
    opt("--install-dir", help="custom installation directory (overrides --package)", type=str, metavar="DIR")
    # fmt: on

    args = parser.parse_args()
    python_builder_class: type[PythonBuilder]

    if PLATFORM == "Darwin":
        python_builder_class = PythonBuilder
        if args.debug:
            python_builder_class = PythonDebugBuilder

    elif PLATFORM == "Windows":
        if args.embeddable_pkg:
            embeddable_builder = WindowsEmbeddablePythonBuilder()
            embeddable_builder.setup()
            sys.exit(0)
        else:
            python_builder_class = WindowsPythonBuilder

    else:
        raise NotImplementedError("script only works on MacOS and Windows")

    builder: PythonBuilder
    if args.type and args.type in BUILD_TYPES:
        if args.type == "local":
            sys.exit(0)
        cfg = {
            "shared-ext": "shared_mid",
            "static-ext": "static_mid",
            "framework-ext": "framework_mid",
            "framework-pkg": "framework_mid",
            "windows-pkg": "shared_max",
        }[args.type]
        is_package = args.type[-3:] == "pkg"
        builder = python_builder_class(
            version=args.version,
            config=cfg,
            precompile=args.precompile,
            optimize=args.optimize,
            optimize_bytecode=args.optimize_bytecode,
            pkgs=args.install,
            cfg_opts=args.cfg_opts,
            jobs=args.jobs,
            is_package=is_package,
            install_dir=args.install_dir,
            skip_ziplib=args.skip_ziplib,
        )
        if args.dry_run:
            builder.dry_run()
            sys.exit(0)
        if args.size_report:
            builder.size_report()
            sys.exit(0)
        if args.auto_reduce:
            success = builder.auto_reduce()
            sys.exit(0 if success else 1)
        if args.analyze_deps:
            builder.analyze_deps()
            if args.auto_config:
                result = builder.auto_configure(
                    output_path=args.auto_config_output,
                )
                if result:
                    print(f"Reduction manifest written to: {result}")
            sys.exit(0)
        if args.apply_reductions:
            result = builder.apply_reductions(
                manifest_path=args.apply_reductions,
                copy_to=args.reduction_copy,
            )
            sys.exit(0 if result else 1)
        if args.reset:
            builder.remove("build")
        builder.process()
        sys.exit(0)

    if "-" in args.config:
        _config = args.config.replace("-", "_")
    else:
        _config = args.config

    builder = python_builder_class(
        version=args.version,
        config=_config,
        precompile=args.precompile,
        optimize=args.optimize,
        optimize_bytecode=args.optimize_bytecode,
        pkgs=args.install,
        cfg_opts=args.cfg_opts,
        jobs=args.jobs,
        is_package=args.package,
        install_dir=args.install_dir,
        skip_ziplib=args.skip_ziplib,
    )

    # Handle --ziplib: compress stdlib of existing build
    if args.ziplib:
        if not builder.prefix.exists():
            print(f"Error: Build not found at {builder.prefix}")
            sys.exit(1)
        print(f"Compressing stdlib at {builder.prefix}...")
        builder.ziplib()
        print("Done.")
        sys.exit(0)

    if args.write:
        if not args.json:
            patch_dir = Path.cwd() / "patch"
            if not patch_dir.exists():
                patch_dir.mkdir()
            cfg_file = patch_dir / args.config.replace("_", ".")
            builder.get_config().write(args.config, to=cfg_file)
        else:
            builder.get_config().write_json(args.config, to=args.json)
            sys.exit()

    if args.dry_run:
        builder.dry_run()
        sys.exit(0)

    if args.size_report:
        builder.size_report()
        sys.exit(0)

    if args.auto_reduce:
        success = builder.auto_reduce()
        sys.exit(0 if success else 1)

    if args.analyze_deps:
        builder.analyze_deps()
        if args.auto_config:
            result = builder.auto_configure(
                output_path=args.auto_config_output,
            )
            if result:
                print(f"Reduction manifest written to: {result}")
        sys.exit(0)

    if args.apply_reductions:
        result = builder.apply_reductions(
            manifest_path=args.apply_reductions,
            copy_to=args.reduction_copy,
        )
        sys.exit(0 if result else 1)

    if args.reset:
        builder.remove("build")
    builder.process()


if __name__ == "__main__":
    main()
