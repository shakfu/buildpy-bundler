# Changelog

All notable changes to the buildpy project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed

- **Renamned to buildpy-bundler**: to avoid pypi name collision.

- **Improved README.md**: Restructured documentation for better readability
  - Added Features, Requirements, and Quick Start sections
  - Reorganized CLI options into scannable table format
  - Added practical usage examples
  - Replaced verbose configuration descriptions with clear tables
  - Added Build Output section explaining directory structure

### Fixed

- **Complete type annotations**: Fixed all 146 mypy type errors
  - Added return type annotations to all functions and methods
  - Fixed `Config.cfg` type from `dict[str, list[str]]` to `dict[str, Any]` for mixed value types
  - Added proper type annotations for `*args` and `**kwargs` parameters
  - Fixed `_validate_checksum` to use `hashlib.new()` instead of `getattr()`
  - Added explicit type annotations for class variables (`depends_on`, `lib_products`)
  - Fixed `main()` function variable typing to avoid inference issues
  - Added `log` attribute initialization to `Project` class

## [0.1.0]

### Security

- **Fixed shell injection vulnerability**: Commands now use `shlex.split()` or list arguments instead of `shell=True`
- **Added checksum validation**: Downloads support optional SHA256/SHA512/MD5 verification to prevent tampered files
- **Fixed tarfile path traversal (CVE-2007-4559)**: Safe extraction backported for Python versions < 3.12
- **Added input validation**: URL validation for git clone operations prevents malicious URLs

### Added

- **Support for Python 3.14.0**
  - New `PythonConfig314` class with updated module configuration
  - Added modules: `_types`, `_hmac` (static by default)
  - Optional modules: `_remote_debugging`, `_zstd` (disabled by default)
  - Removed modules: `_contextvars` (now built-in), `_testexternalinspection` (deprecated)
  - Simplified hash module configurations (`_blake2`, `_md5`, `_sha1`, `_sha2`, `_sha3`)
- **Configurable installation directory**: New `install_dir` parameter generalizes deployment flexibility
  - **API**: `PythonBuilder(install_dir="/path/to/install")` - Direct specification of installation location
  - **CLI**: `--install-dir DIR` - Command-line option for custom installation directory
  - **Dynamic loader path computation**: `_compute_loader_path()` automatically derives `@loader_path` from relative position of `install_dir`
  - **Priority system**: `install_dir` > `is_package` > default (`build/install`) for backwards compatibility
  - **Framework builds**: Installed to `{install_dir}/Python.framework/Versions/{ver}/`
  - **Use cases**: Enables flexible deployment patterns (system-wide installs, containerized builds, embedded frameworks)
- **Exception hierarchy**: New custom exceptions (`BuildError`, `CommandError`, `DownloadError`, `ExtractionError`, `ValidationError`) replace `sys.exit()` calls
- **Platform detection utilities**: Centralized `PlatformInfo` class with properties (`is_darwin`, `is_linux`, `is_windows`, `is_unix`)
- **Build artifact validation**: `validate_build()` method performs smoke tests on built Python (version check, import tests, module validation)
- **Build caching strategy**: `_is_build_cached()` intelligently skips rebuilds when artifacts exist (CI/CD optimized)
- **Progress indicators**: User-friendly messages for download, extraction, configuration, and build phases
- **Type annotations**: Complete type hints added throughout codebase for better IDE support and type checking
- **Configurable install_name_id**: Added `install_name_id` field to `Config` class for customizing framework install names
  - Supports custom paths for specialized builds (e.g., Max/MSP integration)
  - Defaults to `@rpath/Python.framework/Versions/{ver}/Python` for framework builds
  - Can be overridden per-config for special deployment scenarios

### Changed

- **Refactored config class hierarchy**: Created intermediate `PythonConfig` class between `Config` and version-specific configs
  - New hierarchy: `Config` → `PythonConfig` → `PythonConfig311/312/313/314`
  - Moved common build variant methods (`static_max`, `framework_max`, etc.) to `PythonConfig` base class
  - Eliminated code duplication across Python version configs
  - Added `build_type` parameter to `PythonConfig.__init__()` for framework detection
- **Generalized install directory handling**: Replaced hardcoded `is_package` conditionals with flexible `install_dir` system
  - `PythonBuilder.__init__()` now accepts optional `install_dir` parameter
  - `prefix` property now uses `self._install_dir` instead of conditional logic
  - `configure()` method simplified to use `self._install_dir` directly
  - `post_process()` computes `@loader_path` dynamically via `_compute_loader_path()`
  - `WindowsPythonBuilder.prefix` now respects configurable `install_dir`
  - Backwards compatible: `is_package` parameter still supported
