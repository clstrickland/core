"""The songpal component."""

import asyncio
from copy import deepcopy
import logging

# from datetime import timedelta
from songpal import (
    ConnectChange,
    ContentChange,
    Device,
    # PowerChange,
    SettingChange,
    SongpalException,
    VolumeChange,
    ZoneActivatedChange,
)
from songpal.notification import ChangeNotification
import voluptuous as vol

from homeassistant.config_entries import SOURCE_IMPORT, ConfigEntry
from homeassistant.const import CONF_NAME, EVENT_HOMEASSISTANT_STOP, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

# from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from .const import CONF_ENDPOINT, DOMAIN
from .coordinator import SongpalDataUpdateCoordinator
from .data import SongpalData

# --- CONFIG_SCHEMA and async_setup remain the same ---

SONGPAL_CONFIG_SCHEMA = vol.Schema(
    {vol.Optional(CONF_NAME): cv.string, vol.Required(CONF_ENDPOINT): cv.string}
)

CONFIG_SCHEMA = vol.Schema(
    {vol.Optional(DOMAIN): vol.All(cv.ensure_list, [SONGPAL_CONFIG_SCHEMA])},
    extra=vol.ALLOW_EXTRA,
)

PLATFORMS = [Platform.MEDIA_PLAYER]
_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up songpal environment."""
    if (conf := config.get(DOMAIN)) is None:
        return True
    for config_entry in conf:
        hass.async_create_task(
            hass.config_entries.flow.async_init(
                DOMAIN,
                context={"source": SOURCE_IMPORT},
                data=config_entry,
            ),
        )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up songpal media player from a config entry."""
    endpoint = entry.data[CONF_ENDPOINT]
    device = Device(endpoint)
    coordinator = SongpalDataUpdateCoordinator(hass, device, entry)
    _reconnect_in_progress = False

    # --- Notification Callback Handlers ---
    # These functions will be called by the songpal library on a push update.
    # They update the coordinator's data directly.

    async def _handle_volume_change(change: ChangeNotification) -> None:
        """Handle a volume change notification."""
        if not coordinator or not coordinator.data:
            return
        if not isinstance(change, VolumeChange):
            _LOGGER.warning(
                "Received wrong change type in volume change handler: %s", change
            )
            return
        _LOGGER.debug("Handling volume change: %s", change)
        data: SongpalData = deepcopy(coordinator.data)
        if (zone := data.zones.get(change.output)) and zone.volume_info:
            zone.volume_info.volume = change.volume
            zone.volume_info.mute = "on" if change.mute else "off"
            coordinator.async_set_updated_data(data)

    async def _handle_zone_activated_change(change: ChangeNotification) -> None:
        """Handle a zone activated notification."""
        if not coordinator.data:
            return
        if not isinstance(change, ZoneActivatedChange):
            _LOGGER.warning(
                "Received wrong change type in zone activated handler: %s", change
            )
            return
        _LOGGER.debug("Handling zone activated change: %s", change)
        data: SongpalData = deepcopy(coordinator.data)
        if zone := data.zones.get(change.uri):
            zone.active = change.active
            coordinator.async_set_updated_data(data)

    async def _handle_source_change(change: ChangeNotification) -> None:
        """Handle a source change notification."""
        if not coordinator.data:
            return
        if not isinstance(change, ContentChange):
            _LOGGER.warning(
                "Received wrong change type in source change handler: %s", change
            )
            return
        _LOGGER.debug("Handling source change: %s", change)
        data: SongpalData = deepcopy(coordinator.data)
        if zone := data.zones.get(change.output):
            zone.source = change.uri
            coordinator.async_set_updated_data(data)

    async def _reconnect_task():
        """Task to handle the reconnection logic in the background."""
        nonlocal _reconnect_in_progress
        _LOGGER.info("Starting reconnection attempts for %s", endpoint)

        delay = 10
        while _reconnect_in_progress:  # Loop while the flag is set
            try:
                # 1. Test the connection with a simple command.
                await device.get_supported_methods()

                # 2. On success, trigger a full data refresh and exit the loop.
                _LOGGER.info(
                    "Connection re-established to %s, refreshing data", endpoint
                )
                await coordinator.async_request_refresh()
                _reconnect_in_progress = False  # Clear the flag to stop the loop

            except SongpalException as ex:
                _LOGGER.debug(
                    "Failed to reconnect: %s, retrying in %s seconds", ex, delay
                )
                await asyncio.sleep(delay)
                delay = min(2 * delay, 300)  # Exponential backoff

    async def _handle_connect_change(change: ChangeNotification) -> None:
        """Handle a disconnect notification."""
        if not isinstance(change, ConnectChange):
            _LOGGER.warning(
                "Received wrong change type in connect change handler: %s", change
            )
            return
        nonlocal _reconnect_in_progress
        if _reconnect_in_progress:
            _LOGGER.debug("Reconnect already in progress, ignoring disconnect event")
            return

        _LOGGER.warning("Connection lost to %s: %s", endpoint, change.exception)
        _reconnect_in_progress = True
        hass.create_task(_reconnect_task())

    async def _setting_changed(change: ChangeNotification) -> None:
        """Handle a setting change notification."""
        if not coordinator.data:
            return
        if not isinstance(change, SettingChange):
            _LOGGER.warning(
                "Received wrong change type in setting change handler: %s", change
            )
            return
        _LOGGER.debug("Setting changed: %s", change)
        if change.target == "soundField":
            data: SongpalData = deepcopy(coordinator.data)
            data.active_sound_mode = change.currentValue
            _LOGGER.debug("New active sound mode: %s", change.currentValue)
            coordinator.async_set_updated_data(data)
        else:
            _LOGGER.debug("Got non-handled setting change: %s", change)

    # --- Setup the Device and Register Callbacks ---
    try:
        await device.get_supported_methods()
        # interface_info = await device.get_interface_information()
        # model_name = interface_info.modelName
        device.on_notification(VolumeChange, _handle_volume_change)
        # device.on_notification(PowerChange, _handle_power_change)
        device.on_notification(ContentChange, _handle_source_change)
        device.on_notification(SettingChange, _setting_changed)
        device.on_notification(ConnectChange, _handle_connect_change)
        device.on_notification(ZoneActivatedChange, _handle_zone_activated_change)
        # Register other handlers here
        hass.loop.create_task(device.listen_notifications())

    except SongpalException as ex:
        raise ConfigEntryNotReady(f"Unable to connect or start listening: {ex}") from ex

    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "coordinator": coordinator,
        "device": device,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    async def _async_stop_hass(event):
        """Stop the websocket."""
        await device.stop_listen_notifications()

    entry.async_on_unload(
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _async_stop_hass)
    )
    entry.async_on_unload(entry.add_update_listener(update_listener))

    return True


async def update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload songpal media player."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
