"""Status sensor platform for VideLoft integration."""

import logging
from typing import Any, Dict, Optional
from datetime import datetime

from homeassistant.components.sensor import (
    SensorEntity,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import EntityCategory

from .const import DOMAIN
from .device_info import create_device_info, get_technical_specs, get_network_info

_LOGGER = logging.getLogger(__name__)

# ----------------------------------------------------------
# PLATFORM SETUP
# ----------------------------------------------------------


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up VideLoft status sensors."""
    devices = hass.data[DOMAIN][entry.entry_id]["devices"]
    
    entities = []
    for device_data in devices:
        uidd = f"{device_data['uid']}.{device_data['id']}"
        
        # Create status sensors for each camera
        entities.extend([
            VideoloftLastSeenSensor(uidd, device_data),
            VideoloftFirmwareVersionSensor(uidd, device_data),
            VideoloftResolutionSensor(uidd, device_data),
            VideoloftCodecSensor(uidd, device_data),
            VideoloftAnalyticsSchemeSensor(uidd, device_data),
        ])

    async_add_entities(entities)

# ----------------------------------------------------------
# STATUS SENSOR CLASSES
# ----------------------------------------------------------


class VideoloftStatusSensorBase(SensorEntity):
    """Base class for VideLoft status sensors."""

    def __init__(self, uidd: str, device_data: Dict[str, Any], sensor_type: str) -> None:
        """Initialize the status sensor."""
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


class VideoloftLastSeenSensor(VideoloftStatusSensorBase):
    """Sensor for last seen timestamp."""

    def __init__(self, uidd: str, device_data: Dict[str, Any]) -> None:
        """Initialize the last seen sensor."""
        super().__init__(uidd, device_data, "last_seen")
        
        camera_name = device_data.get("name", f"Camera {uidd}")
        self._attr_name = f"{camera_name} Last Seen"
        self._attr_device_class = SensorDeviceClass.TIMESTAMP
        self._attr_icon = "mdi:clock-outline"

    @property
    def native_value(self) -> Optional[datetime]:
        """Return the last seen timestamp."""
        last_logger = self.device_data.get("lastLogger")
        if last_logger:
            try:
                # Parse ISO format timestamp
                return datetime.fromisoformat(last_logger.replace('Z', '+00:00'))
            except (ValueError, AttributeError):
                _LOGGER.warning("Invalid timestamp format: %s", last_logger)
        return None


class VideoloftFirmwareVersionSensor(VideoloftStatusSensorBase):
    """Sensor for firmware version."""

    def __init__(self, uidd: str, device_data: Dict[str, Any]) -> None:
        """Initialize the firmware version sensor."""
        super().__init__(uidd, device_data, "firmware_version")
        
        camera_name = device_data.get("name", f"Camera {uidd}")
        self._attr_name = f"{camera_name} Firmware Version"
        self._attr_icon = "mdi:chip"

    @property
    def native_value(self) -> str:
        """Return the firmware version."""
        return self.device_data.get("cloudAdapterVersion", "Unknown")


class VideoloftResolutionSensor(VideoloftStatusSensorBase):
    """Sensor for recording resolution."""

    def __init__(self, uidd: str, device_data: Dict[str, Any]) -> None:
        """Initialize the resolution sensor."""
        super().__init__(uidd, device_data, "resolution")
        
        camera_name = device_data.get("name", f"Camera {uidd}")
        self._attr_name = f"{camera_name} Recording Resolution"
        self._attr_icon = "mdi:video-high-definition"

    @property
    def native_value(self) -> str:
        """Return the recording resolution."""
        return self.device_data.get("recordingResolution", "Unknown")


class VideoloftCodecSensor(VideoloftStatusSensorBase):
    """Sensor for video codec."""

    def __init__(self, uidd: str, device_data: Dict[str, Any]) -> None:
        """Initialize the codec sensor."""
        super().__init__(uidd, device_data, "video_codec")
        
        camera_name = device_data.get("name", f"Camera {uidd}")
        self._attr_name = f"{camera_name} Video Codec"
        self._attr_icon = "mdi:file-video"

    @property
    def native_value(self) -> str:
        """Return the video codec."""
        return self.device_data.get("videoCodec", "Unknown")


class VideoloftAnalyticsSchemeSensor(VideoloftStatusSensorBase):
    """Sensor for analytics scheme."""

    def __init__(self, uidd: str, device_data: Dict[str, Any]) -> None:
        """Initialize the analytics scheme sensor."""
        super().__init__(uidd, device_data, "analytics_scheme")
        
        camera_name = device_data.get("name", f"Camera {uidd}")
        self._attr_name = f"{camera_name} Analytics Scheme"
        self._attr_icon = "mdi:brain"

    @property
    def native_value(self) -> str:
        """Return the analytics scheme."""
        return self.device_data.get("analyticsScheme", "Unknown")

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return extra state attributes."""
        attrs = super().extra_state_attributes
        attrs.update({
            "analytics_enabled": bool(self.device_data.get("analyticsEnabled", 0)),
        })
        return attrs
