"""Tests for the --auto-config and --apply-reductions features"""

import json
import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from buildpy import PythonBuilder, Project, AnalysisResult, logging


@pytest.fixture
def mock_project(tmp_path):
    """Create a Project instance using temporary directory"""
    project = Project()
    project.root = tmp_path
    project.build = tmp_path / "build"
    project.downloads = project.build / "downloads"
    project.src = project.build / "src"
    project.install = project.build / "install"
    project.support = tmp_path / "support"
    project.bin = project.build / "bin"
    project.lib = project.build / "lib"
    project.lib_static = project.build / "lib" / "static"
    return project


@pytest.fixture
def builder(mock_project):
    """Create a basic PythonBuilder for testing"""
    builder = PythonBuilder(
        version="3.13.11",
        project=mock_project,
        config="shared_mid",
    )
    builder.log = Mock(spec=logging.Logger)
    return builder


@pytest.fixture
def builder_with_pkgs(mock_project):
    """Create a PythonBuilder with packages for testing"""
    builder = PythonBuilder(
        version="3.13.11",
        project=mock_project,
        config="shared_mid",
        pkgs=["requests", "urllib3"],
    )
    builder.log = Mock(spec=logging.Logger)
    return builder


class TestAnalysisResult:
    """Tests for the AnalysisResult dataclass"""

    def test_analysis_result_creation(self):
        """Test creating an AnalysisResult"""
        result = AnalysisResult(
            stdlib_imports={"os", "sys", "json"},
            third_party={"requests"},
            required_extensions={"_json"},
            needed_but_disabled={"_ssl"},
            potentially_unused={"_tkinter"},
            files_analyzed=10,
        )
        assert result.stdlib_imports == {"os", "sys", "json"}
        assert result.third_party == {"requests"}
        assert result.required_extensions == {"_json"}
        assert result.needed_but_disabled == {"_ssl"}
        assert result.potentially_unused == {"_tkinter"}
        assert result.files_analyzed == 10

    def test_analysis_result_with_empty_sets(self):
        """Test creating an AnalysisResult with empty sets"""
        result = AnalysisResult(
            stdlib_imports=set(),
            third_party=set(),
            required_extensions=set(),
            needed_but_disabled=set(),
            potentially_unused=set(),
            files_analyzed=0,
        )
        assert len(result.stdlib_imports) == 0
        assert result.files_analyzed == 0


class TestExtractImports:
    """Tests for the _extract_imports helper method"""

    def test_extract_simple_import(self, builder):
        """Test extraction of simple imports"""
        source = "import os\nimport sys\nimport json"
        imports = builder._extract_imports(source)
        assert "os" in imports
        assert "sys" in imports
        assert "json" in imports

    def test_extract_from_import(self, builder):
        """Test extraction of 'from x import y' statements"""
        source = "from collections import defaultdict\nfrom pathlib import Path"
        imports = builder._extract_imports(source)
        assert "collections" in imports
        assert "pathlib" in imports

    def test_extract_submodule_import(self, builder):
        """Test that submodule imports return top-level module"""
        source = "from urllib.parse import urlparse\nimport xml.etree.ElementTree"
        imports = builder._extract_imports(source)
        assert "urllib" in imports
        assert "xml" in imports
        assert "parse" not in imports
        assert "etree" not in imports

    def test_extract_syntax_error(self, builder):
        """Test that syntax errors are handled gracefully"""
        source = "import os\ndef broken("  # Syntax error
        imports = builder._extract_imports(source)
        # Should return empty set on syntax error
        assert isinstance(imports, set)


class TestAnalyzePackageDeps:
    """Tests for the _analyze_package_deps helper method"""

    def test_no_packages_returns_none(self, builder):
        """Test that _analyze_package_deps returns None when no packages specified"""
        with patch('builtins.print'):
            result = builder._analyze_package_deps()
        assert result is None

    def test_with_packages_returns_analysis_result(self, builder_with_pkgs):
        """Test that _analyze_package_deps returns AnalysisResult"""
        with patch('builtins.print'):
            with patch('subprocess.run') as mock_run:
                mock_run.return_value = MagicMock(returncode=1)
                result = builder_with_pkgs._analyze_package_deps()

        assert result is not None
        assert isinstance(result, AnalysisResult)

    def test_verbose_false_suppresses_output(self, builder_with_pkgs):
        """Test that verbose=False suppresses print statements"""
        output = []
        with patch('builtins.print', side_effect=lambda x: output.append(x)):
            with patch('subprocess.run') as mock_run:
                mock_run.return_value = MagicMock(returncode=1)
                builder_with_pkgs._analyze_package_deps(verbose=False)

        # Should have no output when verbose=False
        assert len(output) == 0