- **Refactored ziplib() logic**: Extracted duplicate code from `PythonBuilder` and `WindowsPythonBuilder` into base class with platform-specific hooks
  - `_get_lib_src_dir()` - Platform-specific library directory
  - `_precompile_lib()` - Bytecode compilation
  - `_handle_lib_dynload()` - Unix-specific lib-dynload handling
  - `_preserve_os_module()` / `_restore_os_module()` - Module preservation
  - `_cleanup_after_zip()` - Post-zip cleanup
  - `_get_zip_path()` - Platform-specific zip paths
- **Improved logging levels**: Reduced noise by converting verbose operations to DEBUG level
  - File operations (move, remove, makedirs) now DEBUG
  - Download/extraction operations now INFO (user-facing) or DEBUG (internal)
  - Build milestones remain INFO
  - Errors remain CRITICAL, warnings remain WARNING
- **Enhanced build caching**: Improved `can_run()` method with dependency checking and complete artifact validation
- **Generalized make_relocatable()**: Now uses configurable `install_name_id` from config instead of hardcoded Max/MSP path

### Removed

- **Dead code cleanup**: Removed commented-out code sections
  - Removed commented dependency iterator in `AbstractBuilder`
  - Removed obsolete platform checks in `PythonConfig312.patch()`
  - Removed commented Windows package installation code
  - Kept documented configuration options as valuable reference

### Fixed

- **Error handling**: All assertions replaced with proper exceptions
  - `Builder.setup()` now raises `ExtractionError` instead of `AssertionError`
  - `XzBuilder.setup()` now raises `BuildError` instead of `AssertionError`
  - `WindowsPythonBuilder.setup()` now raises `ExtractionError` instead of `AssertionError`
- **Exception chaining**: Proper exception chaining with `raise ... from e` for better debugging
- **Archive extraction**: Both tarfile and zipfile extraction now wrapped in proper exception handling

### Testing

- All 16 tests passing (100% pass rate)
- Updated test suite to match new exception types
- Fixed test expectations for command execution (list vs string arguments)
- **mypy type checking**: All type errors resolved, passes strict type checking

### Type Safety

- Fixed `glob_move()` to properly convert Pathlike to Path before calling `.glob()`
- Fixed `downloaded_archive` property return type from `str` to `Path`
- Added type annotation for `WindowsPythonBuilder.lib_products: list[str]`
- All mypy errors resolved with zero issues found

## [0.0.2]

### Added
- Multi-language implementations (Python, Go, Rust, C++, Haskell, Swift)
- Support for static, shared, and framework builds
- Python 3.11, 3.12, and 3.13 configurations
- Custom module configuration via `Setup.local`
- Library zipping and bytecode precompilation
- Relocatable builds with @rpath handling (macOS)

### Features
- Single-file Python implementation (48KB)
- Cross-platform support (macOS, Linux, Windows)
- Dependency building (OpenSSL, bzip2, xz)
- Size optimization options
- Build type variants (max, mid, tiny, bootstrap)

---

## Notes

### Migration Guide

If you're upgrading from a previous version:

1. **Exception Handling**: Code that caught `SystemExit` should now catch specific exceptions:
   ```python
   # Old
   try:
       builder.cmd("some command")
   except SystemExit:
       handle_error()

   # New
   try:
       builder.cmd("some command")
   except CommandError:
       handle_error()
   ```

2. **Custom Installation Directories**: Use the new `install_dir` parameter for flexible deployments:
   ```python
   # API usage
   builder = PythonBuilder(version="3.14.0", config="framework_max",
                          install_dir="/opt/python")

   # CLI usage
   python3 buildpy.py -v 3.14.0 -c framework_max --install-dir /opt/python
   ```

3. **Python 3.14 Support**: Update version strings to use 3.14.x for latest Python features.

4. **Build Validation**: Builds now automatically validate after completion. Check logs for validation warnings.

5. **Logging**: Set `DEBUG=0` environment variable to reduce log verbosity in production.

6. **Caching**: Builds now intelligently skip when artifacts exist. Use `--reset` flag to force rebuild.

### Security Advisories

- **CVE-2007-4559**: Tarfile path traversal vulnerability has been mitigated for all Python versions
- Users should verify checksums when available by providing the `checksum` parameter to download operations

### Performance Improvements

- Build caching reduces CI/CD build times by skipping unnecessary rebuilds
- Parallel job support (`-j` flag) maintained and now shows job count in logs
- Download caching with checksum validation prevents re-downloading unchanged files
