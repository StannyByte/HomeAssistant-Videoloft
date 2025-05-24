"""The Videoloft integration."""
import asyncio
import logging
from typing import List

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.components.frontend import async_register_built_in_panel
from homeassistant.components.http import StaticPathConfig
from homeassistant.exceptions import ConfigEntryNotReady

from .const import DOMAIN, PLATFORMS
from .api import VideoloftAPI
from .camera import VideoloftCameraStreamView
from .coordinator import VideoloftCoordinator
from .views import (
    VideoloftCamerasView,
    VideoloftThumbnailView,
    VideoloftEventsView,
    EventThumbnailView,
    LPRTriggersView,
    LPRLogsWebSocket,
    GeminiKeyView,
    ProcessEventsView,
    SearchEventsView,
    AISearchProcessView,
    ClearDescriptionsView
)

from .sensor import LPRUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Videoloft from a config entry."""
    _LOGGER.debug("Setting up Videoloft integration")
    hass.data.setdefault(DOMAIN, {})

    try:
        api = VideoloftAPI(entry.data["email"], entry.data["password"], hass)
        await api.authenticate()
        devices = await api.get_device_info()
        if not devices or "result" not in devices:
            _LOGGER.error("Failed to retrieve device information.")
            return False

        # Initialize data structures for the integration
        hass.data[DOMAIN][entry.entry_id] = {
            "api": api,
            "devices": devices,
            "tasks": [],
            "lpr_triggers": []  # Initialize LPR triggers list
        }

        # Initialize the coordinator first
        coordinator = VideoloftCoordinator(hass, entry)
        await coordinator.async_setup()
        hass.data[DOMAIN][entry.entry_id]["coordinator"] = coordinator

        # Register views
        hass.http.register_view(VideoloftCameraStreamView(hass, api))
        hass.http.register_view(VideoloftCamerasView(hass))
        hass.http.register_view(VideoloftThumbnailView(hass))
        hass.http.register_view(VideoloftEventsView(hass))
        hass.http.register_view(EventThumbnailView(hass))
        hass.http.register_view(LPRTriggersView(hass))
        hass.http.register_view(LPRLogsWebSocket(hass))
        hass.http.register_view(GeminiKeyView(hass))
        hass.http.register_view(ProcessEventsView(hass))
        hass.http.register_view(SearchEventsView(hass))
        hass.http.register_view(AISearchProcessView(hass))
        hass.http.register_view(ClearDescriptionsView(hass))

        # Register static paths for all HTML, CSS, and JS files
        static_files = [
            "videoloft_cams.html",
        ]
        for file in static_files:
            hass.http.register_static_path(
                f"/videoloft_panel/{file}",
                hass.config.path(f"custom_components/videoloft/panel/{file}"),
                cache_headers=False,
            )

        # Register the CSS directory
        hass.http.register_static_path(
            "/videoloft_panel/css",
            hass.config.path("custom_components/videoloft/panel/css"),
            cache_headers=False,
        )

        # Register the JS directory
        hass.http.register_static_path(
            "/videoloft_panel/js",
            hass.config.path("custom_components/videoloft/panel/js"),
            cache_headers=False,
        )

        # Register the side panel
        if hasattr(hass, "components") and hasattr(hass.components, "frontend"):
            hass.components.frontend.async_register_built_in_panel(
                component_name="iframe",
                sidebar_title="Videoloft",
                sidebar_icon="mdi:cctv",
                frontend_url_path="videoloft_panel",
                config={"url": "/videoloft_panel/videoloft_cams.html"},
                require_admin=False,
            )
        else:
            async_register_built_in_panel(
                hass,
                component_name="iframe",
                sidebar_title="Videoloft",
                sidebar_icon="mdi:cctv",
                frontend_url_path="videoloft_panel",
                config={"url": "/videoloft_panel/videoloft_cams.html"},
                require_admin=False,
            )

        # Forward the setup to the defined platforms (camera and sensor)
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

        return True

    except Exception as e:
        _LOGGER.error(f"Error setting up Videoloft: {e}")
        return False

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a Videoloft config entry."""
    try:
        # First cancel any running tasks
        tasks = hass.data[DOMAIN][entry.entry_id].get("tasks", [])
        for task in tasks:
            task.cancel()

        # Wait for tasks to complete with exceptions handled
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        # Unload platforms
        unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


        if unload_ok:
            # Properly close the API session
            api = hass.data[DOMAIN][entry.entry_id].get("api")
            if api:
                await api.close()

            # Clean up entry data
            hass.data[DOMAIN].pop(entry.entry_id)

            # Remove frontend panel (handle potential attribute errors)
            if hasattr(hass, "components") and hasattr(hass.components, "frontend"):
                hass.components.frontend.async_remove_panel("videoloft_panel")

        return unload_ok

    except Exception as e:
        _LOGGER.error(f"Error unloading entry: {e}")
        return False