class TestAutoConfigureCLI:
    """Tests for CLI argument parsing of auto-config options"""

    def test_auto_config_flag(self):
        """Test that --auto-config is a boolean flag"""
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument("--auto-config", action="store_true")

        args = parser.parse_args([])
        assert args.auto_config is False

        args = parser.parse_args(["--auto-config"])
        assert args.auto_config is True

    def test_auto_config_output_accepts_path(self):
        """Test that --auto-config-output accepts a path"""
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument("--auto-config-output", type=str)

        args = parser.parse_args(["--auto-config-output", "/path/to/manifest.json"])
        assert args.auto_config_output == "/path/to/manifest.json"

    def test_apply_reductions_accepts_path(self):
        """Test that --apply-reductions accepts a manifest path"""
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument("--apply-reductions", type=str)

        args = parser.parse_args(["--apply-reductions", "manifest.json"])
        assert args.apply_reductions == "manifest.json"

    def test_reduction_copy_accepts_path(self):
        """Test that --reduction-copy accepts a directory path"""
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument("--reduction-copy", type=str)

        args = parser.parse_args(["--reduction-copy", "/path/to/copy"])
        assert args.reduction_copy == "/path/to/copy"


class TestAutoConfigureMethod:
    """Tests for the auto_configure method"""

    def test_auto_configure_no_packages_returns_none(self, builder):
        """Test that auto_configure returns None when no packages specified"""
        with patch('builtins.print'):
            result = builder.auto_configure()
        assert result is None

    def test_auto_configure_generates_manifest(self, builder_with_pkgs, tmp_path):
        """Test auto_configure generates a JSON manifest"""
        output_path = tmp_path / "manifest.json"

        with patch('builtins.print'):
            with patch('subprocess.run') as mock_run:
                mock_run.return_value = MagicMock(returncode=1)
                result = builder_with_pkgs.auto_configure(output_path=output_path)

        assert result == output_path
        assert output_path.exists()

        # Verify it's valid JSON with expected structure
        with open(output_path) as f:
            manifest = json.load(f)

        assert "version" in manifest
        assert "python_version" in manifest
        assert "config" in manifest
        assert "packages_analyzed" in manifest
        assert "analysis" in manifest
        assert "reductions" in manifest
        assert "warnings" in manifest

    def test_auto_configure_manifest_structure(self, builder_with_pkgs, tmp_path):
        """Test that manifest has correct structure"""
        output_path = tmp_path / "manifest.json"

        with patch('builtins.print'):
            with patch('subprocess.run') as mock_run:
                mock_run.return_value = MagicMock(returncode=1)
                builder_with_pkgs.auto_configure(output_path=output_path)

        with open(output_path) as f:
            manifest = json.load(f)

        # Check analysis section
        assert "required_extensions" in manifest["analysis"]
        assert "stdlib_imports" in manifest["analysis"]
        assert "third_party" in manifest["analysis"]

        # Check reductions section
        assert "extensions_to_remove" in manifest["reductions"]
        assert "extension_patterns" in manifest["reductions"]
        assert "stdlib_to_remove" in manifest["reductions"]

    def test_auto_configure_default_output_path(self, builder_with_pkgs, tmp_path, monkeypatch):
        """Test that auto_configure creates default output in current directory"""
        monkeypatch.chdir(tmp_path)

        with patch('builtins.print'):
            with patch('subprocess.run') as mock_run:
                mock_run.return_value = MagicMock(returncode=1)
                result = builder_with_pkgs.auto_configure()

        assert result is not None
        assert result.name == "reduction-manifest.json"
        assert result.exists()

    def test_auto_configure_creates_parent_dirs(self, builder_with_pkgs, tmp_path):
        """Test that auto_configure creates parent directories if needed"""
        output_path = tmp_path / "nested" / "dir" / "manifest.json"

        with patch('builtins.print'):
            with patch('subprocess.run') as mock_run:
                mock_run.return_value = MagicMock(returncode=1)
                result = builder_with_pkgs.auto_configure(output_path=output_path)

        assert result == output_path
        assert output_path.exists()


