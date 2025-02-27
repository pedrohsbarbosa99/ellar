import typing as t
from abc import ABC, abstractmethod

from ellar.common.constants import SERIALIZER_FILTER_KEY
from ellar.common.exceptions import RequestValidationError
from ellar.common.helper.modelfield import create_model_field
from ellar.common.interfaces import IExecutionContext, IResponseModel
from ellar.common.logger import request_logger
from ellar.common.serializer import SerializerFilter, serialize_object
from ellar.reflect import reflect
from pydantic import BaseModel
from pydantic.fields import ModelField
from starlette.responses import Response

from .type_converter import ResponseTypeDefinitionConverter


def serialize_if_pydantic_object(obj: t.Any) -> t.Any:
    if isinstance(obj, BaseModel):
        return obj.dict(by_alias=True)
    elif isinstance(obj, list):
        return [serialize_if_pydantic_object(item) for item in obj]
    elif isinstance(obj, dict):
        return {k: serialize_if_pydantic_object(v) for k, v in obj.items()}
    return obj


class ResponseModelField(ModelField):
    """
    A representation of response schema defined in route function

        @get('/', response={200: ASchema, 404: ErrorSchema})
        def example():
            pass

    During module building, `ASchema` and `ErrorSchema` will be converted to ResponseModelField
    types for the of validation and OPENAPI documentation
    """

    def validate_object(self, obj: t.Any) -> t.Any:
        request_logger.debug(
            f"Validating Response Object - '{self.__class__.__name__}'"
        )
        values, error = self.validate(obj, {}, loc=(self.alias,))
        if error:
            _errors = list(error) if isinstance(error, list) else [error]
            raise RequestValidationError(errors=_errors)
        return values

    def serialize(
        self, obj: t.Any, serializer_filter: t.Optional[SerializerFilter] = None
    ) -> t.Union[t.List[t.Dict], t.Dict, t.Any]:
        request_logger.debug(f"Serializing Response Data - '{self.__class__.__name__}'")
        try:
            values = self.validate_object(obj=obj)
        except RequestValidationError:
            try:
                new_obj = serialize_if_pydantic_object(obj)
                values = self.validate_object(obj=new_obj)
            except RequestValidationError as req_val_ex2:
                raise req_val_ex2
        return serialize_object(values, serializer_filter=serializer_filter)


class BaseResponseModel(IResponseModel, ABC):
    """
    A base model representation of endpoint response. It provides essential information about a response type, just as
    it is defined on the endpoint, the status code and schema plus description for OPENAPI documentation.

    For example:

        @get('/', response={200: ASchema, 404: ErrorSchema})
        def example():
            pass

    From the Above example, two response models will be generated.
    - response model for 200 status and ASchema and
    - response model for 400 status and ErrorSchema
    """

    __slots__ = (
        "_response_type",
        "_media_type",
        "meta",
        "_model_field",
    )

    response_type: t.Type[Response] = Response
    model_field_or_schema: t.Union[ResponseModelField, t.Any] = None
    default_description: str = "Successful Response"

    def __init__(
        self,
        description: t.Optional[str] = None,
        model_field_or_schema: t.Union[ResponseModelField, t.Any] = None,
        **kwargs: t.Any,
    ) -> None:
        self._response_type: t.Type[Response] = t.cast(
            t.Type[Response], kwargs.get("response_type") or self.response_type
        )
        self._media_type = str(
            kwargs.get("media_type") or self._response_type.media_type
        )
        self.default_description = description or self.default_description
        self.meta = kwargs
        self._model_field = self._get_model_field_from_schema(model_field_or_schema)

    @property
    def media_type(self) -> str:
        return self._media_type

    @property
    def description(self) -> str:
        return self.default_description

    def _get_model_field_from_schema(
        self, model_field_or_schema: t.Optional[t.Union[ResponseModelField, t.Any]]
    ) -> t.Optional[ResponseModelField]:
        _model_field_or_schema: t.Optional[ResponseModelField] = (
            model_field_or_schema or self.model_field_or_schema
        )
        if not isinstance(_model_field_or_schema, ResponseModelField):
            try:
                # convert to serializable type of base `Class BaseSerializer` is possible
                new_response_schema = ResponseTypeDefinitionConverter(
                    _model_field_or_schema
                ).re_group_outer_type()
            except Exception:
                new_response_schema = _model_field_or_schema

            _model_field_or_schema = t.cast(
                ResponseModelField,
                create_model_field(
                    name="response_model",  # TODO: find a good name for the field
                    type_=new_response_schema,
                    model_field_class=ResponseModelField,
                ),
            )
        return _model_field_or_schema

    def get_model_field(self) -> t.Optional[t.Union[ResponseModelField, t.Any]]:
        return self._model_field

    @abstractmethod
    def serialize(
        self,
        response_obj: t.Any,
        serializer_filter: t.Optional[SerializerFilter] = None,
    ) -> t.Union[t.List[t.Dict], t.Dict, t.Any]:
        pass

    def create_response(
        self, context: IExecutionContext, response_obj: t.Any, status_code: int
    ) -> Response:
        """Please override this function to create a custom response"""
        request_logger.debug(
            f"Creating Response from returned Handler value - '{self.__class__.__name__}'"
        )
        response_args, headers = self.get_context_response(
            context=context, status_code=status_code
        )
        serializer_filter: t.Optional[SerializerFilter] = reflect.get_metadata(
            SERIALIZER_FILTER_KEY, context.get_handler()
        )

        response = self._response_type(
            **response_args,
            content=self.serialize(
                response_obj, serializer_filter=serializer_filter or SerializerFilter()
            ),
            headers=headers,
        )
        return response

    @classmethod
    def get_context_response(
        cls, context: IExecutionContext, **kwargs: t.Any
    ) -> t.Tuple[t.Dict, t.Dict]:
        response_args = dict(kwargs)
        http_connection = context.switch_to_http_connection()
        if http_connection.has_response:
            endpoint_response = http_connection.get_response()
            response_args = {"background": endpoint_response.background}
            if endpoint_response.status_code > 0:
                response_args["status_code"] = endpoint_response.status_code
            return response_args, dict(endpoint_response.headers)
        return response_args, {}


class ResponseModel(BaseResponseModel):
    """
    Handles endpoint models with Response Type as schema

        from starlette.responses import PlainTextResponse

        @get('/', response={200: PlainTextResponse})
        def example():
            pass
    """

    def serialize(
        self,
        response_obj: t.Any,
        serializer_filter: t.Optional[SerializerFilter] = None,
    ) -> t.Union[t.List[t.Dict], t.Dict, t.Any]:
        return response_obj


class ResponseResolver(t.NamedTuple):
    status_code: int
    response_model: IResponseModel
    response_object: t.Any
