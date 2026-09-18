# TODO

Future feature ideas for buildpy-bundler.

## Critical

## High

### Build Reliability

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

## Medium

### Workflow

- [ ] **Custom post-build hooks**
  - Run user-defined scripts after build completion
  - Use cases: copy to deployment location, run custom tests, trigger CI/CD
  - Configure via `--post-hook SCRIPT` or config file

- [ ] **Config presets**
  - Save custom configurations to files for reuse across projects
  - Beyond the built-in static_mid, shared_max, etc.
  - Load with `--preset FILE` or from `.buildpy.toml`
  - Share configurations across team/organization

## Low

### Platform-Specific

- [ ] **macOS universal binaries**
  - Build fat binaries containing both x86_64 and arm64 architectures
  - Use `lipo` to combine architecture-specific builds
  - Useful for distributing single binaries that work on Intel and Apple Silicon

### Future Considerations

- [ ] **Cross-compilation support**
  - Build Python for different target architectures
  - e.g., building ARM64 binaries on x86_64 host

- [ ] **Container/Docker integration**
  - Generate Dockerfiles for reproducible builds
  - Build inside containers for isolation

- [ ] **Code signing** (macOS)
  - Sign built binaries for Gatekeeper compliance
  - Support for Developer ID and ad-hoc signing