class TestApplyReductions:
    """Tests for the apply_reductions method"""

    def test_apply_reductions_missing_manifest(self, builder, tmp_path):
        """Test that apply_reductions fails gracefully with missing manifest"""
        output = []
        with patch('builtins.print', side_effect=lambda x: output.append(x)):
            result = builder.apply_reductions(tmp_path / "nonexistent.json")

        assert result is None
        assert any("not found" in str(o) for o in output)

    def test_apply_reductions_with_copy(self, builder_with_pkgs, tmp_path):
        """Test apply_reductions copies build when copy_to is specified"""
        # Create a mock manifest
        manifest_path = tmp_path / "manifest.json"
        manifest = {
            "version": "1.0",
            "reductions": {
                "extension_patterns": [],
                "stdlib_to_remove": [],
            }
        }
        with open(manifest_path, "w") as f:
            json.dump(manifest, f)

        # Create a mock build directory
        mock_prefix = tmp_path / "build" / "install" / "python-shared"
        lib_dir = mock_prefix / "lib" / "python3.13"
        lib_dir.mkdir(parents=True)
        (lib_dir / "os.py").write_text("# os module")
        (mock_prefix / "bin").mkdir(parents=True)
        (mock_prefix / "bin" / "python3").write_text("#!/bin/bash")

        # Mock the prefix property
        builder_with_pkgs._prefix_override = mock_prefix

        copy_dir = tmp_path / "reduced"

        with patch('builtins.print'):
            with patch.object(type(builder_with_pkgs), 'prefix', property(lambda self: mock_prefix)):
                result = builder_with_pkgs.apply_reductions(
                    manifest_path=manifest_path,
                    copy_to=copy_dir,
                )

        assert result == copy_dir
        assert copy_dir.exists()

    def test_apply_reductions_removes_extensions(self, builder_with_pkgs, tmp_path):
        """Test that apply_reductions removes extension files"""
        # Create manifest with extension patterns
        manifest_path = tmp_path / "manifest.json"
        manifest = {
            "version": "1.0",
            "reductions": {
                "extension_patterns": ["_tkinter.cpython-*.so", "_tkinter.*.so"],
                "stdlib_to_remove": [],
            }
        }
        with open(manifest_path, "w") as f:
            json.dump(manifest, f)

        # Create a mock build directory with extension files
        mock_prefix = tmp_path / "build" / "install" / "python-shared"
        lib_dir = mock_prefix / "lib" / "python3.13"
        dynload_dir = lib_dir / "lib-dynload"
        dynload_dir.mkdir(parents=True)

        # Create mock extension file
        ext_file = dynload_dir / "_tkinter.cpython-313-darwin.so"
        ext_file.write_bytes(b"mock extension content")

        (mock_prefix / "bin").mkdir(parents=True)
        (mock_prefix / "bin" / "python3").write_text("#!/bin/bash")

        with patch('builtins.print'):
            with patch.object(type(builder_with_pkgs), 'prefix', property(lambda self: mock_prefix)):
                result = builder_with_pkgs.apply_reductions(manifest_path=manifest_path)

        assert result == mock_prefix
        # Extension should be removed
        assert not ext_file.exists()

    def test_apply_reductions_removes_stdlib_dirs(self, builder_with_pkgs, tmp_path):
        """Test that apply_reductions removes stdlib directories"""
        # Create manifest with stdlib paths
        manifest_path = tmp_path / "manifest.json"
        manifest = {
            "version": "1.0",
            "reductions": {
                "extension_patterns": [],
                "stdlib_to_remove": ["tkinter/", "idlelib/"],
            }
        }
        with open(manifest_path, "w") as f:
            json.dump(manifest, f)

        # Create mock build with stdlib directories
        mock_prefix = tmp_path / "build" / "install" / "python-shared"
        lib_dir = mock_prefix / "lib" / "python3.13"
        lib_dir.mkdir(parents=True)

        # Create mock stdlib directories
        tkinter_dir = lib_dir / "tkinter"
        tkinter_dir.mkdir()
        (tkinter_dir / "__init__.py").write_text("# tkinter")

        idlelib_dir = lib_dir / "idlelib"
        idlelib_dir.mkdir()
        (idlelib_dir / "__init__.py").write_text("# idlelib")

        (mock_prefix / "bin").mkdir(parents=True)
        (mock_prefix / "bin" / "python3").write_text("#!/bin/bash")

        with patch('builtins.print'):
            with patch.object(type(builder_with_pkgs), 'prefix', property(lambda self: mock_prefix)):
                result = builder_with_pkgs.apply_reductions(manifest_path=manifest_path)

        assert result == mock_prefix
        # Directories should be removed
        assert not tkinter_dir.exists()
        assert not idlelib_dir.exists()


