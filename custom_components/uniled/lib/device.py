"""UniLED Light Device."""
from __future__ import annotations
from abc import abstractmethod
from collections.abc import Callable
from typing import Any
from types import MappingProxyType

from .model import (
    UniledModel,
    UniledChannel,
)

from .const import (
    UNILED_MASTER as MASTER,
    UNILED_UPDATE_SECONDS,
    UNILED_DEVICE_RETRYS,
    CONF_UL_UPDATE_INTERVAL,
    CONF_UL_RETRY_COUNT,
    ATTR_UL_INFO_FIRMWARE,
    ATTR_UL_DEVICE_FORCE_REFRESH,
)

import weakref
import logging

_LOGGER = logging.getLogger(__name__)


class ParseNotificationError(Exception):
    """Raised on notifcation parse errors."""


##
## Master Channel
##
class UniledMaster(UniledChannel):
    """UniLED Master Channel Class"""

    _device: UniledDevice
    _name: str | None

    def __init__(self, device: UniledDevice, name: str | None = MASTER) -> None:
        self._device = device
        self._name = MASTER if name is True else name
        super().__init__(0)

    @property
    def name(self) -> str | None:
        """Returns the channel name."""
        if self.device.channels == 1:
            return ""
        if self.device.channels > 1 and self._name is not None:
            return self._name
        return super().name

    @property
    def identity(self) -> str | None:
        """Returns the channel identity."""
        if self.device.channels == 1:
            return None       
        if self.device.channels > 1 and self._name is not None:
            return self._name.replace(" ", "_").lower()
        return super().identity

    @property
    def device(self) -> UniledDevice:
        """Returns the device."""
        assert self._device is not None  # nosec
        return self._device


