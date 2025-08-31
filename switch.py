"""Switch platform for VideLoft integration."""

import logging
from typing import Any, Dict, Optional

from homeassistant.components.switch import SwitchEntity
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
    """Set up VideLoft switches."""
    devices = hass.data[DOMAIN][entry.entry_id]["devices"]
    api = hass.data[DOMAIN][entry.entry_id]["api"]
    
    entities = []
    for device_data in devices:
        uidd = f"{device_data['uid']}.{device_data['id']}"
        capabilities = get_camera_capabilities(device_data)
        
        # Create capability-based switches
        if capabilities["ptz"]:
            entities.append(VideoloftPTZSwitch(uidd, device_data, api))
        
        if capabilities["talkback"]:
            entities.append(VideoloftTalkbackSwitch(uidd, device_data, api))
            
        if capabilities["rom"]:
            entities.append(VideoloftROMSwitch(uidd, device_data, api))
            
        # Always create recording control if supported
        if capabilities["cloud_recording"]:
            entities.append(VideoloftRecordingSwitch(uidd, device_data, api))
            
        # Analytics control
        if capabilities["analytics"]:
            entities.append(VideoloftAnalyticsSwitch(uidd, device_data, api))

    if entities:
        async_add_entities(entities)

# ----------------------------------------------------------
# SWITCH ENTITY CLASSES
# ----------------------------------------------------------


class VideoloftSwitchBase(SwitchEntity):
    """Base class for VideLoft switches."""

    def __init__(self, uidd: str, device_data: Dict[str, Any], api, switch_type: str) -> None:
        """Initialize the switch."""
        self.uidd = uidd
        self.device_data = device_data
        self.api = api
        self.switch_type = switch_type
        
        # Set up basic attributes
        self._attr_unique_id = f"videoloft_{switch_type}_{uidd}"
        self._attr_device_info = create_device_info(uidd, device_data)
        self._attr_entity_category = EntityCategory.CONFIG

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return extra state attributes."""
        return {
            "device_id": self.uidd,
            "switch_type": self.switch_type,
        }

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on."""
        # Base implementation - override in subclasses
        _LOGGER.info("Turning on %s for %s", self.switch_type, self.uidd)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        # Base implementation - override in subclasses
        _LOGGER.info("Turning off %s for %s", self.switch_type, self.uidd)


class VideoloftPTZSwitch(VideoloftSwitchBase):
    """Switch for PTZ control."""

    def __init__(self, uidd: str, device_data: Dict[str, Any], api) -> None:
        """Initialize the PTZ switch."""
        super().__init__(uidd, device_data, api, "ptz_control")
        
        camera_name = device_data.get("name", f"Camera {uidd}")
        self._attr_name = f"{camera_name} PTZ Control"
        self._attr_icon = "mdi:pan"

    @property
    def is_on(self) -> bool:
        """Return True if PTZ is enabled."""
        return bool(self.device_data.get("ptzEnabled", 0))

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable PTZ control."""
        try:
            # This would need API implementation
            _LOGGER.info("PTZ control enabled for %s", self.uidd)
            # await self.api.enable_ptz(self.uidd)
        except Exception as e:
            _LOGGER.error("Error enabling PTZ for %s: %s", self.uidd, e)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable PTZ control."""
        try:
            # This would need API implementation
            _LOGGER.info("PTZ control disabled for %s", self.uidd)
            # await self.api.disable_ptz(self.uidd)
        except Exception as e:
            _LOGGER.error("Error disabling PTZ for %s: %s", self.uidd, e)


class VideoloftTalkbackSwitch(VideoloftSwitchBase):
    """Switch for talkback control."""

    def __init__(self, uidd: str, device_data: Dict[str, Any], api) -> None:
        """Initialize the talkback switch."""
        super().__init__(uidd, device_data, api, "talkback")
        
        camera_name = device_data.get("name", f"Camera {uidd}")
        self._attr_name = f"{camera_name} Talkback"
        self._attr_icon = "mdi:microphone"

    @property
    def is_on(self) -> bool:
        """Return True if talkback is enabled."""
        return bool(self.device_data.get("talkbackEnabled", 0))


class VideoloftROMSwitch(VideoloftSwitchBase):
    """Switch for ROM feature control."""

    def __init__(self, uidd: str, device_data: Dict[str, Any], api) -> None:
        """Initialize the ROM switch."""
        super().__init__(uidd, device_data, api, "rom")
        
        camera_name = device_data.get("name", f"Camera {uidd}")
        self._attr_name = f"{camera_name} ROM Feature"
        self._attr_icon = "mdi:memory"

    @property
    def is_on(self) -> bool:
        """Return True if ROM is enabled."""
        return bool(self.device_data.get("romEnabled", 0))


class VideoloftRecordingSwitch(VideoloftSwitchBase):
    """Switch for cloud recording control."""

    def __init__(self, uidd: str, device_data: Dict[str, Any], api) -> None:
        """Initialize the recording switch."""
        super().__init__(uidd, device_data, api, "cloud_recording")
        
        camera_name = device_data.get("name", f"Camera {uidd}")
        self._attr_name = f"{camera_name} Cloud Recording"
        self._attr_icon = "mdi:cloud-upload"

    @property
    def is_on(self) -> bool:
        """Return True if cloud recording is enabled."""
        return bool(self.device_data.get("cloudRecordingEnabled", 0))


class VideoloftAnalyticsSwitch(VideoloftSwitchBase):
    """Switch for analytics control."""

    def __init__(self, uidd: str, device_data: Dict[str, Any], api) -> None:
        """Initialize the analytics switch."""
        super().__init__(uidd, device_data, api, "analytics")
        
        camera_name = device_data.get("name", f"Camera {uidd}")
        self._attr_name = f"{camera_name} Analytics"
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
            "analytics_scheme": self.device_data.get("analyticsScheme", "Unknown"),
        })
        return attrs
