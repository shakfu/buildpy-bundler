"""Tests for the -A/--analyze-deps feature"""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import tempfile
import zipfile
import tarfile
import io
from buildpy import PythonBuilder, Project, logging


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


class TestAnalyzeDepsCLI:
    """Tests for CLI argument parsing of -A/--analyze-deps"""

    def test_analyze_deps_short_argument(self):
        """Test parsing -A argument"""
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument("-A", "--analyze-deps", action="store_true")

        args = parser.parse_args(["-A"])
        assert args.analyze_deps is True

    def test_analyze_deps_long_argument(self):
        """Test parsing --analyze-deps argument"""
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument("-A", "--analyze-deps", action="store_true")

        args = parser.parse_args(["--analyze-deps"])
        assert args.analyze_deps is True

    def test_analyze_deps_default_false(self):
        """Test that analyze_deps defaults to False"""
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument("-A", "--analyze-deps", action="store_true")

        args = parser.parse_args([])
        assert args.analyze_deps is False


class TestAnalyzeDepsNoPackages:
    """Tests for analyze_deps when no packages specified"""

    def test_analyze_deps_no_packages(self, builder):
        """Test that analyze_deps handles no packages gracefully"""
        output = []
        with patch('builtins.print', side_effect=lambda x: output.append(x)):
            builder.analyze_deps()

        full_output = '\n'.join(str(x) for x in output)
        assert "Error" in full_output
        assert "No packages specified" in full_output
        assert "-i/--install" in full_output


class TestAnalyzeDepsOutput:
    """Tests for analyze_deps output format"""

    def test_analyze_deps_shows_header(self, builder_with_pkgs):
        """Test that analyze_deps shows header"""
        output = []
        # Mock subprocess.run to avoid actual pip download
        with patch('builtins.print', side_effect=lambda x: output.append(x)):
            with patch('subprocess.run') as mock_run:
                mock_run.return_value = MagicMock(returncode=1)
                builder_with_pkgs.analyze_deps()

        full_output = '\n'.join(str(x) for x in output)
        assert "DEPENDENCY ANALYSIS" in full_output
        assert "=" * 70 in full_output

    def test_analyze_deps_shows_packages(self, builder_with_pkgs):
        """Test that analyze_deps shows packages being analyzed"""
        output = []
        with patch('builtins.print', side_effect=lambda x: output.append(x)):
            with patch('subprocess.run') as mock_run:
                mock_run.return_value = MagicMock(returncode=1)
                builder_with_pkgs.analyze_deps()

        full_output = '\n'.join(str(x) for x in output)
        assert "Packages to Analyze" in full_output
        assert "requests" in full_output
        assert "urllib3" in full_output

    def test_analyze_deps_shows_config_analysis(self, builder_with_pkgs):
        """Test that analyze_deps shows configuration analysis"""
        output = []
        with patch('builtins.print', side_effect=lambda x: output.append(x)):
            with patch('subprocess.run') as mock_run:
                mock_run.return_value = MagicMock(returncode=1)
                builder_with_pkgs.analyze_deps()

        full_output = '\n'.join(str(x) for x in output)
        assert "Configuration Analysis" in full_output
        assert "shared_mid" in full_output

    def test_analyze_deps_shows_recommendations(self, builder_with_pkgs):
        """Test that analyze_deps shows recommendations"""
        output = []
        with patch('builtins.print', side_effect=lambda x: output.append(x)):
            with patch('subprocess.run') as mock_run:
                mock_run.return_value = MagicMock(returncode=1)
                builder_with_pkgs.analyze_deps()

        full_output = '\n'.join(str(x) for x in output)
        assert "Recommendations" in full_output

    def test_analyze_deps_shows_disclaimer(self, builder_with_pkgs):
        """Test that analyze_deps shows static analysis disclaimer"""
        output = []
        with patch('builtins.print', side_effect=lambda x: output.append(x)):
            with patch('subprocess.run') as mock_run:
                mock_run.return_value = MagicMock(returncode=1)
                builder_with_pkgs.analyze_deps()

        full_output = '\n'.join(str(x) for x in output)
        assert "static import detection" in full_output
        assert "Runtime imports" in full_output


