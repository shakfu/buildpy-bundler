import pytest
from pathlib import Path
from unittest.mock import Mock, patch
from buildpy import Builder, Project, ExtractionError

class TestBuilder:
    @pytest.fixture
    def builder(self):
        """Create a basic builder instance for testing"""
        class ConcreteBuilder(Builder):
            name = "test"
            version = "1.0.0"
            download_archive_template = "test-{ver}.tar.gz"
            download_url_template = "https://example.com/test-{ver}.tar.gz"
            depends_on = []
            lib_products = []

        return ConcreteBuilder()

    @pytest.fixture
    def mock_project(self, tmp_path):
        """Create a Project instance using temporary directory"""
        project = Project()
        project.cwd = tmp_path
        project.build = tmp_path / "build"
        project.downloads = project.build / "downloads"
        project.src = project.build / "src"
        project.install = project.build / "install"
        return project

    def test_builder_initialization(self, builder):
        """Test basic builder initialization"""
        assert builder.name == "test"
        assert builder.version == "1.0.0"
        assert builder.download_url == "https://example.com/test-1.0.0.tar.gz"

    def test_src_dir_property(self, builder):
        """Test src_dir property returns correct path"""
        expected = builder.project.src / "test-1.0.0"
        assert builder.src_dir == expected

    # @patch('buildpy.urlretrieve')
    # @patch('buildpy.tarfile.is_tarfile', return_value=True)
    # @patch('buildpy.tarfile.open')
    # def test_setup_downloads_and_extracts(self, mock_tarfile, mock_is_tarfile, 
    #                                     mock_urlretrieve, builder, mock_project):
    #     """Test setup downloads and extracts archive"""
    #     builder.project = mock_project
    #     builder.project.setup()
        
    #     # Mock the tarfile context manager
    #     mock_tar = Mock()
    #     mock_tarfile.return_value.__enter__.return_value = mock_tar
        
    #     # Run setup
    #     builder.setup()
        
    #     # Verify download occurred
    #     mock_urlretrieve.assert_called_once()
    #     download_url = mock_urlretrieve.call_args[0][0]
    #     assert download_url == builder.download_url
        
    #     # Verify extraction occurred
    #     mock_tarfile.assert_called_once()
    #     mock_tar.extractall.assert_called_once()

    # def test_setup_creates_directories(self, builder, mock_project):
    #     """Test setup creates required directories"""
    #     builder.project = mock_project
        
    #     # Run setup
    #     with patch('buildpy.Builder.download'), \
    #          patch('buildpy.Builder.extract'):
    #         builder.setup()
        
    #     # Verify directories were created
    #     assert builder.project.build.exists()
    #     assert builder.project.downloads.exists()
    #     assert builder.project.install.exists()
    #     assert builder.project.src.exists()

    def test_setup_skips_extract_if_src_exists(self, builder, mock_project):
        """Test setup skips extraction if source directory already exists"""
        builder.project = mock_project
        
        # Create source directory
        src_dir = builder.src_dir
        src_dir.parent.mkdir(parents=True)
        src_dir.mkdir()
        
        # Run setup
        with patch('buildpy.Builder.download') as mock_download, \
             patch('buildpy.Builder.extract') as mock_extract:
            builder.setup()
            
            # Verify download occurred but extract didn't
            mock_download.assert_called_once()
            mock_extract.assert_not_called()

    def test_setup_raises_on_extract_failure(self, builder, mock_project):
        """Test setup raises ExtractionError if extraction fails"""
        builder.project = mock_project

        with patch('buildpy.Builder.download'), \
             patch('buildpy.Builder.extract'), \
             patch.object(builder, 'lib_products_exist', return_value=False), \
             pytest.raises(ExtractionError):
            builder.setup()