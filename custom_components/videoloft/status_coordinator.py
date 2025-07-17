"""Enhanced coordinator for VideLoft device status management."""

import logging
from typing import Dict, Any, List, Optional, Set
from datetime import datetime, timedelta
import asyncio

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    DOMAIN, 
    STATUS_UPDATE_INTERVAL,
    CONNECTIVITY_UPDATE_INTERVAL,
    FIRMWARE_UPDATE_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)

# ----------------------------------------------------------
# STATUS COORDINATOR CLASS
# ----------------------------------------------------------


class VideoloftStatusCoordinator(DataUpdateCoordinator):
    """Coordinator for managing camera status updates."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, api) -> None:
        """Initialize the status coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_status",
            update_interval=timedelta(seconds=STATUS_UPDATE_INTERVAL),
        )
        self.entry = entry
        self.api = api
        self._device_data: Dict[str, Dict[str, Any]] = {}
        self._last_connectivity_check = {}
        self._last_firmware_check = {}

    async def _async_update_data(self) -> Dict[str, Dict[str, Any]]:
        """Fetch status data from API."""
        try:
            # Get current devices
            devices = self.hass.data[DOMAIN][self.entry.entry_id]["devices"]
            updated_data = {}
            
            current_time = datetime.now()
            
            for device_data in devices:
                uidd = f"{device_data['uid']}.{device_data['id']}"
                
                # Always update basic status
                updated_data[uidd] = await self._update_device_status(uidd, device_data)
                
                # Connectivity check (every 5 minutes)
                if self._should_update_connectivity(uidd, current_time):
                    await self._update_connectivity_status(uidd, updated_data[uidd])
                    self._last_connectivity_check[uidd] = current_time
                
                # Firmware check (every 12 hours)
                if self._should_update_firmware(uidd, current_time):
                    await self._update_firmware_info(uidd, updated_data[uidd])
                    self._last_firmware_check[uidd] = current_time
            
            self._device_data = updated_data
            return updated_data
            
        except Exception as e:
            _LOGGER.error("Error updating status data: %s", e)
            return self._device_data

    def _should_update_connectivity(self, uidd: str, current_time: datetime) -> bool:
        """Check if connectivity status should be updated."""
        last_check = self._last_connectivity_check.get(uidd)
        if not last_check:
            return True
        return (current_time - last_check).total_seconds() > CONNECTIVITY_UPDATE_INTERVAL

    def _should_update_firmware(self, uidd: str, current_time: datetime) -> bool:
        """Check if firmware info should be updated."""
        last_check = self._last_firmware_check.get(uidd)
        if not last_check:
            return True
        return (current_time - last_check).total_seconds() > FIRMWARE_UPDATE_INTERVAL

    async def _update_device_status(self, uidd: str, device_data: Dict[str, Any]) -> Dict[str, Any]:
        """Update basic device status."""
        try:
            # Get logger server for status check
            logger_server = device_data.get("logger")
            if not logger_server:
                _LOGGER.warning("No logger server for device %s", uidd)
                return device_data.copy()

            # Get current camera status
            status_data = await self.api.get_camera_status(uidd, logger_server)
            owner_uid, device_uid = uidd.split('.')
            device_status = status_data.get("result", {}).get(owner_uid, {}).get("devices", {}).get(device_uid, {})

            # Update status fields
            updated_data = device_data.copy()
            updated_data.update({
                "current_status": device_status.get("status", "unknown"),
                "live_active": device_status.get("live", False),
                "current_wowza": device_status.get("wowza", ""),
                "current_stream_name": device_status.get("liveStreamName", ""),
                "last_status_update": datetime.now().isoformat(),
            })

            return updated_data

        except Exception as e:
            _LOGGER.debug("Error updating device status for %s: %s", uidd, e)
            return device_data.copy()

    async def _update_connectivity_status(self, uidd: str, device_data: Dict[str, Any]) -> None:
        """Update connectivity-specific status."""
        try:
            # Check if camera is responsive
            logger_server = device_data.get("logger")
            if logger_server:
                # Simple ping-like check
                session = async_get_clientsession(self.hass)
                async with session.get(f"https://{logger_server}/health", timeout=5) as response:
                    device_data["connectivity_status"] = "online" if response.status == 200 else "degraded"
            else:
                device_data["connectivity_status"] = "unknown"
                
        except Exception:
            device_data["connectivity_status"] = "offline"

    async def _update_firmware_info(self, uidd: str, device_data: Dict[str, Any]) -> None:
        """Update firmware-related information."""
        try:
            # This would check for firmware updates if API supports it
            device_data["firmware_check_time"] = datetime.now().isoformat()
            device_data["firmware_up_to_date"] = True  # Default assumption
            
        except Exception as e:
            _LOGGER.debug("Error checking firmware for %s: %s", uidd, e)

    def get_device_data(self, uidd: str) -> Optional[Dict[str, Any]]:
        """Get current data for a specific device."""
        return self._device_data.get(uidd)

    def get_all_devices(self) -> Dict[str, Dict[str, Any]]:
        """Get all device data."""
        return self._device_data.copy()

    async def async_refresh_device(self, uidd: str) -> None:
        """Force refresh of a specific device."""
        try:
            devices = self.hass.data[DOMAIN][self.entry.entry_id]["devices"]
            device_data = next((d for d in devices if f"{d['uid']}.{d['id']}" == uidd), None)
            
            if device_data:
                updated_data = await self._update_device_status(uidd, device_data)
                await self._update_connectivity_status(uidd, updated_data)
                self._device_data[uidd] = updated_data
                
                # Notify listeners
                self.async_update_listeners()
                
        except Exception as e:
            _LOGGER.error("Error refreshing device %s: %s", uidd, e)
