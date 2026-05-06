"""
Storage Abstraction Layer.

Defines a common StorageProvider interface with a LocalStorageProvider implementation.
This allows us to seamlessly swap out local disk storage for AWS S3 in the future
without changing any business logic.
"""

import os
import shutil
from abc import ABC, abstractmethod
from typing import BinaryIO

from fastapi import UploadFile

from app.config import get_settings

settings = get_settings()


class StorageProvider(ABC):
    """Abstract base class for all storage operations."""

    @abstractmethod
    async def save_file(self, file: UploadFile, destination_path: str) -> str:
        """
        Save an uploaded file to storage.
        
        Args:
            file: The FastAPI UploadFile object
            destination_path: The desired relative path/filename in storage
            
        Returns:
            The full URL or absolute path to access the file
        """
        pass

    @abstractmethod
    async def delete_file(self, file_path: str) -> bool:
        """Delete a file from storage."""
        pass
        
    @abstractmethod
    async def get_file_content(self, file_path: str) -> bytes:
        """Read the raw bytes of a file from storage."""
        pass


class LocalStorageProvider(StorageProvider):
    """Local filesystem implementation of the storage provider."""

    def __init__(self, base_dir: str):
        self.base_dir = base_dir
        # Ensure base directory exists
        os.makedirs(self.base_dir, exist_ok=True)

    async def save_file(self, file: UploadFile, destination_path: str) -> str:
        """Save file to local disk."""
        full_path = os.path.join(self.base_dir, destination_path)
        
        # Ensure subdirectory exists if destination_path contains folders
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        
        # Write file chunks asynchronously to avoid blocking the event loop
        # (Though file.read() is awaited, shutil is synchronous but fast for local)
        with open(full_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        return full_path

    async def delete_file(self, file_path: str) -> bool:
        """Delete file from local disk."""
        if os.path.exists(file_path):
            os.remove(file_path)
            return True
        return False
        
    async def get_file_content(self, file_path: str) -> bytes:
        """Read file from local disk."""
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")
        with open(file_path, "rb") as f:
            return f.read()


class S3StorageProvider(StorageProvider):
    """AWS S3 implementation placeholder."""
    
    def __init__(self):
        # In a real app, initialize boto3 client here
        pass

    async def save_file(self, file: UploadFile, destination_path: str) -> str:
        raise NotImplementedError("S3 storage not yet implemented")

    async def delete_file(self, file_path: str) -> bool:
        raise NotImplementedError("S3 storage not yet implemented")
        
    async def get_file_content(self, file_path: str) -> bytes:
        raise NotImplementedError("S3 storage not yet implemented")


def get_storage_provider() -> StorageProvider:
    """Factory function to get the configured storage provider."""
    if settings.STORAGE_PROVIDER.lower() == "s3":
        return S3StorageProvider()
    
    # Default to local
    return LocalStorageProvider(base_dir=settings.STORAGE_LOCAL_PATH)
