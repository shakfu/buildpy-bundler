"""Tests for the -n/--dry-run feature"""

import pytest
from io import StringIO
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


class TestDryRunMethod:
    """Tests for the dry_run() method"""

    def test_dry_run_does_not_build(self, builder):
        """Test that dry_run does not call any build methods"""
        with patch.object(builder, 'setup') as mock_setup, \
             patch.object(builder, 'configure') as mock_configure, \
             patch.object(builder, 'build') as mock_build, \
             patch.object(builder, 'install') as mock_install, \
             patch('builtins.print'):
            builder.dry_run()

            mock_setup.assert_not_called()
            mock_configure.assert_not_called()
            mock_build.assert_not_called()
            mock_install.assert_not_called()

    def test_dry_run_prints_output(self, builder):
        """Test that dry_run produces output"""
        output = []
        with patch('builtins.print', side_effect=lambda x: output.append(x)):
            builder.dry_run()

        # Join all output
        full_output = '\n'.join(str(x) for x in output)

        # Check key sections are present
        assert "BUILD PLAN" in full_output
        assert "Build Target" in full_output
        assert "Directories" in full_output
        assert "Build Options" in full_output
        assert "Configure Options" in full_output
        assert "Dependencies" in full_output
        assert "Modules - Core" in full_output
        assert "Modules - Static" in full_output
        assert "No changes were made" in full_output

    def test_dry_run_shows_python_version(self, builder):
        """Test that dry_run displays Python version"""
        output = []
        with patch('builtins.print', side_effect=lambda x: output.append(x)):
            builder.dry_run()

        full_output = '\n'.join(str(x) for x in output)
        assert "3.13.11" in full_output

    def test_dry_run_shows_config(self, builder):
        """Test that dry_run displays configuration"""
        output = []
        with patch('builtins.print', side_effect=lambda x: output.append(x)):
            builder.dry_run()

        full_output = '\n'.join(str(x) for x in output)
        assert "shared_mid" in full_output
        assert "shared" in full_output  # build type
        assert "mid" in full_output  # size type

    def test_dry_run_shows_packages(self, mock_project):
        """Test that dry_run displays packages to install"""
        builder = PythonBuilder(
            version="3.13.11",
            project=mock_project,
            config="shared_mid",
            pkgs=["requests", "numpy"],
        )
        builder.log = Mock(spec=logging.Logger)

        output = []
        with patch('builtins.print', side_effect=lambda x: output.append(x)):
            builder.dry_run()

        full_output = '\n'.join(str(x) for x in output)
        assert "Packages to Install" in full_output
        assert "requests" in full_output
        assert "numpy" in full_output

    def test_dry_run_shows_optimize_options(self, mock_project):
        """Test that dry_run displays optimization options"""
        builder = PythonBuilder(
            version="3.13.11",
            project=mock_project,
            config="shared_mid",
            optimize=True,
        )
        builder.log = Mock(spec=logging.Logger)

        output = []
        with patch('builtins.print', side_effect=lambda x: output.append(x)):
            builder.dry_run()

        full_output = '\n'.join(str(x) for x in output)
        assert "--enable-optimizations" in full_output
        assert "Optimize build:    True" in full_output

    def test_dry_run_shows_dependencies(self, builder):
        """Test that dry_run displays dependencies"""
        output = []
        with patch('builtins.print', side_effect=lambda x: output.append(x)):
            builder.dry_run()

        full_output = '\n'.join(str(x) for x in output)
        assert "openssl" in full_output
        assert "bzip2" in full_output
        assert "xz" in full_output


class TestDryRunCLI:
    """Tests for CLI argument parsing of -n/--dry-run"""

    def test_dry_run_short_argument(self):
        """Test parsing -n argument"""
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument("-n", "--dry-run", action="store_true")

        args = parser.parse_args(["-n"])
        assert args.dry_run is True

    def test_dry_run_long_argument(self):
        """Test parsing --dry-run argument"""
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument("-n", "--dry-run", action="store_true")

        args = parser.parse_args(["--dry-run"])
        assert args.dry_run is True

    def test_dry_run_default_false(self):
        """Test that dry_run defaults to False"""
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument("-n", "--dry-run", action="store_true")

        args = parser.parse_args([])
        assert args.dry_run is False


class TestDryRunStaticConfig:
    """Tests for dry_run with static build configuration"""

    def test_dry_run_static_config(self, mock_project):
        """Test dry_run with static_mid configuration"""
        builder = PythonBuilder(
            version="3.13.11",
            project=mock_project,
            config="static_mid",
        )
        builder.log = Mock(spec=logging.Logger)

        output = []
        with patch('builtins.print', side_effect=lambda x: output.append(x)):
            builder.dry_run()

        full_output = '\n'.join(str(x) for x in output)
        assert "static_mid" in full_output
        assert "--disable-shared" in full_output


class TestDryRunCustomOptions:
    """Tests for dry_run with custom config options"""

    def test_dry_run_with_cfg_opts(self, mock_project):
        """Test dry_run with custom config options"""
        builder = PythonBuilder(
            version="3.13.11",
            project=mock_project,
            config="shared_mid",
            cfg_opts=["with_lto"],
        )
        builder.log = Mock(spec=logging.Logger)

        output = []
        with patch('builtins.print', side_effect=lambda x: output.append(x)):
            builder.dry_run()

        full_output = '\n'.join(str(x) for x in output)
        assert "--with-lto" in full_output
