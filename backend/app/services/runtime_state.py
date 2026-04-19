"""
Shared backend runtime singletons.

Keep expensive service objects in one place so API modules do not each create
their own copy during import.
"""

from src.data.data_manager import (
    DataManager,
    get_shared_data_manager,
    reset_shared_data_manager,
)


def get_data_manager() -> DataManager:
    """Return the process-wide DataManager instance."""
    return get_shared_data_manager()


def reset_runtime_state() -> None:
    """Test helper for clearing cached runtime singletons."""
    reset_shared_data_manager()