class TestCoreModulesConstant:
    """Tests for the CORE_MODULES constant"""

    def test_core_modules_defined(self, builder):
        """Test that CORE_MODULES is defined"""
        assert hasattr(builder, 'CORE_MODULES')
        assert isinstance(builder.CORE_MODULES, set)

    def test_core_modules_contains_essential(self, builder):
        """Test that CORE_MODULES contains essential modules"""
        essential = {"_abc", "_io", "_sre", "_codecs", "_thread", "itertools", "posix"}
        for mod in essential:
            assert mod in builder.CORE_MODULES, f"{mod} should be in CORE_MODULES"


class TestStdlibConstants:
    """Tests for the stdlib-related class constants"""

    def test_stdlib_modules_defined(self, builder):
        """Test that STDLIB_MODULES is defined"""
        assert hasattr(builder, 'STDLIB_MODULES')
        assert isinstance(builder.STDLIB_MODULES, set)
        assert len(builder.STDLIB_MODULES) > 100  # Should have many modules

    def test_stdlib_to_extension_defined(self, builder):
        """Test that STDLIB_TO_EXTENSION is defined"""
        assert hasattr(builder, 'STDLIB_TO_EXTENSION')
        assert isinstance(builder.STDLIB_TO_EXTENSION, dict)

    def test_stdlib_to_extension_mappings(self, builder):
        """Test key mappings in STDLIB_TO_EXTENSION"""
        mappings = builder.STDLIB_TO_EXTENSION
        assert "ssl" in mappings
        assert "_ssl" in mappings["ssl"]
        assert "json" in mappings
        assert "_json" in mappings["json"]
        assert "hashlib" in mappings
        assert "_hashlib" in mappings["hashlib"]


class TestIntegration:
    """Integration tests for the auto-configure feature"""

    def test_analyze_deps_then_auto_configure(self, builder_with_pkgs, tmp_path):
        """Test running analyze_deps followed by auto_configure"""
        output_path = tmp_path / "manifest.json"

        with patch('builtins.print'):
            with patch('subprocess.run') as mock_run:
                mock_run.return_value = MagicMock(returncode=1)

                # First, run analyze_deps
                builder_with_pkgs.analyze_deps()

                # Then, run auto_configure
                result = builder_with_pkgs.auto_configure(output_path=output_path)

        assert result == output_path
        assert output_path.exists()

    def test_auto_configure_then_apply_reductions(self, builder_with_pkgs, tmp_path):
        """Test full workflow: analyze -> generate manifest -> apply reductions"""
        manifest_path = tmp_path / "manifest.json"

        # Create mock build directory
        mock_prefix = tmp_path / "build" / "install" / "python-shared"
        lib_dir = mock_prefix / "lib" / "python3.13"
        dynload_dir = lib_dir / "lib-dynload"
        dynload_dir.mkdir(parents=True)
        (mock_prefix / "bin").mkdir(parents=True)
        (mock_prefix / "bin" / "python3").write_text("#!/bin/bash")

        with patch('builtins.print'):
            with patch('subprocess.run') as mock_run:
                mock_run.return_value = MagicMock(returncode=1)

                # Generate manifest
                result = builder_with_pkgs.auto_configure(output_path=manifest_path)
                assert result == manifest_path

                # Apply reductions to a copy
                copy_dir = tmp_path / "reduced"
                with patch.object(type(builder_with_pkgs), 'prefix', property(lambda self: mock_prefix)):
                    result = builder_with_pkgs.apply_reductions(
                        manifest_path=manifest_path,
                        copy_to=copy_dir,
                    )

        assert result == copy_dir
        assert copy_dir.exists()

    def test_auto_configure_idempotent(self, builder_with_pkgs, tmp_path):
        """Test that running auto_configure twice produces same manifest"""
        output_path1 = tmp_path / "manifest1.json"
        output_path2 = tmp_path / "manifest2.json"

        with patch('builtins.print'):
            with patch('subprocess.run') as mock_run:
                mock_run.return_value = MagicMock(returncode=1)

                builder_with_pkgs.auto_configure(output_path=output_path1)
                builder_with_pkgs.auto_configure(output_path=output_path2)

        with open(output_path1) as f1, open(output_path2) as f2:
            manifest1 = json.load(f1)
            manifest2 = json.load(f2)

        # The manifests should be identical
        assert manifest1 == manifest2


