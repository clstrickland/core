"""The decora_wifi component."""
from __future__ import annotations

from decora_wifi import DecoraWiFiSession
from decora_wifi.models.residence import Residence
from decora_wifi.models.residential_account import ResidentialAccount
import voluptuous as vol

from homeassistant.components import persistent_notification

# pylint: disable=import-error
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (  # EVENT_HOMEASSISTANT_STOP,
    CONF_PASSWORD,
    CONF_USERNAME,
)
from homeassistant.core import HomeAssistant
import homeassistant.helpers.config_validation as cv

from .const import DOMAIN, LOGGER

# Validation of the user's configuration
CONFIG_SCHEMA = vol.Schema(
    {
        vol.Optional(DOMAIN): vol.Schema(
            {
                vol.Required(CONF_USERNAME): cv.string,
                vol.Required(CONF_PASSWORD): cv.string,
            }
        )
    },
    extra=vol.ALLOW_EXTRA,
)

NOTIFICATION_ID = "leviton_notification"
NOTIFICATION_TITLE = "myLeviton Decora Setup"


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up the Decora WiFi platform."""
    email = entry.data[CONF_USERNAME]
    password = entry.data[CONF_PASSWORD]
    hass.data[DOMAIN] = {"Session": DecoraWiFiSession()}

    try:
        success = hass.data[DOMAIN]["Session"].login(email, password)

        # If login failed, notify user.
        if success is None:
            msg = "Failed to log into myLeviton Services. Check credentials."
            LOGGER.error(msg)
            persistent_notification.create(
                hass, msg, title=NOTIFICATION_TITLE, notification_id=NOTIFICATION_ID
            )
            return False

        # Gather all the available devices...
        perms = hass.data[DOMAIN]["Session"].user.get_residential_permissions()
        all_switches = []
        for permission in perms:
            if permission.residentialAccountId is not None:
                acct = ResidentialAccount(
                    hass.data[DOMAIN]["Session"], permission.residentialAccountId
                )
                for residence in acct.get_residences():
                    for switch in residence.get_iot_switches():
                        all_switches.append(switch)
            elif permission.residenceId is not None:
                residence = Residence(
                    hass.data[DOMAIN]["Session"], permission.residenceId
                )
                for switch in residence.get_iot_switches():
                    # search all_switches for duplicates by matching switch.mac, only append if not found
                    if not any(x.mac == switch.mac for x in all_switches):
                        all_switches.append(switch)
        hass.data[DOMAIN]["Switches"] = all_switches
        return True

    except ValueError:
        LOGGER.error("Failed to communicate with myLeviton Service")
        return False


# def setup(hass: HomeAssistant, config: ConfigType) -> bool:
#     """Set up the Decora WiFi platform."""
#     conf = config.get(DOMAIN)
#     email = conf[CONF_USERNAME]
#     password = conf[CONF_PASSWORD]
#     hass.data[DOMAIN] = {"Session": DecoraWiFiSession()}

#     try:
#         success = hass.data[DOMAIN]["Session"].login(email, password)

#         # If login failed, notify user.
#         if success is None:
#             msg = "Failed to log into myLeviton Services. Check credentials."
#             LOGGER.error(msg)
#             persistent_notification.create(
#                 hass, msg, title=NOTIFICATION_TITLE, notification_id=NOTIFICATION_ID
#             )
#             return False

#         # Gather all the available devices...
#         perms = hass.data[DOMAIN]["Session"].user.get_residential_permissions()
#         all_switches = []
#         for permission in perms:
#             if permission.residentialAccountId is not None:
#                 acct = ResidentialAccount(
#                     hass.data[DOMAIN]["Session"], permission.residentialAccountId
#                 )
#                 for residence in acct.get_residences():
#                     for switch in residence.get_iot_switches():
#                         all_switches.append(switch)
#             elif permission.residenceId is not None:
#                 residence = Residence(
#                     hass.data[DOMAIN]["Session"], permission.residenceId
#                 )
#                 for switch in residence.get_iot_switches():
#                     # search all_switches for duplicates by matching switch.mac, only append if not found
#                     if not any(x.mac == switch.mac for x in all_switches):
#                         all_switches.append(switch)
#         hass.data[DOMAIN]["Switches"] = all_switches
#         return True

#     except ValueError:
#         LOGGER.error("Failed to communicate with myLeviton Service")
#         return False

# # Listen for the stop event and log out.
# def logout(event):
#     """Log out..."""
#     try:
#         if hass.data[DOMAIN]["Session"] is not None:
#             Person.logout(hass.data[DOMAIN]["Session"])
#     except ValueError:
#         LOGGER.error("Failed to log out of myLeviton Service")

# hass.bus.listen(EVENT_HOMEASSISTANT_STOP, logout)
