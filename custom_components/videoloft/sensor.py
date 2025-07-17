# sensor.py

"""Sensor platform for the Videoloft integration."""
from __future__ import annotations

import logging
from datetime import timedelta, datetime, timezone
from typing import Any, Dict, List, Optional
import asyncio
import json
import aiohttp

from homeassistant.helpers.storage import Store
from homeassistant.components.binary_sensor import BinarySensorEntity, BinarySensorDeviceClass
from homeassistant.components.sensor import SensorEntity, SensorDeviceClass, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
    UpdateFailed,
)
from homeassistant.helpers import storage
from homeassistant.util import dt as dt_util

from .api import VideoloftAPI
from .const import (
    DOMAIN,
    ICON_CAMERA,
    ATTR_CLOUD_ADAPTER_VERSION,
    ATTR_MAINSTREAM_LIVE,
    ATTR_CLOUD_RECORDING_ENABLED,
    ATTR_LAST_LOGGER,
    CONNECTIVITY_UPDATE_INTERVAL,
    FIRMWARE_UPDATE_INTERVAL,
    STATUS_UPDATE_INTERVAL,
    ATTR_LICENSE_PLATE,
    ATTR_MAKE,
    ATTR_MODEL,
    ATTR_COLOR,
    ATTR_TIMESTAMP,
    ATTR_ALERTID,
    ATTR_RECORDING_URL,
    DEFAULT_POLL_INTERVAL,
    LOOKBACK_PERIOD_HOURS,
    LPR_TRIGGER_STORAGE_KEY,
    LPR_STORAGE_VERSION,
    LPR_STORAGE_KEY,
)

_LOGGER = logging.getLogger(__name__)