class TestManifestWarnings:
    """Tests for manifest warning generation"""

    def test_manifest_includes_disabled_warning(self, mock_project, tmp_path):
        """Test that manifest includes warning when required modules are disabled"""
        builder = PythonBuilder(
            version="3.13.11",
            project=mock_project,
            config="shared_mid",
            pkgs=["requests"],
        )
        builder.log = Mock(spec=logging.Logger)

        # Mock analysis result with needed_but_disabled
        mock_result = AnalysisResult(
            stdlib_imports={"ssl"},
            third_party={"requests"},
            required_extensions={"_ssl"},
            needed_but_disabled={"_ssl", "_hashlib"},
            potentially_unused=set(),
            files_analyzed=5,
        )

        output_path = tmp_path / "manifest.json"

        with patch('builtins.print'):
            with patch.object(builder, '_analyze_package_deps', return_value=mock_result):
                builder.auto_configure(output_path=output_path)

        with open(output_path) as f:
            manifest = json.load(f)

        # Should have a warning about disabled modules
        assert len(manifest["warnings"]) > 0
        warning = manifest["warnings"][0]
        assert warning["type"] == "required_but_disabled"
        assert "_ssl" in warning["modules"]


class TestSharedVanillaConfig:
    """Tests for the shared_vanilla configuration"""

    def test_shared_vanilla_moves_most_static_to_shared(self):
        """Test that shared_vanilla moves most static modules to shared"""
        from buildpy import PythonConfig313, BASE_CONFIG

        config = PythonConfig313(BASE_CONFIG, "shared")
        # Get initial static count
        initial_static = len(config.cfg["static"])
        assert initial_static > 0  # Should have static modules initially

        # Apply shared_vanilla
        config.shared_vanilla()

        # Modules that must stay static (reference internal Python symbols)
        must_stay_static = {
            "_functools", "_locale", "_signal", "_sre", "_thread",
            "posix", "time", "_typing",
        }

        # Only modules that must stay static should remain
        remaining_static = set(config.cfg["static"])
        assert remaining_static.issubset(must_stay_static)
        # Most modules should have been moved to shared
        assert len(config.cfg["shared"]) >= initial_static - len(must_stay_static)

    def test_shared_vanilla_enables_ctypes(self):
        """Test that shared_vanilla enables _ctypes"""
        from buildpy import PythonConfig313, BASE_CONFIG

        config = PythonConfig313(BASE_CONFIG, "shared")
        # _ctypes should be disabled initially
        assert "_ctypes" in config.cfg["disabled"]

        config.shared_vanilla()

        # _ctypes should no longer be disabled
        assert "_ctypes" not in config.cfg["disabled"]

    def test_shared_vanilla_enables_optional_modules(self):
        """Test that shared_vanilla enables optional modules"""
        from buildpy import PythonConfig313, BASE_CONFIG

        config = PythonConfig313(BASE_CONFIG, "shared")

        # Some optional modules should be disabled initially
        initially_disabled = set(config.cfg["disabled"])

        config.shared_vanilla()

        # Several modules should now be enabled
        enabled_modules = {"_ctypes", "_curses", "_curses_panel", "_dbm",
                          "resource", "syslog", "termios"}
        for mod in enabled_modules:
            if mod in initially_disabled:
                assert mod not in config.cfg["disabled"], f"{mod} should be enabled"


