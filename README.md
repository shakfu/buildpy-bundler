# buildpy-bundler

A lightweight, single-file Python build tool for compiling Python 3.11-3.14 from source with customizable configurations.

## Features

- Single-file script with no external dependencies (stdlib only)
- Multiple build configurations (static, shared, framework)
- Automatic dependency building (OpenSSL, bzip2, xz)
- Size optimization options (stdlib zipping, selective module inclusion)
- Cross-platform support (macOS, Linux, Windows)

## Requirements

- Python 3.10+ (to run the build script)
- System tools: `git`, `wget`, `tar`, `make`
- C compiler (gcc/clang)

## Quick Start

```bash
# Build with default configuration (shared_mid)
buildpy

# Or use make
make
```

The built Python will be installed to `./build/install/python/`.

## Usage

```sh
% buildpy --help
usage: buildpy.py [-h] [-a CFG [CFG ...]] [-b OPTIMIZE_BYTECODE] [-c NAME] [-d]
                  [-e] [-i PKG [PKG ...]] [-m] [-o] [-p] [-r] [-v VERSION] [-w]
                  [-j JOBS] [-s] [-t TYPE] [--install-dir DIR]

A python builder

options:
  -h, --help            show this help message and exit
  -a, --cfg-opts CFG [CFG ...]
                        add config options
  -b, --optimize-bytecode OPTIMIZE_BYTECODE
                        set optimization levels -1 .. 2 (default: -1)
  -c, --config NAME     build configuration (default: shared_mid)
  -d, --debug           build debug python
  -e, --embeddable-pkg  install python embeddable package
  -i, --install PKG [PKG ...]
                        install python pkgs
  -m, --package         package build
  -o, --optimize        enable optimization during build
  -p, --precompile      precompile stdlib to bytecode
  -r, --reset           reset build
  -v, --version VERSION
                        python version (default: 3.13.11)
  -w, --write           write configuration
  -j, --jobs JOBS       # of build jobs (default: 4)
  -s, --json            serialize config to json file
  -t, --type TYPE       build based on build type
  --install-dir DIR     custom installation directory (overrides --package)
```

### Options

| Option | Description |
|--------|-------------|
| `-v, --version VERSION` | Python version to build (default: 3.13.11) |
| `-c, --config NAME` | Build configuration (default: shared_mid) |
| `-t, --type TYPE` | Build type: static, shared, or framework |
| `-j, --jobs N` | Number of parallel build jobs (default: 4) |
| `-o, --optimize` | Enable optimization during build |
| `-d, --debug` | Build debug Python |
| `-p, --precompile` | Precompile stdlib to bytecode |
| `-b, --optimize-bytecode` | Set bytecode optimization level -1..2 (default: -1) |
| `-m, --package` | Package the build for distribution |
| `-r, --reset` | Clean and reset build directory |
| `--install-dir DIR` | Custom installation directory (overrides --package) |
| `-i, --install PKG [PKG ...]` | Install packages after build |
| `-w, --write` | Write Setup.local configuration |
| `-s, --json` | Export configuration to JSON |
| `-a, --cfg-opts CFG [CFG ...]` | Add config options |
| `-e, --embeddable-pkg` | Install python embeddable package |

### Examples

```bash
# Build Python 3.12 with static linking
buildpy -v 3.12 -t static

# Build optimized Python with 8 parallel jobs
buildpy -o -j 8

# Build and package for distribution
buildpy -m

# Build to custom directory
buildpy --install-dir /opt/python

# Build and install packages (e.g., for embedding)
buildpy -i requests numpy pandas
```

## Configurations

Configurations follow the naming pattern `<build-type>_<size-type>`:

| Size Type | Description |
|-----------|-------------|
| `max` | Maximum modules included |
| `mid` | Balanced selection (recommended) |
| `min` | Minimal footprint |
| `bootstrap` | Absolute minimum for bootstrapping |

### Static Builds

Statically links libpython into the executable.

| Config | Modules Excluded |
|--------|------------------|
| `static_max` | `_ctypes` only |
| `static_mid` | `_ssl`, `_hashlib` |
| `static_min` | Most optional modules |
| `static_bootstrap` | Based on Setup.bootstrap |

### Shared Builds

Uses a shared libpython library.

| Config | Modules Excluded |
|--------|------------------|
| `shared_max` | None |
| `shared_mid` | `_ctypes`, `_ssl`, `_hashlib`, `_decimal` |
| `shared_min` | Most optional modules |

### Framework Builds (macOS only)

Creates a macOS framework bundle. Not yet implemented.

## Build Output

```
build/
  downloads/     # Cached source archives
  src/           # Extracted source trees
  install/
    python/      # Final Python installation
```

Output naming convention: `py-<type>-<size>-<version>-<platform>-<arch>`

Example: `py-static-mid-3.13.0-darwin-arm64`

## Known Issues

- If `libb2` is installed on your system, the `_blake2` module will link against it, creating a runtime dependency
