import random
import typing as t
from abc import ABC

from ellar.helper.event_loop import get_or_create_eventloop

try:
    from redis.asyncio import Redis  # type: ignore
    from redis.asyncio.connection import ConnectionPool  # type: ignore
except ImportError as e:  # pragma: no cover
    raise RuntimeError(
        "To use `RedisCacheBackend`, you have to install 'redis' package e.g. `pip install redis`"
    ) from e
from ...interface import IBaseCacheBackendAsync
from ...make_key_decorator import make_key_decorator, make_key_decorator_and_validate
from ...model import BaseCacheBackend
from .serializer import IRedisSerializer, RedisSerializer


class _RedisCacheBackendSync(IBaseCacheBackendAsync, ABC):
    def _async_executor(self, func: t.Awaitable) -> t.Any:
        return get_or_create_eventloop().run_until_complete(func)

    def get(self, key: str, version: str = None) -> t.Any:
        return self._async_executor(self.get_async(key, version=version))

    def delete(self, key: str, version: str = None) -> bool:
        res = self._async_executor(self.delete_async(key, version=version))
        return bool(res)

    def set(
        self,
        key: str,
        value: t.Any,
        timeout: t.Union[float, int] = None,
        version: str = None,
    ) -> bool:
        res = self._async_executor(
            self.set_async(key, value, version=version, timeout=timeout)
        )
        return bool(res)

    def touch(
        self, key: str, timeout: t.Union[float, int] = None, version: str = None
    ) -> bool:
        res = self._async_executor(
            self.touch_async(key, version=version, timeout=timeout)
        )
        return bool(res)


class RedisCacheBackend(_RedisCacheBackendSync, BaseCacheBackend):
    MEMCACHE_CLIENT: t.Any = Redis
    """Redis-based cache backend.

    Redis Server Construct example::
        backend = RedisCacheBackend(servers=['redis://[[username]:[password]]@localhost:6379/0'])
        OR
        backend = RedisCacheBackend(servers=['redis://[[username]:[password]]@localhost:6379/0'])
        OR
        backend = RedisCacheBackend(servers=['rediss://[[username]:[password]]@localhost:6379/0'])
        OR
        backend = RedisCacheBackend(servers=['unix://[username@]/path/to/socket.sock?db=0[&password=password]'])

    """

    def __init__(
        self,
        servers: t.List[str],
        options: t.Dict = None,
        serializer: IRedisSerializer = None,
        **kwargs: t.Any
    ) -> None:
        super().__init__(**kwargs)

        self._pools: t.Dict[int, ConnectionPool] = {}
        self._servers = servers
        _default_options = options or {}
        self._options = {
            **_default_options,
        }
        self._serializer = serializer or RedisSerializer()

    def _get_connection_pool_index(self, write: bool) -> int:
        # Write to the first server. Read from other servers if there are more,
        # otherwise read from the first server.
        if write or len(self._servers) == 1:
            return 0
        return random.randint(1, len(self._servers) - 1)

    def _get_connection_pool(self, write: bool) -> ConnectionPool:
        index = self._get_connection_pool_index(write)
        if index not in self._pools:
            self._pools[index] = ConnectionPool.from_url(
                self._servers[index],
                **self._options,
            )
        return self._pools[index]

    def _get_client(self, *, write: bool = False) -> Redis:
        # key is used so that the method signature remains the same and custom
        # cache client can be implemented which might require the key to select
        # the server, e.g. sharding.
        pool = self._get_connection_pool(write)
        return self.MEMCACHE_CLIENT(connection_pool=pool)

    def get_backend_timeout(
        self, timeout: t.Union[float, int] = None
    ) -> t.Union[float, int]:
        if timeout is None:
            timeout = self._default_timeout
        # The key will be made persistent if None used as a timeout.
        # Non-positive values will cause the key to be deleted.
        return None if timeout is None else max(0, int(timeout))

    @make_key_decorator
    async def get_async(self, key: str, version: str = None) -> t.Any:
        client = self._get_client()
        value = await client.get(key)
        if value:
            return self._serializer.load(value)
        return None

    @make_key_decorator_and_validate
    async def set_async(
        self,
        key: str,
        value: t.Any,
        timeout: t.Union[float, int] = None,
        version: str = None,
    ) -> bool:
        client = self._get_client()
        value = self._serializer.dumps(value)
        if timeout == 0:
            await client.delete(key)

        return bool(await client.set(key, value, ex=self.get_backend_timeout(timeout)))

    @make_key_decorator
    async def delete_async(self, key: str, version: str = None) -> bool:
        client = self._get_client()
        result = await client.delete(key)
        return bool(result)

    @make_key_decorator
    async def touch_async(
        self, key: str, timeout: t.Union[float, int] = None, version: str = None
    ) -> bool:
        client = self._get_client()
        if timeout is None:
            res = await client.persist(key)
            return bool(res)
        res = await client.expire(key, self.get_backend_timeout(timeout))
        return bool(res)