##
## Uniled Base Device Class
##
class UniledDevice:
    """UniLED Base Device Class"""

    def __init__(self, config: Any) -> None:
        """Init the UniLED Base Driver"""
        self._model: UniledModel | None = None
        self._config = None
        self._started = True
        self._channels: list[UniledChannel] = list()
        self._callbacks: list[Callable[[UniledChannel], None]] = list()
        self._last_notification_data: bytearray = ()
        self._last_notification_time = None
        if isinstance(config, dict) or isinstance(config, MappingProxyType):
            self._config = config

    def __del__(self):
        """Delete the device"""
        self._model = None
        self._channels.clear()
        _LOGGER.debug("%s: Deleted Device", self.name)

    def _create_channels(self) -> None:
        """Create device channels."""
        assert self._model is not None  # nosec
        total = self._model.channels or 1
        master_name = None

        if hasattr(self._model, "master_channel") and total > 1:
            master_name = self._model.master_channel
            total += 1

        count = len(self._channels)
        if count < total:
            for index in range(total):
                if not index and not count:
                    self._channels.append(UniledMaster(self, master_name))
                else:
                    self._channels.append(UniledChannel(count + index))
        elif count > total:
            for index in range(count - total):
                self._channels.pop()

    @property
    def model(self) -> UniledModel:
        """Return the device model."""
        return self._model

    @property
    def model_name(self) -> int:
        """Return the device model name."""
        assert self._model is not None  # nosec
        return self._model.model_name

    @property
    def model_number(self) -> int:
        """Return the device model number."""
        assert self._model is not None  # nosec
        return self._model.model_num

    @property
    def manufacturer(self) -> str:
        """Return the device manufacturer."""
        assert self._model is not None  # nosec
        return self._model.manufacturer

    @property
    def description(self) -> str:
        """Return the device description."""
        assert self._model is not None  # nosec
        return self._model.description

    @property
    def unique_id(self) -> str:
        """Return the unique ID of the device."""
        return self.address

    @property
    def master(self) -> UniledMaster | None:
        """Return the master channel"""
        return None if not len(self.channel_list) else self.channel_list[0]

    @property
    def channel_list(self) -> list[UniledChannel]:
        """Return the number of channels"""
        return self._channels

    @property
    def channels(self) -> int:
        """Return the number of channels"""
        return len(self.channel_list)

    def channel(self, channel_id: int) -> UniledChannel | None:
        """Return a specified channel"""
        try:
            return self.channel_list[channel_id]
        except IndexError:
            pass
        return self.master

    @property
    def last_notification_data(self) -> bytearray:
        """Last notification data"""
        return self._last_notification_data

    def save_notification_data(self, save: bytearray) -> bytearray:
        """Save some notification data"""
        self._last_notification_data = save
        return save

    @property
    def update_interval(self) -> int:
        """Device update interval"""
        if self._config:
            return self._config.get(CONF_UL_UPDATE_INTERVAL, UNILED_UPDATE_SECONDS)
        return UNILED_UPDATE_SECONDS

    @property
    def retry_count(self) -> int:
        """Device retry count"""
        if self._config:
            return self._config.get(CONF_UL_RETRY_COUNT, UNILED_DEVICE_RETRYS)
        return UNILED_DEVICE_RETRYS

    @property
    def started(self) -> bool:
        """Started."""
        return self._started
    
    async def startup(self, event = None) -> bool:
        """Startup the device."""
        self._started = True
        return True

    async def shutdown(self, event = None) -> None:
        """Shutdown the device."""
        self._started = False
        await self.stop()

    def register_callback(
        self, callback: Callable[[UniledChannel], None]
    ) -> Callable[[], None]:
        """Register a callback to be called when the state changes."""

        def unregister_callback() -> None:
            if callback in self._callbacks:
                self._callbacks.remove(callback)

        self._callbacks.append(callback)
        return unregister_callback

    def _fire_callbacks(self) -> None:
        """Fire the callbacks."""
        for callback in self._callbacks:
            callback(self)

    def get_list(self, channel_id: int, name: str) -> list:
        """Get a channel (id) attribute list"""
        if channel := self.channel(channel_id) is not None:
            return self.get_list(channel, name)
        return []

    def get_list(self, channel: UniledChannel, name: str) -> list:
        """Get a channel attribute list"""
        return self._model.fetch_attribute_list(self, channel, name)

    def get_state(self, channel_id: int, name: str, default: Any = None) -> Any:
        """Get a channel (id) attribute state"""
        if channel := self.channel(channel_id) is not None:
            return self.get_state(channel, name, default)
        return default

    def get_state(self, channel: UniledChannel, name: str, default: Any = None) -> Any:
        """Get a channel attribute state"""
        return channel.get(name, default)

    async def async_set_state(self, channel_id: int, attr: str, state: Any) -> bool:
        """Set a channel (id) attribute state"""
        if not (channel := self.channel(channel_id)):
            return False
        return await self.async_set_state(self, channel, attr, state)

    async def async_set_state(
        self, channel: UniledChannel, attr: str, state: Any
    ) -> bool:
        """Set a channel attribute state"""
        command = self._model.build_command(self, channel, attr, state)
        if command:
            success = await self.send(command) if command else False
            if success:
                channel.set(attr, state, True)
            else:
                channel.refresh()
            return success
        return False

    async def async_set_multi_state(self, channel_id: int, **kwargs) -> None:
        """Set a channel (id) multi attribute states"""
        if not (channel := self.channel(channel_id)):
            return False
        return await self.async_set_multi_state(self, channel, **kwargs)

    async def async_set_multi_state(self, channel: UniledChannel, **kwargs) -> bool:
        """Set a channel multi attribute states"""
        commands = self._model.build_multi_commands(self, channel, **kwargs)
        if not commands:
            return True
        success = await self.send(commands)
        channel.refresh()
        return success

    @property
    @abstractmethod
    def transport(self) -> str:
        """Return the device transport."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the name of the device."""

    @property
    @abstractmethod
    def address(self) -> str:
        """Return the address of the device."""

    @property
    @abstractmethod
    def available(self) -> bool:
        """Return if the device is available."""
        return False

    @abstractmethod
    async def update(self, retry: int | None = None) -> bool:
        """Update the device."""
        return False

    @abstractmethod
    async def stop(self) -> None:
        """Stop the device"""

    @abstractmethod
    async def send(
        self, commands: list[bytes] | bytes, retry: int | None = None
    ) -> bool:
        """Send command(s) to a device."""
        return False
