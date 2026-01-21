# TODO

Future feature ideas for buildpy-bundler.

## Build Analysis & Optimization

- [x] **Size report** (`-S, --size-report`) - IMPLEMENTED
  - Generate a breakdown of build size by component (stdlib, lib-dynload, binaries, etc.)
  - Shows percentage breakdown and top 10 largest files
  - Useful for optimizing embedded deployments

- [x] **Module dependency analyzer** (`-A, --analyze-deps`) - IMPLEMENTED
  - Analyzes packages specified via `-i/--install` for stdlib module usage
  - Uses AST-based import detection to find stdlib dependencies
  - Maps imports to required C extension modules (e.g., `ssl` -> `_ssl`)
  - Compares against current config and provides recommendations

- [x] **Auto-configure** (`--auto-config`) - IMPLEMENTED
  - Generates a reduction manifest (JSON) based on dependency analysis
  - Lists extension modules and stdlib directories that can be removed post-build
  - Preserves modules needed by ensurepip (unlike Setup.local approach)
  - Custom output path with `--auto-config-output PATH`

- [x] **Apply reductions** (`--apply-reductions`) - IMPLEMENTED
  - Applies reduction manifest to remove unused files from completed build
  - Works on lib-dynload/ extensions and lib/pythonX.Y/ stdlib modules
  - `--reduction-copy DIR` to apply to a copy (safer for testing)
  - `--skip-ziplib` to build without compressing stdlib
  - `--ziplib` to compress stdlib after reductions
  - Workflow: `--skip-ziplib` -> `--apply-reductions` -> `--ziplib`

- [x] **Dry-run mode** (`-n, --dry-run`) - IMPLEMENTED
  - Show what would be built (config options, modules, dependencies) without actually building
  - Useful for debugging configs and understanding build behavior
  - Display configure options, modules to be built, dependencies

## Build Reliability

- [ ] **Resume interrupted builds**
  - If a build fails partway through (e.g., network issue during download), resume from the last successful step
  - Track build state in a checkpoint file
  - Avoid re-downloading/re-extracting already completed steps

- [ ] **Build manifest**
  - Generate a JSON/YAML manifest recording:
    - Exact versions of Python and dependencies
    - Source archive checksums
    - Build options and configuration
    - Timestamps
    - Platform/architecture info
  - Enables reproducibility auditing and build verification

## Platform-Specific

- [ ] **macOS universal binaries**
  - Build fat binaries containing both x86_64 and arm64 architectures
  - Use `lipo` to combine architecture-specific builds
  - Useful for distributing single binaries that work on Intel and Apple Silicon

## Workflow

- [ ] **Custom post-build hooks**
  - Run user-defined scripts after build completion
  - Use cases: copy to deployment location, run custom tests, trigger CI/CD
  - Configure via `--post-hook SCRIPT` or config file

- [ ] **Config presets**
  - Save custom configurations to files for reuse across projects
  - Beyond the built-in static_mid, shared_max, etc.
  - Load with `--preset FILE` or from `.buildpy.toml`
  - Share configurations across team/organization

## Future Considerations

- [ ] **Cross-compilation support**
  - Build Python for different target architectures
  - e.g., building ARM64 binaries on x86_64 host

- [ ] **Container/Docker integration**
  - Generate Dockerfiles for reproducible builds
  - Build inside containers for isolation

- [ ] **Code signing** (macOS)
  - Sign built binaries for Gatekeeper compliance
  - Support for Developer ID and ad-hoc signing
