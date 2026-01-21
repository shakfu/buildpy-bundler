import pytest
from pathlib import Path
from buildpy import Project

@pytest.fixture
def project():
    """Create a Project instance for testing"""
    return Project()

def test_project_init(project):
    """Test Project initialization and path attributes"""
    assert isinstance(project.root, Path)
    assert project.build == project.root / "build"
    assert project.downloads == project.build / "downloads"
    assert project.src == project.build / "src"
    assert project.install == project.build / "install"
    assert project.bin == project.build / "bin"
    assert project.lib == project.build / "lib"
    assert project.lib_static == project.build / "lib" / "static"

def test_project_setup(project, tmp_path):
    """Test Project.setup() creates required directories"""
    # Change working directory to temp path for testing
    project.root = tmp_path
    project.build = tmp_path / "build"
    project.downloads = project.build / "downloads"
    project.install = project.build / "install"
    project.src = project.build / "src"

    # Run setup
    project.setup()

    # Verify directories were created
    assert project.build.exists()
    assert project.downloads.exists()
    assert project.install.exists()
    assert project.src.exists()

def test_project_reset(project, tmp_path):
    """Test Project.reset() removes specified directories"""
    # Change working directory to temp path for testing
    project.root = tmp_path
    project.build = tmp_path / "build"
    project.src = project.build / "src"
    project.install = project.build / "install"

    # Create test directories and files
    project.build.mkdir()
    project.src.mkdir