# ----------------------------------------------------------
# PLATFORM SETUP
# ----------------------------------------------------------


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Videoloft sensors based on a config entry."""
    _LOGGER.debug("Setting up Videoloft sensors for entry %s", entry.entry_id)
    
    # Ensure domain data exists
    if DOMAIN not in hass.data:
        hass.data[DOMAIN] = {}
        
    if entry.entry_id not in hass.data[DOMAIN]:
        _LOGGER.error("Entry data not found for %s", entry.entry_id)
        return
        
    api: VideoloftAPI = hass.data[DOMAIN][entry.entry_id]["api"]
    devices: Dict[str, Any] = hass.data[DOMAIN][entry.entry_id]["devices"]

    # Set up DataUpdateCoordinator for Camera Status Sensors
    async def async_update_status_data():
        """Fetch updated device info from the Videoloft API."""
        try:
            cameras_info = await api.get_cameras_info()
            if not cameras_info: # Now expects a list, not a dict with "result"
                raise UpdateFailed("Invalid camera information received.")
            return cameras_info
        except Exception as e:
            _LOGGER.error(f"Error fetching camera info: {e}")
            raise UpdateFailed(f"Error fetching camera info: {e}")

    status_coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name="videoloft_status_sensors",
        update_method=async_update_status_data,
        update_interval=timedelta(hours=1),  # Reduced from 5 minutes to 1 hour
    )

    # Set up DataUpdateCoordinator for LPR Sensors
    lpr_coordinator = LPRUpdateCoordinator(hass, entry)

    # Fetch initial data for both coordinators
    await status_coordinator.async_config_entry_first_refresh()
    await lpr_coordinator.async_config_entry_first_refresh()

    # Initialize sensor entities
    status_entities = []
    lpr_entities = []

    # Create Status Sensors for each camera
    # Iterate directly over the list of camera objects
    for device_data in status_coordinator.data:
        uidd = f"{device_data['uid']}.{device_data['id']}"
        status_sensor = VideoloftStatusSensor(status_coordinator, uidd, device_data)
        status_entities.append(status_sensor)

    # Create LPR Sensors (one per integration entry)
    lpr_sensor = VideoloftLPRSensor(lpr_coordinator, entry)
    lpr_entities.append(lpr_sensor)

    # Add all sensors to Home Assistant
    async_add_entities(status_entities + lpr_entities)


class LPRUpdateCoordinator(DataUpdateCoordinator):
    """Coordinator to manage LPR data updates."""
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry):
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name="Videoloft LPR Sensor",
            update_method=self.async_update_lpr,
            update_interval=timedelta(seconds=DEFAULT_POLL_INTERVAL),
        )
        self.entry = entry
        self.matched_event: Optional[Dict[str, Any]] = None
        self._clear_task: Optional[asyncio.Task] = None  # Initialize the clear task
        self._processed_vehicle_ids: List[str] = []
        self._store = storage.Store(
            hass,
            LPR_STORAGE_VERSION,
            f"{DOMAIN}_{LPR_STORAGE_KEY}_{entry.entry_id}"
        )
        
    async def async_load_triggers(self):
        """Load triggers from persistent storage."""
        data = await self._store.async_load()
        if data:
            self.hass.data[DOMAIN][self.entry.entry_id]["lpr_triggers"] = data
        return data or []

    async def async_save_triggers(self, triggers):
        """Save triggers to persistent storage."""
        await self._store.async_save(triggers)
        self.hass.data[DOMAIN][self.entry.entry_id]["lpr_triggers"] = triggers

    def _generate_lpr_recording_url(self, license_plate: str, timestamp: int, camera_uidd: str) -> str:
        """Generate the recording URL for LPR detection notifications."""
        try:
            # Sanitize license plate for URL (remove spaces, convert to lowercase)
            clean_plate = license_plate.strip().lower() if license_plate else "unknown"
            
            # Remove any potentially problematic characters from license plate
            import re
            clean_plate = re.sub(r'[^a-z0-9]', '', clean_plate) if clean_plate != "unknown" else "unknown"
            
            # Ensure timestamp is valid
            valid_timestamp = timestamp if timestamp and timestamp > 0 else 0
            
            # Ensure camera UIDD is valid
            valid_uidd = camera_uidd if camera_uidd else "unknown"
            
            # Generate URL in the expected format
            recording_url = f"https://app.videoloft.com/vehicles/{clean_plate}?time={valid_timestamp}&uidd={valid_uidd}"
            
            _LOGGER.info(f"Generated LPR recording URL for plate '{license_plate}': {recording_url}")
            return recording_url
            
        except Exception as e:
            _LOGGER.error(f"Error generating LPR recording URL: {e}")
            # Return a fallback URL with unknown values
            return f"https://app.videoloft.com/vehicles/unknown?time=0&uidd=unknown"

    async def clear_matched_event(self, delay: int = 20):
        """Clear matched event after delay seconds."""
        await asyncio.sleep(delay)
        self.matched_event = None
        self.async_set_updated_data(self.matched_event)  # Update the sensor
        _LOGGER.debug("Cleared matched event state after delay")

    async def async_update_lpr(self):
        """Fetch LPR events and check against triggers."""
        try:
            _LOGGER.info("Starting Videoloft vehicle event monitoring.")
            api: VideoloftAPI = self.hass.data[DOMAIN][self.entry.entry_id]["api"]

            # Get LPR triggers
            lpr_triggers = self.hass.data[DOMAIN][self.entry.entry_id].get(
                LPR_TRIGGER_STORAGE_KEY, []
            )
            if not lpr_triggers:
                _LOGGER.info("No LPR triggers defined.")
                self.matched_event = None
                return

            # Get all unique camera UIDs from triggers
            camera_uids = list(set(trigger["uidd"] for trigger in lpr_triggers if "uidd" in trigger))
            if not camera_uids:
                _LOGGER.info("No camera UIDs found in LPR triggers.")
                self.matched_event = None
                return

            # Calculate start time for the last 5 minutes
            start_time_ms = int((datetime.now() - timedelta(minutes=5)).timestamp() * 1000)

            # Fetch vehicle detections directly
            lpr_event_data = await api.get_vehicle_detections(camera_uids, start_time_ms, limit=10)

            _LOGGER.info(f"Raw vehicle detections received: {json.dumps(lpr_event_data, indent=2)}")

            if not lpr_event_data:
                _LOGGER.info("No new vehicle detections found.")
                self.matched_event = None
                return

            # Process each detection
            for detection in lpr_event_data:
                vehicle_id = detection.get("vehicleId")
                if vehicle_id and vehicle_id in self._processed_vehicle_ids:
                    _LOGGER.info(f"Skipping already processed vehicle ID: {vehicle_id}")
                    continue
                lpr_info = api.parse_lpr_data([detection])  # parse_lpr_data expects a list

                if lpr_info:
                    _LOGGER.info(f"Vehicle event detected: {lpr_info}")
                    # Process matches...
                    for trigger in lpr_triggers:
                        vehicle_data = lpr_info
                        matches = False  # Reset matches for each trigger

                        def normalize(value):
                            return value.strip().lower() if isinstance(value, str) else value

                        # Check license plate
                        if trigger.get("license_plate"):
                            if normalize(trigger["license_plate"]) == normalize(vehicle_data.get("license_plate", "")):
                                matches = True

                        # If no license plate match, check make, model, and color
                        if not matches:
                            make_trigger = normalize(trigger.get("make", ""))
                            model_trigger = normalize(trigger.get("model", ""))
                            color_trigger = normalize(trigger.get("color", ""))
                            if make_trigger and model_trigger and color_trigger:
                                if (make_trigger == normalize(vehicle_data.get("make", "")) and
                                    model_trigger == normalize(vehicle_data.get("model", "")) and
                                    color_trigger == normalize(vehicle_data.get("color", ""))):
                                    matches = True

                        if matches:
                            # Generate the recording URL using detection data
                            recording_url = self._generate_lpr_recording_url(
                                license_plate=vehicle_data.get("license_plate", ""),
                                timestamp=vehicle_data.get("timestamp", 0),
                                camera_uidd=trigger["uidd"]
                            )
                            
                            # Store the matched event details
                            self.matched_event = {
                                "license_plate": vehicle_data.get("license_plate", ""),
                                "make": vehicle_data.get("make", ""),
                                "model": vehicle_data.get("model", ""),
                                "color": vehicle_data.get("color", ""),
                                "timestamp": vehicle_data.get("timestamp"),
                                "alertid": vehicle_data.get("alertid"),
                                "direction": vehicle_data.get("direction", "unknown"),
                                "recording_url": recording_url
                            }
                            self.async_set_updated_data(self.matched_event)
                            _LOGGER.info(f"LPR trigger match found! Trigger: {trigger}")
                            _LOGGER.info(f"Generated notification with URL: {recording_url}")

                            # Fetch and save the LPR event thumbnail
                            if detection.get("uid") and detection.get("deviceId") and detection.get("stillTimeMs") and detection.get("vehicleId"):
                                thumbnail_image = await api.get_lpr_event_thumbnail(
                                    str(detection["uid"]),
                                    str(detection["deviceId"]),
                                    str(detection["stillTimeMs"]),
                                    str(detection["vehicleId"])
                                )
                                if thumbnail_image:
                                    thumbnail_filename = "/config/www/lpr.jpg"
                                    with open(thumbnail_filename, "wb") as f:
                                        f.write(thumbnail_image)
                                    _LOGGER.info(f"LPR event thumbnail saved to {thumbnail_filename}")
                                    self.matched_event["lpr_thumbnail_path"] = thumbnail_filename
                                else:
                                    _LOGGER.error(f"Failed to fetch LPR event thumbnail for event {detection.get('eventId')}")
                            else:
                                _LOGGER.error(f"Missing data required to fetch LPR event thumbnail for event {detection.get('eventId')}")

                            # Cancel any existing clear task and schedule clearing of the matched event state
                            if self._clear_task and not self._clear_task.done():
                                self._clear_task.cancel()
                                try:
                                    await self._clear_task
                                except asyncio.CancelledError:
                                    pass  # Expected when canceling
                            self._clear_task = self.hass.loop.create_task(self.clear_matched_event(delay=10))

                            # Add vehicleId to processed list and limit size
                            if vehicle_id:
                                self._processed_vehicle_ids.append(vehicle_id)
                                if len(self._processed_vehicle_ids) > 100:
                                    self._processed_vehicle_ids.pop(0)

                            break  # Exit trigger loop after match

            # If no match found after processing all detections, clear the matched event
            if not self.matched_event:
                self.matched_event = None
                self.async_set_updated_data(self.matched_event)

        except Exception as e:
            _LOGGER.error(f"Error in LPR update: {e}")
            self.matched_event = None
            import traceback
            _LOGGER.error(f"Traceback: {traceback.format_exc()}")

    async def async_cleanup(self):
        """Clean up coordinator resources."""
        try:
            _LOGGER.debug("Cleaning up LPR coordinator...")
            
            # Cancel any running clear task
            if self._clear_task and not self._clear_task.done():
                self._clear_task.cancel()
                try:
                    await self._clear_task
                except asyncio.CancelledError:
                    pass
                    
            # Clear state
            self.matched_event = None
            self._processed_vehicle_ids = []
            
            _LOGGER.debug("LPR coordinator cleanup completed")
            
        except Exception as e:
            _LOGGER.error("Error during LPR coordinator cleanup: %s", e)

# ----------------------------------------------------------
# SENSOR ENTITY CLASSES
# ----------------------------------------------------------

class VideoloftStatusSensor(CoordinatorEntity, SensorEntity):
    """Representation of a Videoloft status sensor."""

    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        uidd: str,
        device_data: Dict[str, Any],
    ) -> None:
        """Initialize the status sensor."""
        super().__init__(coordinator)
        self.uidd = uidd
        self.device_data = device_data
        self._attr_name = f"{device_data.get('phonename', 'Camera')} Status"
        self._attr_unique_id = f"videoloft_status_{uidd}"
        self._attr_icon = ICON_CAMERA
        self.stream_start_time: Optional[datetime] = None  # Track the start time of the stream

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, uidd)},
            name=device_data.get("phonename", f"Camera {uidd}"),
            manufacturer="Videoloft",
            model=device_data.get("model"),
            sw_version=device_data.get("appVersion"),
        )

    @property
    def native_value(self) -> str | None:
        """Return the current state of the sensor as online."""
        return "online"

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return additional attributes for the sensor."""
        attributes = {
            "model": self.device_data.get("model"),
            "resolution": self.device_data.get("recordingResolution"),
            "mac_address": self.device_data.get("macAddress"),
            "cloud_recording": self.device_data.get("cloudRecordingEnabled"),
            "ptz_capabilities": self.device_data.get("ptzEnabled"),
            "audio_enabled": self.device_data.get("audioEnabled"),
            "analytics_enabled": self.device_data.get("analyticsEnabled"),
        }
        if self.device_data.get("status") == "online" and self.stream_start_time:
            attributes["uptime"] = self.calculate_uptime()
        return attributes

    def calculate_uptime(self) -> str:
        """Calculate how long the stream has been live."""
        if self.stream_start_time:
            delta = datetime.now() - self.stream_start_time
            return str(delta).split(".")[0]  # Remove microseconds
        return "unknown"

    @property
    def should_poll(self) -> bool:
        """Disable polling, updates are controlled via the coordinator."""
        return False

    async def async_update(self):
        """Update the sensor data."""
        await self.coordinator.async_request_refresh()
        # Update device_data with the latest information
        # Iterate directly over the list of camera objects
        for device_data in self.coordinator.data:
            uidd = f"{device_data['uid']}.{device_data['id']}"
            if uidd == self.uidd:
                self.device_data = device_data
                break


