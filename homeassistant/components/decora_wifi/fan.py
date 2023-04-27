"""Interfaces with the myLeviton API for Decora Smart WiFi products."""
from __future__ import annotations

from typing import Any

from homeassistant.components.fan import FanEntity, FanEntityFeature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

from .const import DOMAIN, LOGGER


def setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    """Set up the Decora WiFi platform."""

    add_entities(
        DecoraWifiFan(switch)
        for switch in hass.data[DOMAIN]["Switches"]
        if switch.customType == "ceiling-fan"
    )


# Since Leviton only makes one wifi fan switch, and since the api is undocumented, we can hardcode some values, like the speed count.
class DecoraWifiFan(FanEntity):
    """Representation of a Decora WiFi switch."""

    def __init__(self, switch) -> None:
        """Initialize the switch."""
        self._switch = switch
        self._attr_unique_id = switch.serial
        self._attr_speed_count = 4
        self._attr_supported_features = FanEntityFeature.SET_SPEED

    @property
    def percentage(self) -> int | None:
        """Return the current speed as a percentage."""
        return int(
            self._switch.brightness
        )  # Leviton calls the fan speed brightness in their api.

    @property
    def name(self) -> str | None:
        """Return the display name of this switch."""
        return self._switch.name

    @property
    def unique_id(self) -> str | None:
        """Return the ID of this light."""
        return self._switch.serial

    @property
    def is_on(self) -> bool | None:
        """Return true if switch is on."""
        return self._switch.power == "ON"

    def turn_on(
        self,
        percentage: int | None = None,
        preset_mode: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Instruct the switch to turn on & adjust brightness."""
        attribs: dict[str, Any] = {"power": "ON"}

        if percentage is not None:
            min_level = self._switch.data.get("minLevel", 0)
            # max_level = self._switch.data.get("maxLevel", 100)
            brightness = int(percentage)
            brightness = max(brightness, min_level)
            attribs["brightness"] = brightness

        try:
            self._switch.update_attributes(attribs)
            return
        except ValueError:
            LOGGER.error("Failed to turn on myLeviton switch")
            return

    def turn_off(self, **kwargs: Any) -> None:
        """Instruct the switch to turn off."""
        attribs = {"power": "OFF"}
        try:
            self._switch.update_attributes(attribs)
        except ValueError:
            LOGGER.error("Failed to turn off myLeviton switch")

    def update(self) -> None:
        """Fetch new state data for this switch."""
        try:
            self._switch.refresh()
        except ValueError:
            LOGGER.error("Failed to update myLeviton switch data")

    def set_percentage(self, percentage: int) -> None:
        """Set the speed of the fan, as a percentage."""
        attribs = {"brightness": percentage}
        try:
            self._switch.update_attributes(attribs)
        except ValueError:
            LOGGER.error("Failed to turn off myLeviton switch")