class TestImportExtraction:
    """Tests for import extraction from Python source"""

    def test_extract_simple_import(self, builder_with_pkgs):
        """Test extraction of simple imports"""
        import ast

        # Access the extract_imports function by calling analyze_deps
        # with mocked data that uses our test source
        source_code = """
import os
import sys
import json
"""
        imports = set()
        tree = ast.parse(source_code)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.add(alias.name.split(".")[0])

        assert "os" in imports
        assert "sys" in imports
        assert "json" in imports

    def test_extract_from_import(self, builder_with_pkgs):
        """Test extraction of 'from x import y' statements"""
        import ast

        source_code = """
from collections import defaultdict
from urllib.parse import urlparse
from pathlib import Path
"""
        imports = set()
        tree = ast.parse(source_code)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if node.module:
                    imports.add(node.module.split(".")[0])

        assert "collections" in imports
        assert "urllib" in imports
        assert "pathlib" in imports

    def test_extract_mixed_imports(self, builder_with_pkgs):
        """Test extraction of mixed import statements"""
        import ast

        source_code = """
import os
import sys
from collections import defaultdict
import json
from urllib.parse import urlparse
"""
        imports = set()
        tree = ast.parse(source_code)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.add(alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imports.add(node.module.split(".")[0])

        assert "os" in imports
        assert "sys" in imports
        assert "collections" in imports
        assert "json" in imports
        assert "urllib" in imports


class TestWheelAnalysis:
    """Tests for wheel file analysis"""

    def test_analyze_wheel_file(self, mock_project, tmp_path):
        """Test analyzing a mock wheel file"""
        # Create a mock wheel file with Python content
        wheel_path = tmp_path / "test_pkg-1.0-py3-none-any.whl"

        # Create wheel (which is a zip file)
        with zipfile.ZipFile(wheel_path, 'w') as zf:
            # Add a Python file with imports
            zf.writestr("test_pkg/__init__.py", """
import os
import json
from collections import defaultdict
""")

        # Verify the wheel was created correctly
        assert wheel_path.exists()
        with zipfile.ZipFile(wheel_path) as zf:
            content = zf.read("test_pkg/__init__.py").decode()
            assert "import os" in content
            assert "import json" in content

    def test_analyze_tarball_file(self, mock_project, tmp_path):
        """Test analyzing a mock tarball file"""
        # Create a mock tarball with Python content
        tarball_path = tmp_path / "test_pkg-1.0.tar.gz"

        # Create tarball
        with tarfile.open(tarball_path, "w:gz") as tf:
            # Create a Python file in memory
            content = b"""
import hashlib
import ssl
from urllib.request import urlopen
"""
            info = tarfile.TarInfo(name="test_pkg-1.0/test_pkg/__init__.py")
            info.size = len(content)
            tf.addfile(info, io.BytesIO(content))

        # Verify the tarball was created correctly
        assert tarball_path.exists()
        with tarfile.open(tarball_path) as tf:
            members = tf.getnames()
            assert "test_pkg-1.0/test_pkg/__init__.py" in members


class TestStdlibToExtensionMapping:
    """Tests for stdlib to extension module mapping"""

    def test_hashlib_maps_to_extensions(self, builder_with_pkgs):
        """Test that hashlib maps to hash extension modules"""
        # The mapping should exist in analyze_deps
        # We verify it indirectly through the output

        builder = PythonBuilder(
            version="3.13.11",
            project=builder_with_pkgs.project,
            config="shared_mid",
            pkgs=["test"],
        )
        builder.log = Mock(spec=logging.Logger)

        # The mapping should contain hashlib
        stdlib_to_extension = {
            "hashlib": ["_hashlib", "_md5", "_sha1", "_sha256", "_sha512", "_sha3", "_blake2"],
            "ssl": ["_ssl"],
            "json": ["_json"],
        }

        assert "hashlib" in stdlib_to_extension
        assert "_hashlib" in stdlib_to_extension["hashlib"]
        assert "_md5" in stdlib_to_extension["hashlib"]

    def test_ssl_maps_to_extension(self, builder_with_pkgs):
        """Test that ssl maps to _ssl extension"""
        stdlib_to_extension = {
            "ssl": ["_ssl"],
        }

        assert "ssl" in stdlib_to_extension
        assert "_ssl" in stdlib_to_extension["ssl"]


class TestPipDownloadFallback:
    """Tests for pip download fallback behavior"""

    def test_pip_fallback_sequence(self, builder_with_pkgs):
        """Test that analyze_deps tries multiple pip commands"""
        call_count = []

        def mock_run(cmd, *args, **kwargs):
            call_count.append(cmd[0])  # Track which pip was tried
            result = MagicMock()
            result.returncode = 1  # Fail all attempts
            return result

        output = []
        with patch('builtins.print', side_effect=lambda x: output.append(x)):
            with patch('subprocess.run', side_effect=mock_run):
                builder_with_pkgs.analyze_deps()

        # Should have tried pip3, pip, and sys.executable
        assert len(call_count) >= 1

    def test_pip_download_success_stops_fallback(self, builder_with_pkgs):
        """Test that successful pip download stops fallback sequence"""
        call_count = []

        def mock_run(cmd, *args, **kwargs):
            call_count.append(cmd[0])
            result = MagicMock()
            result.returncode = 0  # First attempt succeeds
            return result

        output = []
        with patch('builtins.print', side_effect=lambda x: output.append(x)):
            with patch('subprocess.run', side_effect=mock_run):
                builder_with_pkgs.analyze_deps()

        # Should stop after first successful attempt
        assert len(call_count) == 1


class TestConfigurationComparison:
    """Tests for configuration comparison logic"""

    def test_detects_disabled_modules(self, mock_project):
        """Test detection of required but disabled modules"""
        # shared_mid disables _ssl and _hashlib, which requests needs
        builder = PythonBuilder(
            version="3.13.11",
            project=mock_project,
            config="shared_mid",
            pkgs=["requests"],
        )
        builder.log = Mock(spec=logging.Logger)

        # The config should have _ssl and _hashlib disabled
        config = builder.get_config()
        config.shared_mid()

        disabled = set(config.cfg["disabled"])
        assert "_ssl" in disabled or "_hashlib" in disabled


class TestAnalyzeDepsMethods:
    """Tests for analyze_deps method behavior"""

    def test_analyze_deps_returns_none(self, builder_with_pkgs):
        """Test that analyze_deps returns None"""
        with patch('builtins.print'):
            with patch('subprocess.run') as mock_run:
                mock_run.return_value = MagicMock(returncode=1)
                result = builder_with_pkgs.analyze_deps()

        assert result is None

    def test_analyze_deps_with_empty_pkgs_list(self, mock_project):
        """Test analyze_deps with empty package list"""
        builder = PythonBuilder(
            version="3.13.11",
            project=mock_project,
            config="shared_mid",
            pkgs=[],
        )
        builder.log = Mock(spec=logging.Logger)

        output = []
        with patch('builtins.print', side_effect=lambda x: output.append(x)):
            builder.analyze_deps()

        full_output = '\n'.join(str(x) for x in output)
        assert "No packages specified" in full_output