class VideoloftLPRSensor(CoordinatorEntity, SensorEntity):
    """Sensor to represent matched LPR events."""
    def __init__(self, coordinator: LPRUpdateCoordinator, entry: ConfigEntry):
        """Initialize the LPR sensor."""
        super().__init__(coordinator)
        self.coordinator = coordinator
        self.entry = entry
        self._attr_name = "Videoloft LPR Matched Event"
        self._attr_unique_id = f"videoloft_lpr_matched_event_{entry.entry_id}"
        self._attr_icon = "mdi:license"
        self._attr_device_class = "timestamp"

    @property
    def native_value(self) -> datetime | None:
        """Return the state of the sensor as a timezone-aware datetime."""
        if self.coordinator.matched_event and self.coordinator.matched_event.get(ATTR_TIMESTAMP):
            # Convert milliseconds timestamp to seconds and create timezone-aware datetime
            timestamp_ms = self.coordinator.matched_event[ATTR_TIMESTAMP]
            try:
                return datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)
            except (ValueError, TypeError, OverflowError) as err:
                _LOGGER.error(f"Error converting timestamp {timestamp_ms}: {err}")
                return None
        return None

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return additional attributes."""
        if self.coordinator.matched_event:
            return {
                ATTR_LICENSE_PLATE: self.coordinator.matched_event.get(ATTR_LICENSE_PLATE),
                ATTR_MAKE: self.coordinator.matched_event.get(ATTR_MAKE),
                ATTR_MODEL: self.coordinator.matched_event.get(ATTR_MODEL),
                ATTR_COLOR: self.coordinator.matched_event.get(ATTR_COLOR),
                ATTR_ALERTID: self.coordinator.matched_event.get(ATTR_ALERTID),
                ATTR_RECORDING_URL: self.coordinator.matched_event.get(ATTR_RECORDING_URL)
            }
        return {}

    async def async_will_remove_from_hass(self) -> None:
        """Called when entity will be removed from hass."""
        _LOGGER.debug("Cleaning up LPR sensor entity")
        
        # Clean up coordinator if it has cleanup method
        if hasattr(self.coordinator, 'async_cleanup'):
            try:
                await self.coordinator.async_cleanup()
            except Exception as e:
                _LOGGER.debug("Error during LPR sensor cleanup: %s", e)