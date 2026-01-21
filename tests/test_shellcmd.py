import os
import pytest
import subprocess
from pathlib import Path
from unittest.mock import Mock, patch, call
from buildpy import ShellCmd, CommandError, BuildError, ExtractionError, logging

@pytest.fixture
def shell():
    shell = ShellCmd()
    shell.log = Mock(spec=logging.Logger)
    return shell

def test_cmd_success(shell):
    with patch('subprocess.check_call') as mock_call:
        shell.cmd('echo test')
        # Commands without shell features are split into list
        mock_call.assert_called_once_with(['echo', 'test'], cwd='.')
        shell.log.info.assert_called_once_with('echo test')

def test_cmd_failure(shell):
    with patch('subprocess.check_call') as mock_call:
        mock_call.side_effect = subprocess.CalledProcessError(1, 'failed cmd')
        with pytest.raises(CommandError):
            shell.cmd('failing command')
        shell.log.critical.assert_called_once()

def test_download(shell):
    test_url = "http://test.com/file.tar.gz"
    with patch('buildpy.urlretrieve') as mock_retrieve:
        mock_retrieve.return_value = ('file.tar.gz', None)
        result = shell.download(test_url)
        assert isinstance(result, Path)
        assert str(result) == 'file.tar.gz'

def test_download_with_folder(shell):
    test_url = "http://test.com/file.tar.gz"
    with patch('buildpy.urlretrieve') as mock_retrieve:
        mock_retrieve.return_value = ('downloads/file.tar.gz', None)
        result = shell.download(test_url, tofolder='downloads')
        assert isinstance(result, Path)
        assert str(result) == 'downloads/file.tar.gz'

def test_extract_tar(shell):
    with patch('tarfile.is_tarfile') as mock_is_tar:
        with patch('tarfile.open') as mock_open:
            with patch('sys.version_info') as mock_version:
                mock_is_tar.return_value = True
                mock_version.minor = 13  # >= 12, use filter
                mock_tar = Mock()
                mock_open.return_value.__enter__.return_value = mock_tar

                shell.extract('test.tar.gz', 'extract_dir')

                mock_tar.extractall.assert_called_once_with('extract_dir', filter='data')

def test_extract_invalid(shell):
    with patch('tarfile.is_tarfile') as mock_is_tar:
        with patch('zipfile.is_zipfile') as mock_is_zip:
            mock_is_tar.return_value = False
            mock_is_zip.return_value = False
            with pytest.raises(ExtractionError):
                shell.extract('test.invalid', 'extract_dir')

def test_fail(shell):
    with pytest.raises(BuildError):
        shell.fail("Error message")
    shell.log.critical.assert_called_once_with("Error message")

def test_git_clone_basic(shell):
    with patch.object(shell, 'cmd') as mock_cmd:
        shell.git_clone("https://github.com/test/repo.git")
        mock_cmd.assert_called_once_with(
            ['git', 'clone', '--depth', '1', 'https://github.com/test/repo.git'],
            cwd="."
        )

def test_git_clone_full(shell):
    with patch.object(shell, 'cmd') as mock_cmd:
        shell.git_clone(
            "https://github.com/test/repo.git",
            branch="main",
            directory="test_dir",
            recurse=True
        )
        expected_cmd = [
            'git', 'clone', '--depth', '1', '--branch', 'main',
            '--recurse-submodules', '--shallow-submodules',
            'https://github.com/test/repo.git', 'test_dir'
        ]
        mock_cmd.assert_called_once_with(expected_cmd, cwd=".")

# Add more test files for other functionality...

