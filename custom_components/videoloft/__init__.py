"""The Videoloft integration."""
import asyncio
import logging
from typing import List

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.components.frontend import async_register_built_in_panel
from homeassistant.components.http import StaticPathConfig
from homeassistant.exceptions import ConfigEntryNotReady, HomeAssistantError

from .const import DOMAIN, PLATFORMS
from .api import VideoloftAPI, VideoloftApiClientError
from .camera import VideoloftCameraStreamView
from .coordinator import VideoloftCoordinator
from .status_coordinator import VideoloftStatusCoordinator
from .views import (
    VideoloftCamerasView,
    VideoloftThumbnailView,
    VideoloftThumbnailStatsView,
    VideoloftThumbnailPreloadView,
    VideoloftEventsView,
    EventThumbnailView,
    LPRTriggersView,
    LPRLogsWebSocket,
    GeminiKeyView,
    ProcessEventsView,
    SearchEventsView,
    AISearchProcessView,
    ClearDescriptionsView,
    AIAnalysisView,
    AISearchView,
    VideoloftCameraDiagnosticView,
    GeminiQuotaView
)

_LOGGER = logging.getLogger(__name__)

# ----------------------------------------------------------
# INTEGRATION SETUP
# ----------------------------------------------------------

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Videoloft from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    
    try:
        api = VideoloftAPI(entry.data["email"], entry.data["password"], hass)
        await api.authenticate()
        cameras_info = await api.get_cameras_info()

    except VideoloftApiClientError as err:
        _LOGGER.error(f"Client error during setup: {err}")
        raise ConfigEntryNotReady from err
    except Exception as err:
        _LOGGER.error(f"Unexpected error during setup: {err}", exc_info=True)
        raise ConfigEntryNotReady from err

    if not cameras_info:
        _LOGGER.warning("No cameras found in the Videoloft account. The integration will still load, but no camera entities will be created.")
        
        # Still create the entry with minimal data
        hass.data[DOMAIN][entry.entry_id] = {
            "api": api,
            "devices": [],
            "tasks": [],
            "lpr_triggers": []
        }
        
        # Optionally, you might want to show a persistent notification
        await hass.services.async_call(
            "persistent_notification",
            "create",
            {
                "message": "No cameras found in your Videoloft account. Please check your account setup or contact Videoloft support.",
                "title": "Videoloft Integration",
                "notification_id": "videoloft_no_cameras"
            }
        )
        
        return True  # Still return True to allow the integration to load

    hass.data[DOMAIN][entry.entry_id] = {
        "api": api,
        "devices": cameras_info,
        "tasks": [],
        "lpr_triggers": []
    }

    coordinator = VideoloftCoordinator(hass, entry)
    if not await coordinator.async_setup():
        _LOGGER.error("Coordinator setup failed")
        return False
    hass.data[DOMAIN][entry.entry_id]["coordinator"] = coordinator

    # Initialize status coordinator for enhanced device monitoring
    status_coordinator = VideoloftStatusCoordinator(hass, entry, api)
    hass.data[DOMAIN][entry.entry_id]["status_coordinator"] = status_coordinator

    # Register all views including the critical stream view
    # Store view instances for proper cleanup
    views = {
        "camera_stream": VideoloftCameraStreamView(hass, api),
        "cameras": VideoloftCamerasView(hass),
        "thumbnail": VideoloftThumbnailView(hass),
        "thumbnail_stats": VideoloftThumbnailStatsView(hass),
        "thumbnail_preload": VideoloftThumbnailPreloadView(hass),
        "events": VideoloftEventsView(hass),
        "event_thumbnail": EventThumbnailView(hass),
        "lpr_triggers": LPRTriggersView(hass),
        "lpr_logs_ws": LPRLogsWebSocket(hass),
        "gemini_key": GeminiKeyView(hass),
        "process_events": ProcessEventsView(hass),
        "search_events": SearchEventsView(hass),
        "ai_search_process": AISearchProcessView(hass),
        "clear_descriptions": ClearDescriptionsView(hass),
        "ai_analysis": AIAnalysisView(hass),
        "ai_search": AISearchView(hass),
        "camera_diagnostic": VideoloftCameraDiagnosticView(hass),
        "gemini_quota": GeminiQuotaView(hass)
    }
    
    # ----------------------------------------------------------
    # VIEW REGISTRATION
    # ----------------------------------------------------------
    
    # Register all views
    for view_name, view_instance in views.items():
        try:
            hass.http.register_view(view_instance)
            _LOGGER.debug(f"Registered view: {view_name}")
        except Exception as e:
            _LOGGER.error(f"Failed to register view {view_name}: {e}")
            
    # Store view instances for cleanup
    hass.data[DOMAIN][entry.entry_id]["views"] = views
    
    # ----------------------------------------------------------
    # FRONTEND PANEL REGISTRATION
    # ----------------------------------------------------------
    
    # Register static paths using the async method (Home Assistant 2024.6+)
    static_configs = [
        StaticPathConfig(
            "/videoloft_panel/videoloft_cams.html",
            hass.config.path("custom_components/videoloft/panel/videoloft_cams.html"),
            False,
        ),
        StaticPathConfig(
            "/videoloft_panel/css",
            hass.config.path("custom_components/videoloft/panel/css"),
            False,
        ),
        StaticPathConfig(
            "/videoloft_panel/js",
            hass.config.path("custom_components/videoloft/panel/js"),
            False,
        ),
    ]
    await hass.http.async_register_static_paths(static_configs)

    # Register the side panel using the correct method
    try:
        async_register_built_in_panel(
            hass,
            component_name="iframe",
            sidebar_title="Videoloft",
            sidebar_icon="mdi:cctv",
            frontend_url_path="videoloft_panel",
            config={"url": "/videoloft_panel/videoloft_cams.html"},
            require_admin=False,
        )
        _LOGGER.debug("Successfully registered Videoloft panel")
    except Exception as e:
        _LOGGER.warning("Failed to register panel: %s", e)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True

