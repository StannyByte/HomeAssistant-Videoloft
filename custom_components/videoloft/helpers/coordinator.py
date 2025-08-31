# coordinator.py

from __future__ import annotations

import logging
from typing import List, Dict, Any, Optional
import asyncio
from datetime import datetime, timedelta
import aiofiles

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers import storage
from homeassistant.util import dt as dt_util

from ..const import (
    DOMAIN,
    LPR_STORAGE_VERSION,
    LPR_STORAGE_KEY,
)
from .gemini_api import GeminiAPI

_LOGGER = logging.getLogger(__name__)

# ----------------------------------------------------------
# MAIN COORDINATOR CLASS
# ----------------------------------------------------------

class VideoloftCoordinator:
    """Class to manage Videoloft triggers, thumbnails, and state."""
    
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the coordinator."""
        self.hass = hass
        self.entry = entry
        self.api = hass.data[DOMAIN][entry.entry_id]["api"]  # Add API reference
        self.gemini_api = GeminiAPI(hass, self.api)  # Initialize Gemini API
        self._store = storage.Store(
            hass,
            LPR_STORAGE_VERSION,
            f"{DOMAIN}_{LPR_STORAGE_KEY}_{entry.entry_id}"
        )
        self._triggers: List[Dict[str, Any]] = []
        self._descriptions: Dict[str, Any] = {}
        
        # Thumbnail caching
        self._thumbnail_cache: Dict[str, Dict[str, Any]] = {}
        self._thumbnail_refresh_task: Optional[asyncio.Task] = None
        self._thumbnail_cache_duration = timedelta(minutes=5)  # Cache for 5 minutes
        self._thumbnail_refresh_interval = timedelta(minutes=2)  # Refresh every 2 minutes
        
        _LOGGER.debug("Initialized VideoloftCoordinator with thumbnail caching")

    async def async_setup(self) -> bool:
        """Set up the coordinator."""
        try:
            # Initialize Gemini API with quota tracking
            await self.gemini_api.initialize()
            
            # Load existing data
            self._triggers = await self._store.async_load() or []
            self._descriptions = await self.async_load_descriptions() or {}
            
            # Initialize data structure
            if DOMAIN not in self.hass.data:
                self.hass.data[DOMAIN] = {}
            if self.entry.entry_id not in self.hass.data[DOMAIN]:
                self.hass.data[DOMAIN][self.entry.entry_id] = {}
                
            self.hass.data[DOMAIN][self.entry.entry_id].update({
                "coordinator": self,
                "lpr_triggers": self._triggers,
                "descriptions": self._descriptions
            })
            
            # Start the thumbnail cache refresh task
            if self._thumbnail_refresh_task is None:
                self._thumbnail_refresh_task = self.hass.loop.create_task(self._async_refresh_thumbnail_cache())
            
            # Preload thumbnails after a short delay to allow system to stabilize
            self.hass.loop.call_later(5, lambda: self.hass.async_create_task(self.preload_all_thumbnails()))
            
            _LOGGER.debug("Coordinator setup complete")
            return True

    # ----------------------------------------------------------
    # LPR TRIGGER MANAGEMENT
    # ----------------------------------------------------------            
        except Exception as e:
            _LOGGER.error("Failed to setup coordinator: %s", e, exc_info=True)
            return False
            
    async def async_load_triggers(self) -> List[Dict[str, Any]]:
        """Load triggers from storage."""
        try:
            # Make sure self._triggers is always a list
            if not isinstance(self._triggers, list):
                self._triggers = []
            return self._triggers
        except Exception as e:
            _LOGGER.error("Error loading triggers: %s", e)
            return []

    async def async_save_triggers(self, triggers: List[Dict[str, Any]]) -> None:
        """Save triggers to storage."""
        await self._store.async_save(triggers)
        self._triggers = triggers
        self.hass.data[DOMAIN][self.entry.entry_id]["lpr_triggers"] = triggers

    async def process_events(self, api_key: str, selected_cameras: List[str]) -> None:
        """Process events for selected cameras."""
        # Get the sensor from the existing entities instead of creating new one
        for entity in self.hass.data[DOMAIN][self.entry.entry_id].get("entities", []):
            if hasattr(entity, 'process_events') and entity.__class__.__name__ == "VideoloftLPRSensor":
                await entity.process_events(api_key, selected_cameras)
                return

    async def process_ai_search(self, selected_cameras: List[str]) -> None:
        """Process events and get descriptions from Google Gemini."""
        await self.gemini_api.process_ai_search(selected_cameras)

    async def async_load_descriptions(self) -> Dict[str, Any]:
        """Load stored descriptions from Home Assistant storage."""
        return await self.gemini_api.async_load_descriptions()

    async def async_save_descriptions(self, descriptions: Dict[str, Any]) -> None:
        """Save descriptions to Home Assistant storage."""
        await self.gemini_api.async_save_descriptions(descriptions)

    async def clear_descriptions(self) -> None:
        """Clear all stored event descriptions."""
        await self.gemini_api.clear_descriptions()
        self._descriptions = {}

    async def get_gemini_quota_status(self) -> Dict[str, Any]:
        """Get Gemini API quota status."""
        return await self.gemini_api.get_quota_status()

    async def reset_gemini_quota_state(self) -> Dict[str, Any]:
        """Reset Gemini quota state (for testing or manual reset)."""
        return await self.gemini_api.reset_quota_state()

    async def force_circuit_breaker_reset(self) -> Dict[str, Any]:
        """Force reset the Gemini circuit breaker (emergency use only)."""
        return await self.gemini_api.force_circuit_breaker_reset()

    # ----------------------------------------------------------
    # THUMBNAIL CACHING SYSTEM
    # ----------------------------------------------------------
    
    # Thumbnail Caching Methods
    async def get_cached_thumbnail(self, uidd: str) -> Optional[bytes]:
        """Get cached thumbnail for a camera."""
        cache_entry = self._thumbnail_cache.get(uidd)
        if not cache_entry:
            return None
            
        cached_time = cache_entry.get("timestamp")
        if not cached_time:
            return None
            
        # Check if cache is still valid - use different expiry for immediate requests
        cache_age = dt_util.utcnow() - cached_time
        if cache_age > self._thumbnail_cache_duration:
            _LOGGER.debug(f"Thumbnail cache expired for {uidd}")
            return None
            
        return cache_entry.get("data")

    async def get_cached_thumbnail_immediate(self, uidd: str) -> Optional[bytes]:
        """Get cached thumbnail immediately, even if slightly stale."""
        try:
            cache_entry = self._thumbnail_cache.get(uidd)
            if not cache_entry:
                return None
                
            cached_time = cache_entry.get("timestamp")
            if not cached_time:
                return None
                
            # Allow slightly stale thumbnails for immediate display (up to 10 minutes)
            cache_age = dt_util.utcnow() - cached_time
            if cache_age > timedelta(minutes=10):
                _LOGGER.debug(f"Thumbnail cache too old for {uidd}")
                return None
                
            data = cache_entry.get("data")
            # Ensure we return bytes, not a coroutine
            if isinstance(data, bytes):
                return data
            else:
                _LOGGER.warning(f"Cached thumbnail data for {uidd} is not bytes: {type(data)}")
                return None
        except Exception as e:
            _LOGGER.error(f"Error getting cached thumbnail for {uidd}: {e}")
            return None

    async def refresh_thumbnail(self, uidd: str, force: bool = False) -> Optional[bytes]:
        """Refresh thumbnail for a specific camera."""
        try:
            # Check if we need to refresh
            if not force:
                cache_entry = self._thumbnail_cache.get(uidd)
                if cache_entry:
                    cached_time = cache_entry.get("timestamp")
                    if cached_time:
                        cache_age = dt_util.utcnow() - cached_time
                        if cache_age < self._thumbnail_refresh_interval:
                            return cache_entry.get("data")
            
            # Get device data to find logger server
            devices = self.hass.data[DOMAIN][self.entry.entry_id].get("devices", [])
            device_data = None
            for device in devices:
                if f"{device['uid']}.{device['id']}" == uidd:
                    device_data = device
                    break
                    
            if not device_data:
                _LOGGER.warning(f"Device data not found for {uidd}")
                return None
                
            logger_server = device_data.get("logger")
            if not logger_server:
                _LOGGER.warning(f"No logger server for {uidd}")
                return None
            
            # Fetch new thumbnail
            thumbnail_data = await self.api.get_camera_thumbnail(uidd, logger_server)
            if thumbnail_data and isinstance(thumbnail_data, bytes):
                # Cache the thumbnail
                self._thumbnail_cache[uidd] = {
                    "data": thumbnail_data,
                    "timestamp": dt_util.utcnow(),
                    "size": len(thumbnail_data)
                }
                _LOGGER.debug(f"Thumbnail refreshed for {uidd} ({len(thumbnail_data)} bytes)")
                return thumbnail_data
            elif thumbnail_data is not None:
                _LOGGER.error(f"Thumbnail data for {uidd} is not bytes: {type(thumbnail_data)}")
                return None
            else:
                _LOGGER.warning(f"No thumbnail data received for {uidd}")
                return None
                
        except Exception as e:
            _LOGGER.error(f"Error refreshing thumbnail for {uidd}: {e}")
            return None

    async def preload_all_thumbnails(self) -> None:
        """Preload thumbnails for all cameras to improve frontend loading."""
        try:
            _LOGGER.debug("Starting thumbnail preload for all cameras")
            devices = self.hass.data[DOMAIN][self.entry.entry_id].get("devices", [])
            
            # Create tasks for parallel thumbnail loading
            tasks = []
            for device in devices:
                uidd = f"{device['uid']}.{device['id']}"
                task = self.refresh_thumbnail(uidd, force=False)
                tasks.append(task)
            
            # Execute all thumbnail fetches in parallel
            if tasks:
                results = await asyncio.gather(*tasks, return_exceptions=True)
                successful_loads = sum(1 for result in results if result and not isinstance(result, Exception))
                _LOGGER.info(f"Preloaded {successful_loads}/{len(tasks)} thumbnails")
            
        except Exception as e:
            _LOGGER.error(f"Error during thumbnail preload: {e}")

    async def ensure_thumbnail_available(self, uidd: str) -> Optional[bytes]:
        """Ensure a thumbnail is available, using cache or fetching fresh."""
        try:
            # First try immediate cache (allows slightly stale)
            thumbnail_data = await self.get_cached_thumbnail_immediate(uidd)
            if thumbnail_data and isinstance(thumbnail_data, bytes):
                return thumbnail_data
            
            # If no cache, fetch fresh
            fresh_data = await self.refresh_thumbnail(uidd, force=True)
            if fresh_data and isinstance(fresh_data, bytes):
                return fresh_data
            
            _LOGGER.warning(f"Unable to get thumbnail for {uidd}")
            return None
        except Exception as e:
            _LOGGER.error(f"Error ensuring thumbnail available for {uidd}: {e}")
            return None

    async def _async_refresh_thumbnail_cache(self) -> None:
        """Background task to periodically refresh thumbnails."""
        _LOGGER.debug("Starting thumbnail cache refresh task")
        
        while True:
            try:
                # Get all devices
                devices = self.hass.data[DOMAIN][self.entry.entry_id].get("devices", [])
                
                for device in devices:
                    uidd = f"{device['uid']}.{device['id']}"
                    await self.refresh_thumbnail(uidd)
                    # Small delay between cameras to avoid overwhelming the servers
                    await asyncio.sleep(1)
                
                # Wait for the next refresh cycle
                await asyncio.sleep(self._thumbnail_refresh_interval.total_seconds())
                
            except asyncio.CancelledError:
                _LOGGER.debug("Thumbnail refresh task cancelled")
                break
            except Exception as e:
                _LOGGER.error(f"Error in thumbnail refresh task: {e}")
                # Wait a bit before retrying
                await asyncio.sleep(30)

    async def get_thumbnail_cache_stats(self) -> Dict[str, Any]:
        """Get thumbnail cache statistics."""
        total_size = sum(entry.get("size", 0) for entry in self._thumbnail_cache.values())
        cache_count = len(self._thumbnail_cache)
        
        return {
            "cached_thumbnails": cache_count,
            "total_cache_size": total_size,
            "cache_duration_minutes": self._thumbnail_cache_duration.total_seconds() / 60,
            "refresh_interval_minutes": self._thumbnail_refresh_interval.total_seconds() / 60
        }

    async def async_cleanup(self):
        """Clean up coordinator resources."""
        try:
            _LOGGER.debug("Starting coordinator cleanup...")
            
            # Cancel the thumbnail refresh task
            if self._thumbnail_refresh_task is not None:
                self._thumbnail_refresh_task.cancel()
                self._thumbnail_refresh_task = None
            
            # Clear caches and reset state
            self._triggers = []
            self._descriptions = {}
            self._thumbnail_cache = {}
            
            # Clear any stored references
            if hasattr(self, 'api') and self.api:
                try:
                    # Don't close the API here as it might be used by other components
                    # The API will be closed in the main unload function
                    self.api = None
                except Exception as e:
                    _LOGGER.warning("Error clearing API reference: %s", e)
            
            _LOGGER.debug("Coordinator cleanup completed")
            
        except Exception as e:
            _LOGGER.error("Error during coordinator cleanup: %s", e)
            raise
