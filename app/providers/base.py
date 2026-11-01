"""
Base Retrieval Provider Interface for WebinarAI.
Defines common contracts for remote and local media source ingestion.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional

class BaseRetrievalProvider(ABC):
    """
    Abstract interface for all webinar retrieval providers:
    Direct Links, YouTube, Google Drive, Local Files, and Local Folders.
    """

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Machine identifier for provider (e.g. 'direct', 'youtube', 'gdrive', 'local_file')."""
        pass

    @abstractmethod
    def identify(self, source_reference: str) -> bool:
        """Determines if this provider can handle the given URL or source reference."""
        pass

    @abstractmethod
    def check_accessibility(self, source_reference: str, options: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Non-destructively verifies reachability, authentication requirements,
        media compatibility, and size limits without executing a full download.
        """
        pass

    @abstractmethod
    def retrieve_media(
        self,
        source_reference: str,
        destination_dir: str,
        max_size_bytes: int,
        options: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Downloads or stages authorized media into destination_dir and performs
        binary integrity and container signature validation.
        """
        pass

