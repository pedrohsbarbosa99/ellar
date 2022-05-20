import importlib
import typing as t

from starlette.config import environ

from ellar.compatible.dict import AttributeDictAccessMixin, DataMutableMapper
from ellar.constants import ELLAR_CONFIG_MODULE
from ellar.types import VT

from . import default_settings
from .app_settings_models import ConfigValidationSchema


class Config(DataMutableMapper, AttributeDictAccessMixin):
    __slots__ = ("config_module", "_data")

    def __init__(
        self,
        config_module: str = environ.get(ELLAR_CONFIG_MODULE, None),
        **mapping: t.Any,
    ):
        """
        Creates a new instance of Configuration object with the given values.
        """
        super().__init__()
        self.config_module = config_module

        self._data.clear()
        for setting in dir(default_settings):
            if setting.isupper():
                self._data[setting] = getattr(default_settings, setting)

        if self.config_module:
            mod = importlib.import_module(self.config_module)
            for setting in dir(mod):
                if setting.isupper():
                    self._data[setting] = getattr(mod, setting)

        self._data.update(**mapping)

        validate_config = ConfigValidationSchema.parse_obj(self._data)
        self._data.update(validate_config.serialize())

    def set_defaults(self, **kwargs: t.Any) -> "Config":
        for k, v in kwargs.items():
            self._data.setdefault(k, v)
        return self

    def __repr__(self) -> str:
        hidden_values = {key: "..." for key in self._data.keys()}
        return f"<Configuration {repr(hidden_values)}, settings_module: {self.config_module}>"

    def __setattr__(self, key: t.Any, value: t.Any) -> None:
        if key in self.__slots__:
            super(Config, self).__setattr__(key, value)
            return

        self._data[key] = value

    @property
    def values(self) -> t.ValuesView[VT]:
        """
        Returns a copy of the dictionary of current settings.
        """
        return self._data.values()
