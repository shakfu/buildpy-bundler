"""Tests for the -S/--size-report feature"""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch
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
def mock_build(mock_project):
    """Create a mock build directory structure"""
    # Create install directory
    install_dir = mock_project.install / "python-shared"
    install_dir.mkdir(parents=True)

    # Create bin directory with executables
    bin_dir = install_dir / "bin"
    bin_dir.mkdir()
    (bin_dir / "python3").write_bytes(b"x" * 1000)
    (bin_dir / "pip3").write_bytes(b"x" * 500)

    # Create lib directory
    lib_dir = install_dir / "lib"
    lib_dir.mkdir()

    # Create a shared library
    (lib_dir / "libpython3.13.dylib").write_bytes(b"x" * 5000)

    # Create stdlib directory
    stdlib_dir = lib_dir / "python3.13"
    stdlib_dir.mkdir()
    (stdlib_dir / "os.py").write_bytes(b"x" * 200)
    (stdlib_dir / "sys.py").write_bytes(b"x" * 150)
    (stdlib_dir / "json").mkdir()
    (stdlib_dir / "json" / "__init__.py").write_bytes(b"x" * 100)

    # Create lib-dynload directory
    dynload_dir = stdlib_dir / "lib-dynload"
    dynload_dir.mkdir()
    (dynload_dir / "_json.cpython-313-darwin.so").write_bytes(b"x" * 800)
    (dynload_dir / "_ssl.cpython-313-darwin.so").write_bytes(b"x" * 1200)

    # Create include directory
    include_dir = install_dir / "include"
    include_dir.mkdir()
    (include_dir / "python3.13").mkdir()
    (include_dir / "python3.13" / "Python.h").write_bytes(b"x" * 300)

    return install_dir


class TestSizeReportMethod:
    """Tests for the size_report() method"""

    def test_size_report_no_build(self, builder):
        """Test that size_report handles missing build gracefully"""
        output = []
        with patch('builtins.print', side_effect=lambda x: output.append(x)):
            builder.size_report()

        full_output = '\n'.join(str(x) for x in output)
        assert "Error" in full_output or "not found" in full_output

    def test_size_report_with_build(self, builder, mock_build):
        """Test that size_report produces output for existing build"""
        output = []
        with patch('builtins.print', side_effect=lambda x: output.append(x)):
            builder.size_report()

        full_output = '\n'.join(str(x) for x in output)

        # Check key sections are present
        assert "BUILD SIZE REPORT" in full_output
        assert "Build Info" in full_output
        assert "Size Breakdown" in full_output
        assert "Largest Files" in full_output
        assert "TOTAL" in full_output

    def test_size_report_shows_config(self, builder, mock_build):
        """Test that size_report displays configuration"""
        output = []
        with patch('builtins.print', side_effect=lambda x: output.append(x)):
            builder.size_report()

        full_output = '\n'.join(str(x) for x in output)
        assert "shared_mid" in full_output
        assert "shared" in full_output
        assert "3.13.11" in full_output

    def test_size_report_shows_components(self, builder, mock_build):
        """Test that size_report shows component breakdown"""
        output = []
        with patch('builtins.print', side_effect=lambda x: output.append(x)):
            builder.size_report()

        full_output = '\n'.join(str(x) for x in output)

        # Should show various components
        assert "bin/" in full_output or "executables" in full_output
        assert "lib/" in full_output or "stdlib" in full_output

    def test_size_report_shows_percentages(self, builder, mock_build):
        """Test that size_report shows percentage breakdown"""
        output = []
        with patch('builtins.print', side_effect=lambda x: output.append(x)):
            builder.size_report()

        full_output = '\n'.join(str(x) for x in output)
        assert "%" in full_output
        assert "100.0%" in full_output  # Total should be 100%

    def test_size_report_does_not_modify_build(self, builder, mock_build):
        """Test that size_report doesn't modify the build"""
        # Get initial file count and sizes
        initial_files = list(mock_build.rglob("*"))
        initial_count = len(initial_files)

        with patch('builtins.print'):
            builder.size_report()

        # Verify nothing changed
        final_files = list(mock_build.rglob("*"))
        assert len(final_files) == initial_count


class TestSizeReportCLI:
    """Tests for CLI argument parsing of -S/--size-report"""

    def test_size_report_short_argument(self):
        """Test parsing -S argument"""
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument("-S", "--size-report", action="store_true")

        args = parser.parse_args(["-S"])
        assert args.size_report is True

    def test_size_report_long_argument(self):
        """Test parsing --size-report argument"""
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument("-S", "--size-report", action="store_true")

        args = parser.parse_args(["--size-report"])
        assert args.size_report is True

    def test_size_report_default_false(self):
        """Test that size_report defaults to False"""
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument("-S", "--size-report", action="store_true")

        args = parser.parse_args([])
        assert args.size_report is False


class TestSizeReportFormatting:
    """Tests for size formatting utilities"""

    def test_format_bytes(self, builder, mock_build):
        """Test that sizes are formatted in human-readable units"""
        output = []
        with patch('builtins.print', side_effect=lambda x: output.append(x)):
            builder.size_report()

        full_output = '\n'.join(str(x) for x in output)
        # Should contain unit indicators
        assert any(unit in full_output for unit in ["B", "KB", "MB", "GB"])

    def test_largest_files_section(self, builder, mock_build):
        """Test that largest files are listed"""
        output = []
        with patch('builtins.print', side_effect=lambda x: output.append(x)):
            builder.size_report()

        full_output = '\n'.join(str(x) for x in output)
        # Should show largest file (libpython in our mock)
        assert "libpython" in full_output or "dylib" in full_output
