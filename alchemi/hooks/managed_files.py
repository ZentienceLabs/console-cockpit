"""Managed files hook - handles file management across providers."""
from typing import Optional


class AlchemiManagedFilesHandler:
    """Handles file management operations across multiple LLM providers."""

    async def handle_file_upload(self, file_data: dict, account_id: Optional[str] = None):
        pass

    async def handle_file_delete(self, file_id: str, account_id: Optional[str] = None):
        pass
