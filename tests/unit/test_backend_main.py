import asyncio

from backend.main import cancel_background_tasks


def test_cancel_background_tasks_cancels_pending_tasks():
    async def _runner():
        async def _sleep_forever():
            await asyncio.sleep(60)

        task = asyncio.create_task(_sleep_forever(), name="test-sleeper")
        await cancel_background_tasks([task])
        assert task.cancelled()

    asyncio.run(_runner())
