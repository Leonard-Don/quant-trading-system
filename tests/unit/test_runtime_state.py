from backend.app.services.runtime_state import get_data_manager, reset_runtime_state


def test_get_data_manager_returns_cached_instance():
    reset_runtime_state()

    first = get_data_manager()
    second = get_data_manager()

    assert first is second

    reset_runtime_state()
