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
usage: buildpy.py [-h] [-a CFG [CFG ...]] [-b OPTIMIZE_BYTECODE] [-c NAME] [-d]
                  [-n] [-e] [-i PKG [PKG ...]] [-m] [-o] [-p] [-r] [-v VERSION]
                  [-w] [-j JOBS] [-s] [-t TYPE] [-S] [-A] [--auto-reduce]
                  [--auto-config] [--auto-config-output PATH]
                  [--apply-reductions MANIFEST] [--reduction-copy DIR]
                  [--skip-ziplib] [--ziplib] [--install-dir DIR]

A python builder

options:
  -h, --help            show this help message and exit
  -a, --cfg-opts CFG [CFG ...]
                        add config options
  -b, --optimize-bytecode OPTIMIZE_BYTECODE
                        set optimization levels -1 .. 2 (default: -1)
  -c, --config NAME     build configuration (default: shared_mid)
  -d, --debug           build debug python
  -n, --dry-run         show build plan without building
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
  -S, --size-report     show size breakdown of build
  -A, --analyze-deps    analyze stdlib dependencies of packages
  --auto-reduce         automatic workflow: analyze deps, build with
                        shared_vanilla, apply reductions, zip stdlib
  --auto-config         generate reduction manifest based on dependency analysis
  --auto-config-output PATH
                        output path for reduction manifest (default: reduction-
                        manifest.json)
  --apply-reductions MANIFEST
                        apply reduction manifest to remove unused files from
                        build
  --reduction-copy DIR  copy build to DIR before applying reductions (safer for
                        testing)
  --skip-ziplib         skip stdlib compression (use with --apply-reductions
                        workflow)
  --ziplib              compress stdlib of existing build (after --apply-
                        reductions)
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
| `-n, --dry-run` | Show build plan without building |
| `-S, --size-report` | Show size breakdown of build |
| `-A, --analyze-deps` | Analyze stdlib dependencies of packages |
| `--auto-reduce` | Automatic workflow: analyze, build, reduce, compress |
| `--auto-config` | Generate reduction manifest based on analysis |
| `--auto-config-output PATH` | Output path for reduction manifest |
| `--apply-reductions MANIFEST` | Apply reduction manifest to remove unused files |
| `--reduction-copy DIR` | Copy build to DIR before applying reductions |
| `--skip-ziplib` | Skip stdlib compression (for reduction workflow) |
| `--ziplib` | Compress stdlib of existing build |

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

# Preview build plan without building (dry-run)
buildpy -n -c static_mid -v 3.12

# Analyze size of completed build
buildpy -S

# Analyze stdlib dependencies of packages
buildpy -A -i requests urllib3

# Generate reduction manifest based on dependency analysis
buildpy -A -i ipython --auto-config
```

### Size-Optimized Builds

The `--auto-reduce` flag provides a single-command workflow for creating minimal Python distributions:

```bash
# Build Python with only the modules needed for numpy
buildpy -i numpy --auto-reduce
```

This command:
1. Analyzes numpy's stdlib dependencies using AST-based import detection
2. Builds (or reuses cached) vanilla Python with all modules as shared extensions
3. Copies to `python-shared-reduced` and installs the specified packages
4. Removes unused extension modules and stdlib directories
5. Compresses the stdlib into a zip archive
6. Verifies the build by importing each specified package

The vanilla build is cached at `build/install/python-shared-vanilla` for fast iterations.

**Manual workflow** (for more control):

```bash
# 1. Build without zipping stdlib
buildpy -c shared_vanilla --skip-ziplib

# 2. Apply reductions
buildpy --apply-reductions reduction-manifest.json

# 3. Compress the reduced stdlib
buildpy --ziplib

# Or apply to a copy for testing:
buildpy --apply-reductions reduction-manifest.json --reduction-copy build/reduced
```

## Configurations

Configurations follow the naming pattern `<build-type>_<size-type>`:

| Size Type | Description |
|-----------|-------------|
| `max` | Maximum modules included |
| `mid` | Balanced selection (recommended) |
| `min` | Minimal footprint |
| `bootstrap` | Absolute minimum for bootstrapping |
| `vanilla` | All modules as shared extensions (for `--auto-reduce`) |

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
| `shared_vanilla` | None (all as shared extensions for post-build reduction) |

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
