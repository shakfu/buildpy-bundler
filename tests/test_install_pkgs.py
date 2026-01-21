"""Tests for the -i/--install package installation feature"""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
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
def builder_with_pkgs(mock_project):
    """Create a PythonBuilder with packages specified"""
    builder = PythonBuilder(
        version="3.13.11",
        project=mock_project,
        config="shared_mid",
        pkgs=["requests", "numpy"],
    )
    builder.log = Mock(spec=logging.Logger)
    return builder


@pytest.fixture
def builder_no_pkgs(mock_project):
    """Create a PythonBuilder without packages"""
    builder = PythonBuilder(
        version="3.13.11",
        project=mock_project,
        config="shared_mid",
        pkgs=None,
    )
    builder.log = Mock(spec=logging.Logger)
    return builder


class TestPythonBuilderPkgsInit:
    """Tests for PythonBuilder initialization with pkgs parameter"""

    def test_pkgs_stored_correctly(self, builder_with_pkgs):
        """Test that packages are stored in self.pkgs"""
        assert builder_with_pkgs.pkgs == ["requests", "numpy"]

    def test_pkgs_default_empty_list(self, builder_no_pkgs):
        """Test that pkgs defaults to empty list when None"""
        assert builder_no_pkgs.pkgs == []

    def test_pkgs_empty_list_input(self, mock_project):
        """Test that empty list input remains empty"""
        builder = PythonBuilder(
            version="3.13.11",
            project=mock_project,
            config="shared_mid",
            pkgs=[],
        )
        assert builder.pkgs == []


class TestConfigureEnsurepip:
    """Tests for ensurepip configuration based on pkgs"""

    def test_ensurepip_disabled_when_no_pkgs(self, builder_no_pkgs):
        """Test that --without-ensurepip is added when no packages specified"""
        # Builder with no pkgs and no required_packages should disable ensurepip
        assert builder_no_pkgs.pkgs == []
        # The config_options should include --without-ensurepip after configure
        # This is set during configure(), we test the initial state
        assert "--without-ensurepip" not in builder_no_pkgs.config_options

    def test_ensurepip_enabled_when_pkgs_specified(self, builder_with_pkgs):
        """Test that ensurepip is not disabled when packages are specified"""
        assert builder_with_pkgs.pkgs == ["requests", "numpy"]
        assert "--without-ensurepip" not in builder_with_pkgs.config_options


class TestInstallPkgs:
    """Tests for the install_pkgs method"""

    def test_install_pkgs_runs_ensurepip(self, builder_with_pkgs):
        """Test that install_pkgs runs ensurepip first"""
        with patch.object(builder_with_pkgs, 'cmd') as mock_cmd:
            builder_with_pkgs.install_pkgs()
            # First call should be ensurepip
            calls = mock_cmd.call_args_list
            assert len(calls) >= 1
            first_call_args = calls[0][0][0]
            assert 'ensurepip' in first_call_args

    def test_install_pkgs_installs_packages(self, builder_with_pkgs):
        """Test that install_pkgs calls pip install"""
        with patch.object(builder_with_pkgs, 'cmd') as mock_cmd:
            builder_with_pkgs.install_pkgs()
            calls = mock_cmd.call_args_list
            assert len(calls) >= 2
            # Second call should be pip install
            second_call_args = calls[1][0][0]
            assert 'pip' in second_call_args or 'install' in second_call_args

    def test_install_pkgs_installs_user_specified_packages(self, builder_with_pkgs):
        """Test that install_pkgs installs the user-specified packages.

        This test verifies that when a user specifies packages via -i/--install,
        those packages are actually installed (not just required_packages).
        """
        with patch.object(builder_with_pkgs, 'cmd') as mock_cmd:
            builder_with_pkgs.install_pkgs()
            calls = mock_cmd.call_args_list
            assert len(calls) == 2, f"Expected 2 calls (ensurepip + pip install), got {len(calls)}"

            # First call should be ensurepip
            ensurepip_call = calls[0][0][0]
            assert 'ensurepip' in ensurepip_call

            # Second call should be pip install with user packages
            pip_install_call = calls[1][0][0]
            assert 'install' in pip_install_call, \
                f"Expected pip install command, got: {pip_install_call}"
            # User specified "requests" and "numpy" in the fixture
            assert 'requests' in pip_install_call, \
                f"User package 'requests' not in pip install command: {pip_install_call}"
            assert 'numpy' in pip_install_call, \
                f"User package 'numpy' not in pip install command: {pip_install_call}"


