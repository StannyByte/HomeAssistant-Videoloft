"""Binary sensor platform for VideLoft integration."""

import logging
from typing import Any, Dict, Optional
from datetime import datetime

from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorDeviceClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import EntityCategory

from .const import DOMAIN
from .helpers.device_info import create_device_info, get_camera_capabilities

_LOGGER = logging.getLogger(__name__)

# ----------------------------------------------------------
# PLATFORM SETUP
# ----------------------------------------------------------


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up VideLoft binary sensors."""
    devices = hass.data[DOMAIN][entry.entry_id]["devices"]
    
    entities = []
    for device_data in devices:
        uidd = f"{device_data['uid']}.{device_data['id']}"
        capabilities = get_camera_capabilities(device_data)
        
        # Always create connectivity sensor
        entities.append(VideoloftConnectivitySensor(uidd, device_data))
        
        # Create capability-based sensors
        if capabilities["cloud_recording"]:
            entities.append(VideoloftCloudRecordingSensor(uidd, device_data))
        
        if capabilities["analytics"]:
            entities.append(VideoloftAnalyticsSensor(uidd, device_data))
            
        if capabilities["mainstream_live"]:
            entities.append(VideoloftStreamStatusSensor(uidd, device_data))

    async_add_entities(entities)

# ----------------------------------------------------------
# BASE BINARY SENSOR CLASS
# ----------------------------------------------------------


class VideoloftBinarySensorBase(BinarySensorEntity):
    """Base class for VideLoft binary sensors."""

    def __init__(self, uidd: str, device_data: Dict[str, Any], sensor_type: str) -> None:
        """Initialize the binary sensor."""
        self.uidd = uidd
        self.device_data = device_data
        self.sensor_type = sensor_type
        
        # Set up basic attributes
        self._attr_unique_id = f"videoloft_{sensor_type}_{uidd}"
        self._attr_device_info = create_device_info(uidd, device_data)
        self._attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return extra state attributes."""
        return {
            "device_id": self.uidd,
            "last_updated": datetime.now().isoformat(),
        }

# ----------------------------------------------------------
# BINARY SENSOR IMPLEMENTATIONS
# ----------------------------------------------------------


class VideoloftConnectivitySensor(VideoloftBinarySensorBase):
    """Binary sensor for camera connectivity status."""

    def __init__(self, uidd: str, device_data: Dict[str, Any]) -> None:
        """Initialize the connectivity sensor."""
        super().__init__(uidd, device_data, "connectivity")
        
        camera_name = device_data.get("name", f"Camera {uidd}")
        self._attr_name = f"{camera_name} Connectivity"
        self._attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
        self._attr_icon = "mdi:wifi"

    @property
    def is_on(self) -> bool:
        """Return True if camera is connected."""
        return bool(self.device_data.get("mainstreamLive", 0))

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return extra state attributes."""
        attrs = super().extra_state_attributes
        attrs.update({
            "logger_server": self.device_data.get("logger", ""),
            "last_logger_time": self.device_data.get("lastLogger", ""),
            "local_live_hosts": self.device_data.get("localLiveHosts", []),
        })
        return attrs


class VideoloftCloudRecordingSensor(VideoloftBinarySensorBase):
    """Binary sensor for cloud recording status."""

    def __init__(self, uidd: str, device_data: Dict[str, Any]) -> None:
        """Initialize the cloud recording sensor."""
        super().__init__(uidd, device_data, "cloud_recording")
        
        camera_name = device_data.get("name", f"Camera {uidd}")
        self._attr_name = f"{camera_name} Cloud Recording"
        self._attr_device_class = BinarySensorDeviceClass.RUNNING
        self._attr_icon = "mdi:cloud-upload"

    @property
    def is_on(self) -> bool:
        """Return True if cloud recording is enabled."""
        return bool(self.device_data.get("cloudRecordingEnabled", 0))

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return extra state attributes."""
        attrs = super().extra_state_attributes
        attrs.update({
            "recorded_stream_name": self.device_data.get("recordedStreamName", ""),
            "recording_resolution": self.device_data.get("recordingResolution", ""),
        })
        return attrs


class VideoloftAnalyticsSensor(VideoloftBinarySensorBase):
    """Binary sensor for analytics status."""

    def __init__(self, uidd: str, device_data: Dict[str, Any]) -> None:
        """Initialize the analytics sensor."""
        super().__init__(uidd, device_data, "analytics")
        
        camera_name = device_data.get("name", f"Camera {uidd}")
        self._attr_name = f"{camera_name} Analytics"
        self._attr_device_class = BinarySensorDeviceClass.RUNNING
        self._attr_icon = "mdi:brain"

    @property
    def is_on(self) -> bool:
        """Return True if analytics is enabled."""
        return bool(self.device_data.get("analyticsEnabled", 0))

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return extra state attributes."""
        attrs = super().extra_state_attributes
        attrs.update({
            "analytics_scheme": self.device_data.get("analyticsScheme", ""),
        })
        return attrs


class VideoloftStreamStatusSensor(VideoloftBinarySensorBase):
    """Binary sensor for live stream status."""

    def __init__(self, uidd: str, device_data: Dict[str, Any]) -> None:
        """Initialize the stream status sensor."""
        super().__init__(uidd, device_data, "stream_status")
        
        camera_name = device_data.get("name", f"Camera {uidd}")
        self._attr_name = f"{camera_name} Live Stream"
        self._attr_device_class = BinarySensorDeviceClass.RUNNING
        self._attr_icon = "mdi:video"

    @property
    def is_on(self) -> bool:
        """Return True if live stream is active."""
        return bool(self.device_data.get("mainstreamLive", 0))

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return extra state attributes."""
        attrs = super().extra_state_attributes
        attrs.update({
            "video_codec": self.device_data.get("videoCodec", ""),
            "wowza_server": self.device_data.get("wowza", ""),
        })
        return attrs
