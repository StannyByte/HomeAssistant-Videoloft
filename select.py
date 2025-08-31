"""Select platform for VideLoft integration."""

import logging
from typing import Any, Dict, List, Optional

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import EntityCategory

from .const import DOMAIN
from .helpers.device_info import create_device_info

_LOGGER = logging.getLogger(__name__)

# ----------------------------------------------------------
# PLATFORM SETUP
# ----------------------------------------------------------


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up VideLoft select entities."""
    devices = hass.data[DOMAIN][entry.entry_id]["devices"]
    api = hass.data[DOMAIN][entry.entry_id]["api"]
    
    entities = []
    for device_data in devices:
        uidd = f"{device_data['uid']}.{device_data['id']}"
        
        # Add analytics scheme selector if analytics is enabled
        if device_data.get("analyticsEnabled", 0):
            entities.append(VideoloftAnalyticsSchemeSelect(uidd, device_data, api))
        
        # Add video codec selector (informational/future use)
        entities.append(VideoloftVideoCodecSelect(uidd, device_data, api))

    if entities:
        async_add_entities(entities)

# ----------------------------------------------------------
# BASE SELECT ENTITY CLASS
# ----------------------------------------------------------


class VideoloftSelectBase(SelectEntity):
    """Base class for VideLoft select entities."""

    def __init__(self, uidd: str, device_data: Dict[str, Any], api, select_type: str) -> None:
        """Initialize the select entity."""
        self.uidd = uidd
        self.device_data = device_data
        self.api = api
        self.select_type = select_type
        
        # Set up basic attributes
        self._attr_unique_id = f"videoloft_{select_type}_{uidd}"
        self._attr_device_info = create_device_info(uidd, device_data)
        self._attr_entity_category = EntityCategory.CONFIG

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return extra state attributes."""
        return {
            "device_id": self.uidd,
            "select_type": self.select_type,
        }


class VideoloftAnalyticsSchemeSelect(VideoloftSelectBase):
    """Select entity for analytics scheme."""

    def __init__(self, uidd: str, device_data: Dict[str, Any], api) -> None:
        """Initialize the analytics scheme selector."""
        super().__init__(uidd, device_data, api, "analytics_scheme")
        
        camera_name = device_data.get("name", f"Camera {uidd}")
        self._attr_name = f"{camera_name} Analytics Scheme"
        self._attr_icon = "mdi:brain"
        
        # Common analytics schemes based on VideLoft API data
        self._attr_options = [
            "videoloft",
            "lpr-night", 
            "people-lc",
            "motion-basic",
            "ai-detection",
            "custom"
        ]

    @property
    def current_option(self) -> Optional[str]:
        """Return the current analytics scheme."""
        current = self.device_data.get("analyticsScheme", "videoloft")
        return current if current in self.options else "videoloft"

    async def async_select_option(self, option: str) -> None:
        """Select new analytics scheme."""
        try:
            _LOGGER.info("Setting analytics scheme to %s for %s", option, self.uidd)
            # This would need API implementation
            # await self.api.set_analytics_scheme(self.uidd, option)
        except Exception as e:
            _LOGGER.error("Error setting analytics scheme for %s: %s", self.uidd, e)


class VideoloftVideoCodecSelect(VideoloftSelectBase):
    """Select entity for video codec (informational)."""

    def __init__(self, uidd: str, device_data: Dict[str, Any], api) -> None:
        """Initialize the video codec selector."""
        super().__init__(uidd, device_data, api, "video_codec")
        
        camera_name = device_data.get("name", f"Camera {uidd}")
        self._attr_name = f"{camera_name} Video Codec"
        self._attr_icon = "mdi:file-video"
        
        # Common video codecs
        self._attr_options = [
            "h264",
            "h265", 
            "mjpeg",
            "auto"
        ]

    @property
    def current_option(self) -> Optional[str]:
        """Return the current video codec."""
        current = self.device_data.get("videoCodec", "h264")
        return current if current in self.options else "h264"

    async def async_select_option(self, option: str) -> None:
        """Select new video codec."""
        try:
            _LOGGER.info("Setting video codec to %s for %s", option, self.uidd)
            # This would need API implementation
            # await self.api.set_video_codec(self.uidd, option)
        except Exception as e:
            _LOGGER.error("Error setting video codec for %s: %s", self.uidd, e)