class TestAutoReduceCLI:
    """Tests for --auto-reduce CLI argument"""

    def test_auto_reduce_flag(self):
        """Test that --auto-reduce is a boolean flag"""
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument("--auto-reduce", action="store_true")

        args = parser.parse_args([])
        assert args.auto_reduce is False

        args = parser.parse_args(["--auto-reduce"])
        assert args.auto_reduce is True

    def test_auto_reduce_requires_packages(self, builder):
        """Test that auto_reduce fails without packages"""
        # builder has no packages
        assert len(builder.pkgs) == 0

        with patch('builtins.print'):
            result = builder.auto_reduce()

        assert result is False

    def test_auto_reduce_with_packages(self, builder_with_pkgs, tmp_path):
        """Test auto_reduce with packages specified"""
        # Create mock vanilla cache directory (simulating what process() would create)
        vanilla_cache = tmp_path / "build" / "install" / "python-shared-vanilla"
        lib_dir = vanilla_cache / "lib" / "python3.13"
        dynload_dir = lib_dir / "lib-dynload"
        dynload_dir.mkdir(parents=True)
        (lib_dir / "site-packages").mkdir(parents=True)
        (vanilla_cache / "bin").mkdir(parents=True)
        (vanilla_cache / "bin" / "python3").write_text("#!/bin/bash")

        # Mock analysis result
        mock_result = AnalysisResult(
            stdlib_imports={"os", "sys"},
            third_party={"requests"},
            required_extensions={"_socket"},
            needed_but_disabled=set(),
            potentially_unused={"_tkinter"},
            files_analyzed=5,
        )

        # Set up project to use tmp_path
        builder_with_pkgs.project.install = tmp_path / "build" / "install"
        builder_with_pkgs.project.install.mkdir(parents=True, exist_ok=True)

        # Mock subprocess.run for import verification
        mock_subprocess_result = MagicMock()
        mock_subprocess_result.returncode = 0

        with patch('builtins.print'):
            with patch.object(builder_with_pkgs, '_analyze_package_deps', return_value=mock_result):
                with patch.object(builder_with_pkgs, 'ziplib'):
                    with patch.object(builder_with_pkgs, 'install_pkgs'):
                        with patch('subprocess.run', return_value=mock_subprocess_result):
                            # process() won't be called since vanilla_cache exists
                            result = builder_with_pkgs.auto_reduce()

        assert result is True
        # Reduced build should exist
        reduced_prefix = tmp_path / "build" / "install" / "python-shared-reduced"
        assert reduced_prefix.exists()

    def test_auto_reduce_builds_vanilla_if_not_cached(self, builder_with_pkgs, tmp_path):
        """Test that auto_reduce builds vanilla if cache doesn't exist"""
        # Set up project to use tmp_path (no vanilla cache)
        builder_with_pkgs.project.install = tmp_path / "build" / "install"
        builder_with_pkgs.project.install.mkdir(parents=True, exist_ok=True)

        mock_result = AnalysisResult(
            stdlib_imports={"os"},
            third_party={"requests"},
            required_extensions=set(),
            needed_but_disabled=set(),
            potentially_unused=set(),
            files_analyzed=1,
        )

        process_called = []

        def mock_process():
            # Simulate process() creating the vanilla cache
            vanilla_cache = tmp_path / "build" / "install" / "python-shared-vanilla"
            lib_dir = vanilla_cache / "lib" / "python3.13"
            (lib_dir / "lib-dynload").mkdir(parents=True)
            (lib_dir / "site-packages").mkdir(parents=True)
            (vanilla_cache / "bin").mkdir(parents=True)
            (vanilla_cache / "bin" / "python3").write_text("#!/bin/bash")
            process_called.append(True)

        # Mock subprocess.run for import verification
        mock_subprocess_result = MagicMock()
        mock_subprocess_result.returncode = 0

        with patch('builtins.print'):
            with patch.object(builder_with_pkgs, '_analyze_package_deps', return_value=mock_result):
                with patch.object(builder_with_pkgs, 'process', side_effect=mock_process):
                    with patch.object(builder_with_pkgs, 'ziplib'):
                        with patch.object(builder_with_pkgs, 'install_pkgs'):
                            with patch('subprocess.run', return_value=mock_subprocess_result):
                                result = builder_with_pkgs.auto_reduce()

        assert result is True
        # process() should have been called to build vanilla
        assert len(process_called) == 1

    def test_auto_reduce_uses_cached_vanilla(self, builder_with_pkgs, tmp_path):
        """Test that auto_reduce uses cached vanilla without rebuilding"""
        # Create pre-existing vanilla cache
        vanilla_cache = tmp_path / "build" / "install" / "python-shared-vanilla"
        lib_dir = vanilla_cache / "lib" / "python3.13"
        (lib_dir / "lib-dynload").mkdir(parents=True)
        (lib_dir / "site-packages").mkdir(parents=True)
        (vanilla_cache / "bin").mkdir(parents=True)
        (vanilla_cache / "bin" / "python3").write_text("#!/bin/bash")

        builder_with_pkgs.project.install = tmp_path / "build" / "install"

        mock_result = AnalysisResult(
            stdlib_imports={"os"},
            third_party={"requests"},
            required_extensions=set(),
            needed_but_disabled=set(),
            potentially_unused=set(),
            files_analyzed=1,
        )

        process_called = []

        def mock_process():
            process_called.append(True)

        # Mock subprocess.run for import verification
        mock_subprocess_result = MagicMock()
        mock_subprocess_result.returncode = 0

        with patch('builtins.print'):
            with patch.object(builder_with_pkgs, '_analyze_package_deps', return_value=mock_result):
                with patch.object(builder_with_pkgs, 'process', side_effect=mock_process):
                    with patch.object(builder_with_pkgs, 'ziplib'):
                        with patch.object(builder_with_pkgs, 'install_pkgs'):
                            with patch('subprocess.run', return_value=mock_subprocess_result):
                                result = builder_with_pkgs.auto_reduce()

        assert result is True
        # process() should NOT have been called since cache exists
        assert len(process_called) == 0

    def test_auto_reduce_changes_config_to_shared_vanilla(self, builder_with_pkgs, tmp_path):
        """Test that auto_reduce uses shared_vanilla config when building"""
        builder_with_pkgs.project.install = tmp_path / "build" / "install"
        builder_with_pkgs.project.install.mkdir(parents=True, exist_ok=True)

        mock_result = AnalysisResult(
            stdlib_imports={"os"},
            third_party={"requests"},
            required_extensions=set(),
            needed_but_disabled=set(),
            potentially_unused=set(),
            files_analyzed=1,
        )

        config_during_build = []

        def mock_process():
            config_during_build.append(builder_with_pkgs.config)
            # Create vanilla cache
            vanilla_cache = tmp_path / "build" / "install" / "python-shared-vanilla"
            lib_dir = vanilla_cache / "lib" / "python3.13"
            (lib_dir / "lib-dynload").mkdir(parents=True)
            (lib_dir / "site-packages").mkdir(parents=True)
            (vanilla_cache / "bin").mkdir(parents=True)
            (vanilla_cache / "bin" / "python3").write_text("#!/bin/bash")

        original_config = builder_with_pkgs.config
        assert original_config == "shared_mid"

        with patch('builtins.print'):
            with patch.object(builder_with_pkgs, '_analyze_package_deps', return_value=mock_result):
                with patch.object(builder_with_pkgs, 'process', side_effect=mock_process):
                    with patch.object(builder_with_pkgs, 'ziplib'):
                        with patch.object(builder_with_pkgs, 'install_pkgs'):
                            builder_with_pkgs.auto_reduce()

        # Config should have been shared_vanilla during build
        assert "shared_vanilla" in config_during_build
        # Config should be restored after
        assert builder_with_pkgs.config == original_config

    def test_auto_reduce_calls_ziplib_at_end(self, builder_with_pkgs, tmp_path):
        """Test that auto_reduce calls ziplib at the end"""
        # Create pre-existing vanilla cache
        vanilla_cache = tmp_path / "build" / "install" / "python-shared-vanilla"
        lib_dir = vanilla_cache / "lib" / "python3.13"
        (lib_dir / "lib-dynload").mkdir(parents=True)
        (lib_dir / "site-packages").mkdir(parents=True)
        (vanilla_cache / "bin").mkdir(parents=True)
        (vanilla_cache / "bin" / "python3").write_text("#!/bin/bash")

        builder_with_pkgs.project.install = tmp_path / "build" / "install"

        mock_result = AnalysisResult(
            stdlib_imports={"os"},
            third_party={"requests"},
            required_extensions=set(),
            needed_but_disabled=set(),
            potentially_unused=set(),
            files_analyzed=1,
        )

        ziplib_called = []

        def mock_ziplib():
            ziplib_called.append(True)

        with patch('builtins.print'):
            with patch.object(builder_with_pkgs, '_analyze_package_deps', return_value=mock_result):
                with patch.object(builder_with_pkgs, 'ziplib', side_effect=mock_ziplib):
                    with patch.object(builder_with_pkgs, 'install_pkgs'):
                        builder_with_pkgs.auto_reduce()

        # ziplib should have been called
        assert len(ziplib_called) == 1
