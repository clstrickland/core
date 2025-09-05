"""Media player platform for Songpal."""

from copy import deepcopy
import logging

from songpal import Device as SongpalDevice, SongpalException
from songpal.containers import Input
import voluptuous as vol

from homeassistant.components.media_player import (
    MediaPlayerDeviceClass,
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
    # MediaPlayerState,
)
from homeassistant.config_entries import ConfigEntry

# from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv, entity_platform
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, ERROR_REQUEST_RETRY, SET_SOUND_SETTING
from .coordinator import SongpalDataUpdateCoordinator
from .data import ZoneInfo

_LOGGER = logging.getLogger(__name__)

PARAM_NAME = "name"
PARAM_VALUE = "value"


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the Songpal media player platform."""
    data = hass.data[DOMAIN][config_entry.entry_id]
    coordinator: SongpalDataUpdateCoordinator = data["coordinator"]
    device = data["device"]

    entities = [
        SongpalZoneEntity(coordinator, device, zone_uri)
        for zone_uri in coordinator.data.zones
    ]
    async_add_entities(entities)

    # INTEGRATED: Register the custom service from the original file
    platform = entity_platform.async_get_current_platform()
    platform.async_register_entity_service(
        SET_SOUND_SETTING,
        {vol.Required(PARAM_NAME): cv.string, vol.Required(PARAM_VALUE): cv.string},
        "async_set_sound_setting",
    )


class SongpalZoneEntity(
    CoordinatorEntity[SongpalDataUpdateCoordinator], MediaPlayerEntity
):
    """Represents a single zone of a Songpal device."""

    _attr_device_class = MediaPlayerDeviceClass.RECEIVER
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: SongpalDataUpdateCoordinator,
        device,
        zone_uri: str,
    ) -> None:
        """Initialize the zone entity."""
        _LOGGER.info("Initializing SongpalZoneEntity for zone: %s", zone_uri)
        super().__init__(coordinator)
        self._device: SongpalDevice = device
        self._zone_uri = zone_uri
        self._attr_name = self._zone_data.title
        self._attr_unique_id = f"{self.coordinator.data.model}-{self._zone_data.id}"

        self._attr_supported_features = (
            MediaPlayerEntityFeature.TURN_ON
            | MediaPlayerEntityFeature.TURN_OFF
            | MediaPlayerEntityFeature.SELECT_SOURCE
            | MediaPlayerEntityFeature.SELECT_SOUND_MODE
        )
        if self._zone_data.volume_info:
            self._attr_supported_features |= (
                MediaPlayerEntityFeature.VOLUME_SET
                | MediaPlayerEntityFeature.VOLUME_MUTE
                | MediaPlayerEntityFeature.VOLUME_STEP
            )

    @property
    def _zone_data(self) -> ZoneInfo:
        """Helper to get the data for this specific zone."""
        return self.coordinator.data.zones[self._zone_uri]

    @property
    def name(self) -> str:
        """Return the name of the zone."""
        return self._zone_data.title

    @property
    def unique_id(self) -> str:
        """Return a unique ID for the zone."""
        return f"{self.coordinator.data.model}-{self._zone_data.id}"

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device info for the zone to create a unique device."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.unique_id)},
            name=self.name,
            manufacturer="Sony",
            model=f"Zone ({self.coordinator.data.model})",
            via_device=(DOMAIN, self.coordinator.data.model),
        )

    @property
    def state(self) -> MediaPlayerState | None:
        """Return the state of the zone."""
        try:
            return (
                MediaPlayerState.ON if self._zone_data.active else MediaPlayerState.OFF
            )
        except Exception:
            _LOGGER.exception("Error getting state for zone %s", self._zone_uri)
            return None

    @property
    def is_volume_muted(self) -> bool:
        """Boolean if volume is currently muted."""
        try:
            if vol_info := self._zone_data.volume_info:
                return vol_info.mute == "on"
        except Exception:
            _LOGGER.exception(
                "Error getting is_volume_muted for zone %s", self._zone_uri
            )
            return False
        else:
            return False

    @property
    def volume_level(self) -> float | None:
        """Volume level of the media player (0..1)."""
        try:
            if vol_info := self._zone_data.volume_info:
                return vol_info.volume / vol_info.max if vol_info.max else 0
        except Exception:
            _LOGGER.exception("Error getting volume_level for zone %s", self._zone_uri)
            return None
        else:
            return None

    @property
    def source(self) -> str | None:
        """Name of the current input source."""
        try:
            if not self._zone_data.source:
                return None
            for source in self._zone_data.inputs:
                if source.uri == self._zone_data.source:
                    return source.title

        except Exception:
            _LOGGER.exception("Error getting source for zone %s", self._zone_uri)
            return None
        else:
            return None

    @property
    def source_list(self) -> list[str]:
        """List of available input sources."""
        try:
            return [source.title for source in self._zone_data.inputs]
        except Exception:
            _LOGGER.exception("Error getting source_list for zone %s", self._zone_uri)
            return []

    @property
    def sound_mode(self) -> str | None:
        """Name of the current sound mode."""
        try:
            active_mode_val = self.coordinator.data.active_sound_mode
            if active_mode_val and (
                mode := self.coordinator.data.sound_modes.get(active_mode_val)
            ):
                return mode.title

        except Exception:
            _LOGGER.exception("Error getting sound_mode for zone %s", self._zone_uri)
            return None
        else:
            return None

    @property
    def sound_mode_list(self) -> list[str]:
        """List of available sound modes."""
        try:
            return [mode.title for mode in self.coordinator.data.sound_modes.values()]
        except Exception:
            _LOGGER.exception(
                "Error getting sound_mode_list for zone %s", self._zone_uri
            )
            return []

    # --- State and Info Properties (reading from coordinator) ---
    # ... (These properties remain the same as the previous version) ...
    # (state, is_volume_muted, volume_level, source, source_list, etc.)

    # --- Action Methods (Integrated from original file) ---
    async def async_turn_on(self) -> None:
        """Turn the zone on."""
        try:
            # Only perform optimistic update on success
            zones = await self._device.get_zones()
            zone = next(x for x in zones if x.uri == self._zone_uri)
            if await zone.activate(True):
                data = deepcopy(self.coordinator.data)
                data.zones[self._zone_uri].active = True
                self.coordinator.async_set_updated_data(data)
        except SongpalException as ex:
            if ex.code == ERROR_REQUEST_RETRY:
                _LOGGER.debug("Swallowing %s, device may already be on", ex)
                # Still do an optimistic update in case state was out of sync
                data = deepcopy(self.coordinator.data)
                data.zones[self._zone_uri].active = True
                self.coordinator.async_set_updated_data(data)
                return
            raise

    async def async_turn_off(self) -> None:
        """Turn the zone off."""
        try:
            # Only perform optimistic update on success
            zones = await self._device.get_zones()
            zone = next(x for x in zones if x.uri == self._zone_uri)
            if await zone.activate(False):
                data = deepcopy(self.coordinator.data)
                data.zones[self._zone_uri].active = False
                self.coordinator.async_set_updated_data(data)
        except SongpalException as ex:
            if ex.code == ERROR_REQUEST_RETRY:
                _LOGGER.debug("Swallowing %s, device may already be off", ex)
                data = deepcopy(self.coordinator.data)
                data.zones[self._zone_uri].active = False
                self.coordinator.async_set_updated_data(data)
                return
            raise

    async def async_mute_volume(self, mute: bool) -> None:
        """Mute the volume."""
        volume_control = next(
            (
                v
                for v in await self._device.get_volume_information()
                if v.output == self._zone_uri
            ),
            None,
        )
        # Only perform optimistic update on success
        if volume_control and await volume_control.set_mute(mute):
            data = deepcopy(self.coordinator.data)
            if volume_info := data.zones[self._zone_uri].volume_info:
                volume_info.mute = "on" if mute else "off"
            self.coordinator.async_set_updated_data(data)

    async def async_set_volume_level(self, volume: float) -> None:
        """Set volume level, range 0..1."""
        if not self._zone_data.volume_info:
            return
        volume_control = next(
            (
                v
                for v in await self._device.get_volume_information()
                if v.output == self._zone_uri
            ),
            None,
        )
        if volume_control:
            target_vol = int(volume * self._zone_data.volume_info.max)
            # Only perform optimistic update on success
            if await volume_control.set_volume(target_vol):
                data = deepcopy(self.coordinator.data)
                if volume_info := data.zones[self._zone_uri].volume_info:
                    volume_info.volume = target_vol
                self.coordinator.async_set_updated_data(data)

    async def async_volume_up(self) -> None:
        """Volume up the media player."""
        if vol_info := self._zone_data.volume_info:
            current_vol = vol_info.volume
            # The optimistic update is handled inside async_set_volume_level
            await self.async_set_volume_level((current_vol + 1) / vol_info.max)

    async def async_volume_down(self) -> None:
        """Volume down media player."""
        if vol_info := self._zone_data.volume_info:
            current_vol = vol_info.volume
            # The optimistic update is handled inside async_set_volume_level
            await self.async_set_volume_level((current_vol - 1) / vol_info.max)

    async def async_select_source(self, source: str) -> None:
        """Select input source."""
        sources = await self._device.get_inputs()
        target_source: Input | None = next(
            (x for x in sources if x.title == source), None
        )
        if target_source:
            # Only perform optimistic update on success
            result = await self._device.services["avContent"]["setPlayContent"](
                uri=target_source.uri, output=self._zone_uri
            )
            if result:
                data = deepcopy(self.coordinator.data)
                data.zones[self._zone_uri].source = target_source.uri
                self.coordinator.async_set_updated_data(data)

    async def async_select_sound_mode(self, sound_mode: str) -> None:
        """Select sound mode."""
        target_value = next(
            (
                value
                for value, mode in self.coordinator.data.sound_modes.items()
                if mode.title == sound_mode
            ),
            None,
        )
        if target_value:
            # Only perform optimistic update on success
            if await self._device.set_sound_settings("soundField", target_value):
                data = deepcopy(self.coordinator.data)
                data.active_sound_mode = target_value
                self.coordinator.async_set_updated_data(data)
        else:
            _LOGGER.error("Unable to find sound mode: %s", sound_mode)

    async def async_set_sound_setting(self, name: str, value: str) -> None:
        """Change a setting on the device (custom service)."""
        # Only perform optimistic update on success
        if await self._device.set_sound_settings(name, value):
            if name == "soundField":
                data = deepcopy(self.coordinator.data)
                data.active_sound_mode = value
                self.coordinator.async_set_updated_data(data)
