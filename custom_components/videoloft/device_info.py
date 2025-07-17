"""Device information helpers for VideLoft integration."""

from typing import Dict, Any, Set, Tuple, Optional
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC

from .const import DOMAIN

# ----------------------------------------------------------
# DEVICE INFO CREATION
# ----------------------------------------------------------


def create_device_info(uidd: str, device_data: Dict[str, Any]) -> DeviceInfo:
    """Create device info for VideLoft camera."""
    name = device_data.get("name", device_data.get("phonename", f"Camera {uidd}"))
    
    # Create connections set
    connections: Set[Tuple[str, str]] = set()
    if mac_address := device_data.get("macAddress"):
        connections.add((CONNECTION_NETWORK_MAC, mac_address))
    
    # Create configuration URL 
    config_url = None
    if logger := device_data.get("logger"):
        config_url = f"https://{logger}"
    
    # Get model information
    model = device_data.get("model", "Unknown Model")
    
    return DeviceInfo(
        identifiers={(DOMAIN, uidd)},
        name=name,
        manufacturer="VideLoft",
        model=model,
        sw_version=device_data.get("cloudAdapterVersion"),
        hw_version=device_data.get("recordingResolution"),  # Use resolution as hw version
        serial_number=device_data.get("cameraId", device_data.get("macAddress", uidd)),
        configuration_url=config_url,
        connections=connections,
        suggested_area=_suggest_area_from_tags(device_data.get("tags", [])),
    )

# ----------------------------------------------------------
# DEVICE CAPABILITY UTILITIES
# ----------------------------------------------------------


def _suggest_area_from_tags(tags: list) -> Optional[str]:
    """Suggest an area based on camera tags."""
    if not tags:
        return None
    
    # Common area mappings
    area_keywords = {
        "inside": "Inside",
        "indoor": "Inside", 
        "outside": "Outside",
        "outdoor": "Outside",
        "front": "Front",
        "back": "Back",
        "garden": "Garden",
        "driveway": "Driveway",
        "garage": "Garage",
        "kitchen": "Kitchen",
        "living": "Living Room",
        "bedroom": "Bedroom",
        "office": "Office",
        "hallway": "Hallway",
        "hall": "Hallway",
        "entrance": "Entrance",
    }
    
    # Look for area keywords in tags
    for tag in tags:
        tag_lower = tag.lower()
        for keyword, area in area_keywords.items():
            if keyword in tag_lower:
                return area
    
    # Return first tag if no specific area found
    return tags[0] if tags else None


def get_camera_capabilities(device_data: Dict[str, Any]) -> Dict[str, bool]:
    """Extract camera capabilities from device data."""
    return {
        "ptz": bool(device_data.get("ptzEnabled", 0)),
        "talkback": bool(device_data.get("talkbackEnabled", 0)),
        "audio": bool(device_data.get("audioEnabled", 0)),
        "rom": bool(device_data.get("romEnabled", 0)),
        "analytics": bool(device_data.get("analyticsEnabled", 0)),
        "cloud_recording": bool(device_data.get("cloudRecordingEnabled", 0)),
        "mainstream_live": bool(device_data.get("mainstreamLive", 0)),
    }

# ----------------------------------------------------------
# TECHNICAL SPECIFICATIONS
# ----------------------------------------------------------


def get_technical_specs(device_data: Dict[str, Any]) -> Dict[str, Any]:
    """Extract technical specifications from device data."""
    return {
        "recording_resolution": device_data.get("recordingResolution", "Unknown"),
        "video_codec": device_data.get("videoCodec", "Unknown"),
        "analytics_scheme": device_data.get("analyticsScheme", "Unknown"),
        "timezone": device_data.get("timeZoneName", "Unknown"),
        "cloud_adapter_version": device_data.get("cloudAdapterVersion", "Unknown"),
        "model": device_data.get("model", "Unknown"),
    }


def get_network_info(device_data: Dict[str, Any]) -> Dict[str, Any]:
    """Extract network information from device data."""
    return {
        "logger_server": device_data.get("logger", ""),
        "wowza_server": device_data.get("wowza", ""),
        "recorded_stream_name": device_data.get("recordedStreamName", ""),
        "local_live_id": device_data.get("localLiveId", ""),
        "local_live_hosts": device_data.get("localLiveHosts", []),
        "mac_address": device_data.get("macAddress", ""),
        "camera_id": device_data.get("cameraId", ""),
        "cloud_adapter_id": device_data.get("cloudAdapterId", ""),
    }
