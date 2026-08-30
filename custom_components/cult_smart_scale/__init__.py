"""The Cult Smart Scale integration."""

from __future__ import annotations

import logging

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv

from .const import (
    ATTR_USER_ID,
    DOMAIN,
    SERVICE_ASSIGN_READING,
)
from .coordinator import CultScaleDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR]

ASSIGN_READING_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_USER_ID): cv.string,
    }
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Cult Smart Scale from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    coordinator = CultScaleDataUpdateCoordinator(hass, entry)
    hass.data[DOMAIN][entry.entry_id] = coordinator

    # Start listening to BLE
    await coordinator.async_start()

    # Forward setup to sensor platform
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Listen for option changes (e.g. users added/removed, mode changed)
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    # Register custom service: cult_smart_scale.assign_reading
    async def handle_assign_reading(call: ServiceCall) -> None:
        """Handle assign reading service call."""
        user_id = call.data[ATTR_USER_ID]
        # Search all active coordinators
        for coord in hass.data[DOMAIN].values():
            if isinstance(coord, CultScaleDataUpdateCoordinator):
                await coord.async_assign_reading(user_id)

    if not hass.services.has_service(DOMAIN, SERVICE_ASSIGN_READING):
        hass.services.async_register(
            DOMAIN,
            SERVICE_ASSIGN_READING,
            handle_assign_reading,
            schema=ASSIGN_READING_SCHEMA,
        )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    coordinator: CultScaleDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    await coordinator.async_stop()

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry when options are updated."""
    await hass.config_entries.async_reload(entry.entry_id)
