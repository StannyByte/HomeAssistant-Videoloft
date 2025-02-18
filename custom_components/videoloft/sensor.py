# sensor.py

"""Sensor platform for the Videoloft integration."""
from __future__ import annotations

import logging
from datetime import timedelta, datetime, timezone
from typing import Any, Dict, List, Optional
import asyncio
import json
import openai
import aiohttp

from homeassistant.helpers.storage import Store
from homeassistant.components.sensor import SensorEntity
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

from .api import VideoloftAPI
from .const import (
    DOMAIN,
    ICON_CAMERA,
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


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Videoloft sensors based on a config entry."""
    api: VideoloftAPI = hass.data[DOMAIN][entry.entry_id]["api"]
    devices: Dict[str, Any] = hass.data[DOMAIN][entry.entry_id]["devices"]

    # Set up DataUpdateCoordinator for Camera Status Sensors
    async def async_update_status_data():
        """Fetch updated device info from the Videoloft API."""
        try:
            device_info = await api.get_device_info()
            if not device_info or "result" not in device_info:
                raise UpdateFailed("Invalid device information received.")
            return device_info
        except Exception as e:
            _LOGGER.error(f"Error fetching device info: {e}")
            raise UpdateFailed(f"Error fetching device info: {e}")

    status_coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name="videoloft_status_sensors",
        update_method=async_update_status_data,
        update_interval=timedelta(minutes=5),
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
    for owner_uid, owner_data in status_coordinator.data.get("result", {}).items():
        for device_uid, device_data in owner_data.get("devices", {}).items():
            uidd = f"{owner_uid}.{device_uid}"
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
            camera_uids = set(trigger["uidd"] for trigger in lpr_triggers if "uidd" in trigger)
            if not camera_uids:
                _LOGGER.info("No camera UIDs found in LPR triggers.")
                self.matched_event = None
                return

            # Track the last processed event time and IDs
            last_event_time = self.hass.data[DOMAIN][self.entry.entry_id].get("last_event_time", None)
            processed_event_ids = self.hass.data[DOMAIN][self.entry.entry_id].get("processed_event_ids", set())

            for uidd in camera_uids:
                owner_uid, device_uid = uidd.split('.')
                device_data = (
                    self.hass.data[DOMAIN][self.entry.entry_id].get("devices", {})
                    .get("result", {})
                    .get(owner_uid, {})
                    .get("devices", {})
                    .get(device_uid, {})
                )
                logger_server = device_data.get("logger")
                if not logger_server:
                    _LOGGER.warning(f"Logger server not found for camera {uidd}")
                    continue

                try:
                    # Fetch the most recent event starting from last known time
                    latest_event = await api.get_latest_event(logger_server, uidd, last_event_time)
                    if not latest_event:
                        _LOGGER.info(f"No new events for camera {uidd}")
                        continue

                    event_id = latest_event.get("alert")
                    event_start_time = latest_event.get("startt")
                    if not event_id or not event_start_time:
                        continue

                    # Check if the event has already been processed
                    if event_id in processed_event_ids:
                        _LOGGER.info(f"Event {event_id} has already been processed. Skipping.")
                        continue

                    # Store the new event ID and update last event time to prevent reprocessing
                    processed_event_ids.add(event_id)
                    self.hass.data[DOMAIN][self.entry.entry_id]["processed_event_ids"] = processed_event_ids
                    self.hass.data[DOMAIN][self.entry.entry_id]["last_event_time"] = event_start_time

                    # Poll the most recent event continuously for up to 60 seconds for LPR data
                    _LOGGER.info(f"New event {event_id} detected. Polling for LPR data every 5 seconds (timeout: 60s). 🚀")
                    max_wait = 60  # seconds
                    poll_interval = 5  # seconds between checks
                    lpr_event_data = None
                    start_poll = datetime.now().timestamp()  # record polling start time
                    while (datetime.now().timestamp() - start_poll) < max_wait:
                        lpr_event_data = await api.get_event_vehicle_analytics(logger_server, uidd, event_id)
                        if lpr_event_data and isinstance(lpr_event_data, list) and len(lpr_event_data) > 0:
                            _LOGGER.info(f"LPR data found for event {event_id} after polling. ✅")
                            break
                        _LOGGER.debug(f"No LPR data yet for event {event_id}. Retrying in {poll_interval} seconds.")
                        await asyncio.sleep(poll_interval)
                    if not lpr_event_data:
                        _LOGGER.info(f"No LPR data found for event {event_id} after 60 seconds. Backing off. ⏱️")
                        continue  # Skip further processing of this event

                    if not isinstance(lpr_event_data, list) or len(lpr_event_data) == 0:
                        _LOGGER.info("No vehicle details found in this event. Skipping.")
                        continue

                    _LOGGER.info(f"Vehicle analytics data: {json.dumps(lpr_event_data, indent=2)}")
                    lpr_info = api.parse_lpr_data(lpr_event_data)

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
                                self.matched_event = {
                                    "license_plate": vehicle_data.get("license_plate", ""),
                                    "make": vehicle_data.get("make", ""),
                                    "model": vehicle_data.get("model", ""),
                                    "color": vehicle_data.get("color", ""),
                                    "timestamp": vehicle_data.get("timestamp"),
                                    "alertid": vehicle_data.get("alertid"),
                                    "direction": vehicle_data.get("direction", "unknown")
                                }
                                self.async_set_updated_data(self.matched_event)
                                _LOGGER.info(f"Match found with trigger: {trigger}")

                                # Cancel any existing clear task
                                if self._clear_task and not self._clear_task.done():
                                    self._clear_task.cancel()
                                    try:
                                        await self._clear_task
                                    except asyncio.CancelledError:
                                        pass  # Expected when canceling

                                # Schedule a new clear task
                                self._clear_task = self.hass.loop.create_task(self.clear_matched_event(delay=10))
                                break  # Exit trigger loop after match

                except Exception as e:
                    _LOGGER.error(f"Error processing camera {uidd}: {e}")
                    continue

        except Exception as e:
            _LOGGER.error(f"Error in LPR update: {e}")
            self.matched_event = None
            import traceback
            _LOGGER.error(f"Traceback: {traceback.format_exc()}")

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
        for owner_uid, owner_data in self.coordinator.data.get("result", {}).items():
            for device_uid, device_data in owner_data.get("devices", {}).items():
                uidd = f"{owner_uid}.{device_uid}"
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