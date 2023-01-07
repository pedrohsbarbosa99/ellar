from starlette.exceptions import HTTPException
from starlette.responses import PlainTextResponse

from ellar.common import Controller, Module, exception_handler, get
from ellar.constants import ASGI_CONTEXT_VAR
from ellar.core import TestClientFactory
from ellar.core.context import (
    ExecutionContext,
    HostContext,
    IExecutionContext,
    IExecutionContextFactory,
    IHostContext,
    IHostContextFactory,
)
from ellar.core.exceptions import IExceptionMiddlewareService
from ellar.core.exceptions.service import ExceptionMiddlewareService
from ellar.di import ProviderConfig, injectable
from ellar.di.exceptions import ServiceUnavailable
from ellar.services import Reflector


@Controller
class ExampleController:
    @get()
    def index(self):
        return self.context.__class__.__name__

    @get("/exception")
    def exception(self):
        raise HTTPException(status_code=400)


class NewExecutionContext(ExecutionContext):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.instantiated = True
        self.__class__.worked = True


@injectable()
class NewExecutionHostFactory(IExecutionContextFactory):
    def __init__(self, reflector: Reflector):
        self.reflector = reflector

    def create_context(self, operation) -> IExecutionContext:
        scoped_request_args = ASGI_CONTEXT_VAR.get()

        if not scoped_request_args:
            raise ServiceUnavailable()

        scope, receive, send = scoped_request_args.get_args()
        i_execution_context = NewExecutionContext(
            scope=scope,
            receive=receive,
            send=send,
            operation_handler=operation.endpoint,
            reflector=self.reflector,
        )
        i_execution_context.get_service_provider().update_scoped_context(
            IExecutionContext, i_execution_context
        )

        return i_execution_context


@injectable()
class NewHostContextFactory(IHostContextFactory):
    def create_context(self) -> IHostContext:
        scoped_request_args = ASGI_CONTEXT_VAR.get()

        if not scoped_request_args:
            raise ServiceUnavailable()

        scope, receive, send = scoped_request_args.get_args()
        host_context = NewHostContext(scope=scope, receive=receive, send=send)
        host_context.get_service_provider().update_scoped_context(
            IHostContext, host_context
        )
        return host_context


class NewHostContext(HostContext):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.instantiated = True
        self.__class__.worked = True


@injectable()
class NewExceptionMiddlewareService(ExceptionMiddlewareService):
    def lookup_status_code_exception_handler(self, status_code: int):
        self.__class__.worked = True
        return self._status_handlers.get(status_code)


def test_can_replace_host_context():
    tm = TestClientFactory.create_test_module(controllers=[ExampleController])
    tm.app.injector.container.register(IHostContextFactory, NewHostContextFactory)

    assert hasattr(NewHostContext, "worked") is False
    client = tm.get_client()
    res = client.get("/example/")
    assert res.status_code == 200
    assert res.text == '"ExecutionContext"'

    assert hasattr(NewHostContext, "worked") is True
    assert NewHostContext.worked is True


def test_can_replace_exception_service():
    @Module(
        controllers=[ExampleController],
        providers=[
            ProviderConfig(
                IExceptionMiddlewareService, use_class=NewExceptionMiddlewareService
            )
        ],
    )
    class ExampleModule:
        @exception_handler(400)
        def exception_400(self, context: IHostContext, exc: Exception):
            return PlainTextResponse(
                "Exception 400 handled by ExampleModule.exception_400"
            )

    tm = TestClientFactory.create_test_module_from_module(ExampleModule)

    assert hasattr(NewExceptionMiddlewareService, "worked") is False
    client = tm.get_client()
    res = client.get("/example/exception")
    assert res.status_code == 200
    assert res.text == "Exception 400 handled by ExampleModule.exception_400"

    assert hasattr(NewExceptionMiddlewareService, "worked") is True
    assert NewExceptionMiddlewareService.worked is True


def test_can_replace_execution_context():
    tm = TestClientFactory.create_test_module(controllers=[ExampleController])
    tm.app.injector.container.register(
        IExecutionContextFactory, NewExecutionHostFactory
    )

    assert hasattr(NewExecutionContext, "worked") is False
    client = tm.get_client()
    res = client.get("/example/")
    assert res.status_code == 200
    assert res.text == '"NewExecutionContext"'

    assert hasattr(NewExecutionContext, "worked") is True
    assert NewExecutionContext.worked is True
