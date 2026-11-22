import asyncio
from apify import Actor

_MAIN_LOOP: asyncio.AbstractEventLoop | None = None

def set_main_loop(loop: asyncio.AbstractEventLoop):
    global _MAIN_LOOP
    _MAIN_LOOP = loop

def _run_async(coro):
    if _MAIN_LOOP and _MAIN_LOOP.is_running():
        return asyncio.run_coroutine_threadsafe(coro, _MAIN_LOOP).result()
    return asyncio.run(coro)

def kv_get(store_name: str, key: str, default=None):
    async def _task():
        store = await Actor.open_key_value_store(name=store_name)
        return await store.get_value(key, default_value=default)
    return _run_async(_task())

def kv_set(store_name: str, key: str, value):
    async def _task():
        store = await Actor.open_key_value_store(name=store_name)
        await store.set_value(key, value)
    return _run_async(_task())