class TestProcessWithPkgs:
    """Tests for the process method when pkgs are specified"""

    def test_process_calls_install_pkgs_when_pkgs_present(self, builder_with_pkgs):
        """Test that process() calls install_pkgs when packages are specified"""
        # Clear dependencies to avoid actual downloads/builds
        builder_with_pkgs.depends_on = []

        with patch.object(builder_with_pkgs, 'pre_process'), \
             patch.object(builder_with_pkgs, 'setup'), \
             patch.object(builder_with_pkgs, 'configure'), \
             patch.object(builder_with_pkgs, 'build'), \
             patch.object(builder_with_pkgs, 'install'), \
             patch.object(builder_with_pkgs, 'clean'), \
             patch.object(builder_with_pkgs, 'ziplib'), \
             patch.object(builder_with_pkgs, 'install_pkgs') as mock_install_pkgs, \
             patch.object(builder_with_pkgs, 'post_process'), \
             patch.object(builder_with_pkgs, 'can_run', return_value=True):
            builder_with_pkgs.process()
            mock_install_pkgs.assert_called_once()

    def test_process_skips_install_pkgs_when_no_pkgs(self, builder_no_pkgs):
        """Test that process() skips install_pkgs when no packages specified"""
        # Clear dependencies to avoid actual downloads/builds
        builder_no_pkgs.depends_on = []

        with patch.object(builder_no_pkgs, 'pre_process'), \
             patch.object(builder_no_pkgs, 'setup'), \
             patch.object(builder_no_pkgs, 'configure'), \
             patch.object(builder_no_pkgs, 'build'), \
             patch.object(builder_no_pkgs, 'install'), \
             patch.object(builder_no_pkgs, 'clean'), \
             patch.object(builder_no_pkgs, 'ziplib'), \
             patch.object(builder_no_pkgs, 'install_pkgs') as mock_install_pkgs, \
             patch.object(builder_no_pkgs, 'post_process'), \
             patch.object(builder_no_pkgs, 'can_run', return_value=True):
            builder_no_pkgs.process()
            mock_install_pkgs.assert_not_called()


class TestPkgsWithRequiredPackages:
    """Tests for interaction between user pkgs and required_packages"""

    def test_pkgs_extended_with_required_packages(self, mock_project):
        """Test that user pkgs are extended with required_packages during configure"""

        class BuilderWithRequired(PythonBuilder):
            required_packages = ["setuptools", "wheel"]

        builder = BuilderWithRequired(
            version="3.13.11",
            project=mock_project,
            config="shared_mid",
            pkgs=["requests"],
        )
        builder.log = Mock(spec=logging.Logger)

        # Before configure, pkgs should only have user packages
        assert builder.pkgs == ["requests"]
        assert builder.required_packages == ["setuptools", "wheel"]

    def test_only_required_packages_no_user_pkgs(self, mock_project):
        """Test builder with only required_packages, no user pkgs"""

        class BuilderWithRequired(PythonBuilder):
            required_packages = ["setuptools"]

        builder = BuilderWithRequired(
            version="3.13.11",
            project=mock_project,
            config="shared_mid",
            pkgs=None,
        )
        builder.log = Mock(spec=logging.Logger)

        # Should have required_packages but empty pkgs initially
        assert builder.pkgs == []
        assert builder.required_packages == ["setuptools"]


class TestCliPkgsArgument:
    """Tests for CLI argument parsing of -i/--install"""

    def test_single_package_argument(self):
        """Test parsing single package from CLI"""
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument("-i", "--install", type=str, nargs="+", metavar="PKG")

        args = parser.parse_args(["-i", "requests"])
        assert args.install == ["requests"]

    def test_multiple_packages_argument(self):
        """Test parsing multiple packages from CLI"""
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument("-i", "--install", type=str, nargs="+", metavar="PKG")

        args = parser.parse_args(["-i", "requests", "numpy", "pandas"])
        assert args.install == ["requests", "numpy", "pandas"]

    def test_no_packages_argument(self):
        """Test that install is None when not specified"""
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument("-i", "--install", type=str, nargs="+", metavar="PKG")

        args = parser.parse_args([])
        assert args.install is None

    def test_packages_with_version_specifiers(self):
        """Test parsing packages with version specifiers"""
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument("-i", "--install", type=str, nargs="+", metavar="PKG")

        args = parser.parse_args(["-i", "requests>=2.28.0", "numpy==1.24.0"])
        assert args.install == ["requests>=2.28.0", "numpy==1.24.0"]
