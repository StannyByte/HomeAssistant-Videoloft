# coordinator.py

from __future__ import annotations

import logging
from typing import List, Dict, Any, Optional
import asyncio
import base64
from datetime import datetime, timedelta
import aiohttp

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers import storage

from .const import (
    DOMAIN,
    LPR_STORAGE_VERSION,
    LPR_STORAGE_KEY,
)

_LOGGER = logging.getLogger(__name__)

class VideoloftCoordinator:
    """Class to manage Videoloft triggers and state."""
    
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the coordinator."""
        self.hass = hass
        self.entry = entry
        self.api = hass.data[DOMAIN][entry.entry_id]["api"]  # Add API reference
        self._store = storage.Store(
            hass,
            LPR_STORAGE_VERSION,
            f"{DOMAIN}_{LPR_STORAGE_KEY}_{entry.entry_id}"
        )
        self._triggers: List[Dict[str, Any]] = []
        self._descriptions: Dict[str, Any] = {}
        _LOGGER.debug("Initialized VideoloftCoordinator")

    async def async_setup(self) -> bool:
        """Set up the coordinator."""
        try:
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
            
            _LOGGER.debug("Coordinator setup complete")
            return True
            
        except Exception as e:
            _LOGGER.error("Failed to setup coordinator: %s", e, exc_info=True)
            return False

    async def async_load_triggers(self) -> List[Dict[str, Any]]:
        """Load triggers from storage."""
        return self._triggers

    async def async_save_triggers(self, triggers: List[Dict[str, Any]]) -> None:
        """Save triggers to storage."""
        await self._store.async_save(triggers)
        self._triggers = triggers
        self.hass.data[DOMAIN][self.entry.entry_id]["lpr_triggers"] = triggers

    async def process_events(self, api_key: str, selected_cameras: List[str]) -> None:
        """Process events for selected cameras."""
        # Get the sensor from the existing entities instead of creating new one
        for entity in self.hass.data[DOMAIN][self.entry.entry_id].get("entities", []):
            if isinstance(entity, "VideoloftLPRSensor"):
                await entity.process_events(api_key, selected_cameras)
                return

    async def process_ai_search(self, selected_cameras: List[str]) -> None:
        """Process events and get descriptions from Google Gemini, with improved prompt, rate limiting, and daytime filtering."""
        import pytz
        api_key = self.hass.data[DOMAIN].get("gemini_api_key")
        if not api_key:
            _LOGGER.error("Google Gemini API key not set.")
            return

        descriptions = await self.async_load_descriptions()
        events_processed = 0
        RATE_LIMIT = 15  # Gemini allows 15/min for safety
        WINDOW_SECONDS = 60
        now = datetime.utcnow()
        # Only process events from last 5 days, 6am-8pm local time
        start_time = int((now - timedelta(days=5)).replace(hour=0, minute=0, second=0, microsecond=0).timestamp() * 1000)
        end_time = int(now.timestamp() * 1000)

        # For rate limiting
        call_times = []

        # Use local timezone if available, else UTC
        try:
            local_tz = pytz.timezone(self.hass.config.time_zone)
        except Exception:
            local_tz = pytz.UTC

        for camera_uidd in selected_cameras:
            try:
                logger_server = await self.api.get_logger_server(camera_uidd)
                if not logger_server:
                    _LOGGER.error(f"Could not get logger server for camera {camera_uidd}")
                    continue

                events = await self.api.get_recent_events_paginated(
                    logger_server, camera_uidd, start_time, end_time
                )

                if not events:
                    _LOGGER.warning(f"No events found for camera {camera_uidd}")
                    continue

                _LOGGER.info(f"Processing {len(events)} events for camera {camera_uidd}")

                # Filter and batch events
                filtered_events = []
                for event in events:
                    event_id = event.get("alert")
                    if not event_id or event_id in descriptions:
                        continue
                    event_ts = event.get('startt')
                    if not event_ts:
                        continue
                    dt_utc = datetime.utcfromtimestamp(event_ts / 1000).replace(tzinfo=pytz.UTC)
                    dt_local = dt_utc.astimezone(local_tz)
                    if not (6 <= dt_local.hour < 20):
                        continue
                    filtered_events.append(event)

                # Process in batches of RATE_LIMIT (fetch 15, send 1 at a time, wait for all, then wait for the minute)
                for i in range(0, len(filtered_events), RATE_LIMIT):
                    batch = filtered_events[i:i+RATE_LIMIT]
                    batch_start = datetime.utcnow()
                    _LOGGER.info(f"Processing batch {i//RATE_LIMIT+1} ({len(batch)} events) for camera {camera_uidd}")

                    # Step 1: Fetch all thumbnails for the batch (sequentially, to avoid overloading the logger server)
                    thumbnails = []
                    for event in batch:
                        event_id = event.get("alert")
                        image_data = await self.api.download_event_thumbnail(
                            logger_server, camera_uidd, event_id
                        )
                        thumbnails.append((event, event_id, image_data))

                    # Step 2: For each event, send Gemini API call (sequentially, but gather all tasks)
                    async def gemini_task(event, event_id, image_data):
                        if not image_data:
                            _LOGGER.warning(f"No thumbnail available for event {event_id}")
                            return event, event_id, None
                        description = await self.get_gemini_description(image_data, api_key)
                        # Remove unwanted leading phrase if present (robust, trims any variant)
                        if description:
                            desc = description.strip()
                            # Remove all known variants and extra whitespace/colons
                            for prefix in [
                                "here's a description of the surveillance image:",
                                "here is a description of the surveillance image:",
                                "description of the surveillance image:",
                                "here's a description of the surveillance image",
                                "here is a description of the surveillance image",
                                "description of the surveillance image"
                            ]:
                                if desc.lower().startswith(prefix):
                                    desc = desc[len(prefix):].lstrip(' .:').strip()
                            description = desc
                        return event, event_id, description

                    gemini_tasks = [gemini_task(event, event_id, image_data) for event, event_id, image_data in thumbnails]
                    results = await asyncio.gather(*gemini_tasks)
                    for event, event_id, description in results:
                        if event_id and description:
                            _LOGGER.debug(f"Description for event {event_id}: {description}")
                            descriptions[event_id] = {
                                'description': description,
                                'uidd': camera_uidd,
                                'logger_server': logger_server,
                                'startt': event.get('startt')
                            }
                            events_processed += 1
                            await self.async_save_descriptions(descriptions)
                            _LOGGER.info(f"Saved description for event {event_id}")
                        elif event_id:
                            _LOGGER.warning(f"No description generated for event {event_id}")

                    # Wait for the remainder of the minute if needed
                    batch_elapsed = (datetime.utcnow() - batch_start).total_seconds()
                    if batch_elapsed < WINDOW_SECONDS and i + RATE_LIMIT < len(filtered_events):
                        sleep_time = WINDOW_SECONDS - batch_elapsed + 0.1
                        _LOGGER.info(f"Batch complete, sleeping {sleep_time:.1f}s to respect Gemini rate limit")
                        await asyncio.sleep(sleep_time)

            except Exception as e:
                _LOGGER.exception(f"Error processing events for camera {camera_uidd}: {str(e)}")
                continue

        _LOGGER.info(f"Processed {events_processed} new events.")

    async def get_gemini_description(self, image_bytes: bytes, api_key: str) -> Optional[str]:
        """Get a clean, simple, but highly descriptive VMS event summary using Google Gemini Flash-2.0-lite."""
        try:
            base64_image = base64.b64encode(image_bytes).decode('utf-8')
            prompt = (
                "Describe the surveillance image for a video management system operator. "
                "Be clear, specific, and concise. Include:\n"
                "- Number of vehicles, make, model, color, and any visible branding (e.g., DPD, DHL, Amazon).\n"
                "- Number of people, gender (if clear), clothing colors, accessories (e.g., hats, bags), and what each person is doing.\n"
                "- Any visible actions (e.g., walking, running, carrying, talking, delivering, entering vehicle).\n"
                "- Any notable objects (e.g., packages, bicycles, animals) and their location.\n"
                "- The general scene (e.g., street, parking lot, warehouse, office).\n"
                "- Lighting conditions (e.g., daylight, night, artificial light).\n"
                "Use full sentences. Do not guess or invent details. Do not start your response with any generic phrase. DO NOT SAY Here's a description of the surveillance image:\n"
                "Example: 'A white DPD van with a DPD logo is parked on the left. Two people are present: a woman in a red jacket is walking toward the van carrying a brown package, and a man in a blue hoodie stands near a blue car. The scene is a parking lot in daylight.'"
            )

            url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-lite:generateContent"
            headers = {"Content-Type": "application/json"}
            data = {
                "contents": [
                    {
                        "parts": [
                            {"inline_data": {"mime_type": "image/jpeg", "data": base64_image}},
                            {"text": prompt}
                        ]
                    }
                ]
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(f"{url}?key={api_key}", headers=headers, json=data) as response:
                    if response.status == 200:
                        result = await response.json()
                        description = result["candidates"][0]["content"]["parts"][0]["text"]
                        _LOGGER.debug(f"Gemini response for image: {description}")
                        return description
                    else:
                        error_text = await response.text()
                        _LOGGER.error(f"Gemini API error: {response.status} - {error_text}")
                        return None
        except Exception as e:
            _LOGGER.error(f"Error in get_gemini_description: {e}")
            return None

    async def async_load_descriptions(self) -> Dict[str, Any]:
        """Load stored descriptions from Home Assistant storage."""
        store = storage.Store(self.hass, 1, f"{DOMAIN}_descriptions")
        try:
            data = await store.async_load()
            return data if data is not None else {}
        except Exception as e:
            _LOGGER.error(f"Error loading descriptions: {str(e)}")
            return {}

    async def async_save_descriptions(self, descriptions: Dict[str, Any]) -> None:
        """Save descriptions to Home Assistant storage."""
        store = storage.Store(self.hass, 1, f"{DOMAIN}_descriptions")
        try:
            await store.async_save(descriptions)
        except Exception as e:
            _LOGGER.error(f"Error saving descriptions: {str(e)}")

    async def clear_descriptions(self) -> None:
        """Clear all stored event descriptions."""
        try:
            self._descriptions = {}
            await self.async_save_descriptions(self._descriptions)
            _LOGGER.info("All event descriptions cleared successfully")
        except Exception as e:
            _LOGGER.error("Failed to clear descriptions: %s", str(e))
            raise