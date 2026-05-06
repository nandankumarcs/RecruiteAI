"""
Tests for the StorageProvider abstraction and LocalStorageProvider implementation.
"""

import os
import shutil
from io import BytesIO

import pytest
from fastapi import UploadFile

from app.services.storage import LocalStorageProvider


@pytest.fixture
def temp_storage_dir(tmp_path):
    """Provide a temporary directory for local storage tests."""
    storage_path = tmp_path / "test_uploads"
    yield str(storage_path)
    # Cleanup after test if it still exists
    if os.path.exists(storage_path):
        shutil.rmtree(storage_path)


@pytest.fixture
def local_storage(temp_storage_dir):
    """Fixture providing a LocalStorageProvider instance."""
    return LocalStorageProvider(base_dir=temp_storage_dir)


@pytest.fixture
def mock_upload_file():
    """Create a mock FastAPI UploadFile with some text content."""
    content = b"Mock resume content for testing."
    file_obj = BytesIO(content)
    return UploadFile(filename="test_resume.pdf", file=file_obj)


@pytest.mark.asyncio
async def test_local_storage_save_file(local_storage, mock_upload_file, temp_storage_dir):
    """Test saving a file creates the file on disk."""
    dest_path = "resumes/job-123/test_resume.pdf"
    
    # Save the file
    saved_path = await local_storage.save_file(mock_upload_file, dest_path)
    
    # Verify the path returned is correct
    expected_path = os.path.join(temp_storage_dir, dest_path)
    assert saved_path == expected_path
    
    # Verify the file exists on disk
    assert os.path.exists(saved_path)
    
    # Verify file content
    with open(saved_path, "rb") as f:
        content = f.read()
    assert content == b"Mock resume content for testing."


@pytest.mark.asyncio
async def test_local_storage_get_file_content(local_storage, mock_upload_file):
    """Test retrieving file content from disk."""
    dest_path = "resumes/job-456/test2.pdf"
    saved_path = await local_storage.save_file(mock_upload_file, dest_path)
    
    # Get content via provider
    content = await local_storage.get_file_content(saved_path)
    
    assert content == b"Mock resume content for testing."


@pytest.mark.asyncio
async def test_local_storage_get_file_not_found(local_storage):
    """Test getting content for non-existent file raises FileNotFoundError."""
    with pytest.raises(FileNotFoundError):
        await local_storage.get_file_content("/fake/path/does_not_exist.txt")


@pytest.mark.asyncio
async def test_local_storage_delete_file(local_storage, mock_upload_file):
    """Test deleting a file from disk."""
    dest_path = "test_delete.pdf"
    saved_path = await local_storage.save_file(mock_upload_file, dest_path)
    
    assert os.path.exists(saved_path)
    
    # Delete the file
    result = await local_storage.delete_file(saved_path)
    
    assert result is True
    assert not os.path.exists(saved_path)


@pytest.mark.asyncio
async def test_local_storage_delete_nonexistent_file(local_storage):
    """Test deleting a file that doesn't exist returns False."""
    result = await local_storage.delete_file("/fake/path/does_not_exist.txt")
    assert result is False