# ----------------------------------------------------------
# INTEGRATION UNLOAD
# ----------------------------------------------------------

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a Videoloft config entry."""
    _LOGGER.debug("Starting unload process for entry %s", entry.entry_id)
    
    try:
        # Get entry data before cleanup
        entry_data = hass.data[DOMAIN].get(entry.entry_id, {})
        
        # Step 1: Unload platforms FIRST to stop all entities
        _LOGGER.debug("Unloading platforms...")
        unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
        
        if not unload_ok:
            _LOGGER.error("Failed to unload platforms for entry %s", entry.entry_id)
            return False
        
        # Step 2: Wait a moment for entities to fully unload
        await asyncio.sleep(0.5)
        
        # Step 3: Cancel any running tasks before other cleanup
        tasks = entry_data.get("tasks", [])
        for task in tasks:
            if not task.done():
                task.cancel()
                _LOGGER.debug("Cancelled background task")

        # Wait for tasks to complete with exceptions handled
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
            _LOGGER.debug("All background tasks stopped")

        # Step 4: Close WebSocket connections and cleanup views
        views = entry_data.get("views", {})
        for view_name, view_instance in views.items():
            try:
                if hasattr(view_instance, 'cleanup'):
                    await view_instance.cleanup()
                    _LOGGER.debug(f"Cleaned up view: {view_name}")
            except Exception as e:
                _LOGGER.warning(f"Error cleaning up view {view_name}: {e}")

        # Step 5: Cleanup coordinator resources
        coordinator = entry_data.get("coordinator")
        if coordinator:
            try:
                await coordinator.async_cleanup()
                _LOGGER.debug("Coordinator cleanup completed")
            except Exception as e:
                _LOGGER.warning("Error during coordinator cleanup: %s", e)

        # Step 5.5: Clean up any sensor coordinators (LPR, status, etc.)
        try:
            # Look for and cleanup any sensor coordinators that might exist
            entities = entry_data.get("entities", [])
            for entity in entities:
                if hasattr(entity, 'coordinator') and hasattr(entity.coordinator, 'async_cleanup'):
                    try:
                        await entity.coordinator.async_cleanup()
                        _LOGGER.debug("Sensor coordinator cleanup completed")
                    except Exception as e:
                        _LOGGER.warning("Error during sensor coordinator cleanup: %s", e)
        except Exception as e:
            _LOGGER.debug("No sensor coordinators to clean up: %s", e)

        # Step 6: Remove frontend panel BEFORE closing API session
        try:
            if hasattr(hass.components, "frontend"):
                await hass.async_add_executor_job(
                    hass.components.frontend.async_remove_panel, "videoloft_panel"
                )
                _LOGGER.debug("Frontend panel removed successfully")
        except Exception as e:
            _LOGGER.debug("Panel removal failed (likely already removed): %s", e)

        # Step 7: Properly close the API session
        api = entry_data.get("api")
        if api:
            try:
                await api.close()
                _LOGGER.debug("API session closed successfully")
            except Exception as e:
                _LOGGER.warning("Error closing API session: %s", e)

        # Step 8: Clean up entry data
        hass.data[DOMAIN].pop(entry.entry_id, None)
        
        # If no more entries, clean up domain data
        if not hass.data[DOMAIN]:
            hass.data.pop(DOMAIN, None)
            _LOGGER.debug("All domain data cleaned up")

        _LOGGER.info("Unload completed successfully for entry %s", entry.entry_id)
        return True

    except Exception as e:
        _LOGGER.error("Error unloading entry %s: %s", entry.entry_id, e, exc_info=True)
        return False

# ----------------------------------------------------------
# INTEGRATION REMOVAL
# ----------------------------------------------------------

async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Remove a config entry and clean up all associated data."""
    _LOGGER.debug("Starting removal process for entry %s", entry.entry_id)
    
    try:
        # Clean up persistent storage
        from homeassistant.helpers import storage
        
        # Remove LPR triggers storage
        store = storage.Store(hass, 1, f"{DOMAIN}_lpr_triggers_{entry.entry_id}")
        try:
            await store.async_remove()
            _LOGGER.debug("LPR triggers storage removed")
        except Exception as e:
            _LOGGER.warning("Error removing LPR triggers storage: %s", e)
        
        # Remove descriptions storage  
        store = storage.Store(hass, 1, f"{DOMAIN}_descriptions")
        try:
            data = await store.async_load()
            if data:
                # Filter out descriptions for this entry if they're tagged
                # (You might need to adapt this based on how you store descriptions)
                await store.async_save({})
            _LOGGER.debug("Descriptions storage cleaned")
        except Exception as e:
            _LOGGER.warning("Error cleaning descriptions storage: %s", e)
        
        # Remove Gemini API key storage
        try:
            if "gemini_api_key" in hass.data.get(DOMAIN, {}):
                hass.data[DOMAIN].pop("gemini_api_key", None)
            _LOGGER.debug("Gemini API key removed from memory")
        except Exception as e:
            _LOGGER.warning("Error removing Gemini API key: %s", e)
            
        _LOGGER.info("Entry removal completed successfully for %s", entry.entry_id)
        
    except Exception as e:
        _LOGGER.error("Error during entry removal for %s: %s", entry.entry_id, e, exc_info=True)