"""Create coordinator for all zones."""

from datetime import timedelta
import logging
from urllib.parse import parse_qs, urlparse

from songpal import Device, SongpalException
from songpal.containers import Setting

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN
from .data import InputInfo, SongpalData, VolumeInfo, ZoneInfo

_LOGGER = logging.getLogger(__name__)


class SongpalDataUpdateCoordinator(DataUpdateCoordinator[SongpalData]):
    """Manages fetching data from the Songpal device."""

    def __init__(self, hass, device: Device, entry: ConfigEntry) -> None:
        """Initialize the coordinator."""
        self.device = device
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=300),
            config_entry=entry,
        )

    async def _get_sound_modes(self) -> tuple[dict, str | None]:
        """Fetch current sound modes and active sound mode.

        This logic is extracted so it can be reused when sound mode state changes
        (e.g., when switching inputs, which resets the sound mode to the saved value for that input).
        """
        soundfields = await self.device.get_soundfield()

        if isinstance(soundfields, Setting):
            soundfields = [soundfields]

        sound_modes = {}
        active_sound_mode = None
        for soundfield in soundfields:
            cur = soundfield.currentValue
            for opt in soundfield.candidate:
                if not opt.isAvailable:
                    continue
                if opt.value == cur:
                    active_sound_mode = opt.value
                sound_modes[opt.value] = opt

        _LOGGER.debug("Got sound modes: %s", sound_modes)
        _LOGGER.debug("Active sound mode: %s", active_sound_mode)

        return sound_modes, active_sound_mode

    async def _async_update_data(self):
        """Fetch all data for the device (polling)."""
        try:
            # Get all necessary data from the device in one go
            zones = await self.device.get_zones()
            volume_info_list = await self.device.get_volume_information()
            playing_content_list = await self.device.get_play_info()
            inputs_list = await self.device.get_inputs()

            # Process the data into clean, lookup-friendly dictionaries
            volume_info = {
                zone.output: VolumeInfo(
                    min=zone.minVolume,
                    max=zone.maxVolume,
                    step=zone.step,
                    mute=zone.mute,
                    volume=zone.volume,
                )
                for zone in volume_info_list
            }
            zone_sources = {zone.output: zone.source for zone in playing_content_list}
            outputs_to_inputs = {}
            for input_obj in inputs_list:
                for output_uri in input_obj.outputs:
                    outputs_to_inputs.setdefault(output_uri, []).append(
                        {"uri": input_obj.uri, "title": input_obj.title}
                    )

            # Assemble the final data structure for all zones
            zone_data = {}
            for zone in zones:
                zone_data[zone.uri] = ZoneInfo(
                    title=zone.title,
                    active=zone.active,
                    source=zone_sources.get(zone.uri),
                    volume_info=volume_info.get(zone.uri),
                    inputs=[
                        InputInfo(**inp) for inp in outputs_to_inputs.get(zone.uri, [])
                    ],
                    id=parse_qs(urlparse(zone.uri).query)["zone"][
                        0
                    ],  # gets the zone number from the reported uri
                )
            interface_info = await self.device.get_interface_information()
            model_name = interface_info.modelName

            sound_modes, active_sound_mode = await self._get_sound_modes()

        except SongpalException as err:
            raise UpdateFailed(
                f"Error communicating with Songpal device: {err}"
            ) from err

        else:
            return SongpalData(
                model=model_name,
                zones=zone_data,
                sound_modes=sound_modes,
                active_sound_mode=active_sound_mode,
            )
            # return {
            #     "model": model_name,
            #     "zones": zone_data,
            #     "sound_modes": sound_modes,
            #     "active_sound_mode": active_sound_mode,
            # }
