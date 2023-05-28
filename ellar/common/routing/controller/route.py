import typing as t

from starlette.concurrency import run_in_threadpool

from ellar.common.interfaces import IExecutionContext
from ellar.common.routing.route import RouteOperation

from .base import ControllerRouteOperationBase


class ControllerRouteOperation(ControllerRouteOperationBase, RouteOperation):
    methods: t.Set[str]

    async def run(self, context: IExecutionContext, **kwargs: t.Any) -> t.Any:
        controller_instance = self._get_controller_instance(ctx=context)
        if self._is_coroutine:
            return await self.endpoint(controller_instance, **kwargs)
        else:
            return await run_in_threadpool(self.endpoint, controller_instance, **kwargs)
