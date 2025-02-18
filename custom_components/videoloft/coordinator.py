# coordinator.py

from __future__ import annotations

import logging
from typing import List, Dict, Any, Optional
import openai
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
        """Process events and get descriptions from OpenAI."""
        api_key = self.hass.data[DOMAIN].get("openai_api_key")
        if not api_key:
            _LOGGER.error("OpenAI API key not set.")
            return
            
        openai.api_key = api_key
        descriptions = await self.async_load_descriptions()
        events_processed = 0
        
        for camera_uidd in selected_cameras:
            try:
                logger_server = await self.api.get_logger_server(camera_uidd)
                if not logger_server:
                    _LOGGER.error(f"Could not get logger server for camera {camera_uidd}")
                    continue
                    
                now = datetime.utcnow()
                previous_day = now - timedelta(days=1)
                start_time = int(previous_day.replace(hour=10, minute=0, second=0, microsecond=0).timestamp() * 1000)
                end_time = int(previous_day.replace(hour=11, minute=0, second=0, microsecond=0).timestamp() * 1000)
                
                events = await self.api.get_recent_events_paginated(
                    logger_server, camera_uidd, start_time, end_time
                )
                
                if not events:
                    _LOGGER.warning(f"No events found for camera {camera_uidd}")
                    continue
                    
                _LOGGER.info(f"Processing {len(events)} events for camera {camera_uidd}")
                
                for event in events:
                    event_id = event.get("alert")
                    if not event_id or event_id in descriptions:
                        continue

                    # Download thumbnail
                    image_data = await self.api.download_event_thumbnail(
                        logger_server, camera_uidd, event_id
                    )
                    
                    if not image_data:
                        _LOGGER.warning(f"No thumbnail available for event {event_id}")
                        continue

                    # Get description from OpenAI
                    description = await self.get_openai_description(image_data)
                    if description:
                        _LOGGER.debug(f"Description for event {event_id}: {description}")
                        descriptions[event_id] = {
                            'description': description,
                            'uidd': camera_uidd,
                            'logger_server': logger_server,
                            'startt': event.get('startt')
                        }
                        events_processed += 1

                        # Save descriptions immediately after processing each event
                        await self.async_save_descriptions(descriptions)
                        _LOGGER.info(f"Saved description for event {event_id}")
                    else:
                        _LOGGER.warning(f"No description generated for event {event_id}")

            except Exception as e:
                _LOGGER.exception(f"Error processing events for camera {camera_uidd}: {str(e)}")
                continue

        _LOGGER.info(f"Processed {events_processed} new events.")

    async def get_openai_description(self, image_bytes: bytes) -> Optional[str]:
        """Get a detailed, searchable description focusing on identifiable elements."""
        try:
            base64_image = base64.b64encode(image_bytes).decode('utf-8')
            prompt = (
                "Create a concise, searchable description, focusing solely on visible and relevant elements. "
                "Exclude unnecessary details such as 'there is no person' or generic observations like 'the sky is blue.' "
                "Provide a clear paragraph that captures only specific, identifiable, and searchable features. Focus on:\n\n"
                
                "1. **Vehicles**:\n"
                "- Mention the exact make, model, and color of any visible vehicles (e.g., 'black BMW 3-Series').\n"
                "- Include license plate numbers if they are clearly visible.\n"
                "- Identify any commercial or delivery vehicles with visible branding or logos (e.g., 'white DPD van with logo on side').\n"
                "- Specify the total count of vehicles and note positions only if they add relevance (e.g., 'parked near entrance').\n\n"
                
                "2. **People** (if present):\n"
                "- Note the number of people and provide distinctive descriptions.\n"
                "- Describe clothing colors, patterns, or unique items (e.g., 'red jacket with hood').\n"
                "- Mention any visible uniforms or branding on clothing (e.g., 'Royal Mail jacket').\n"
                "- Include observed actions (e.g., 'delivering package,' 'walking westbound').\n"
                "- Indicate direction of movement (e.g., 'walking north').\n\n"
                
                "3. **Contextual Details**:\n"
                "- Describe any visible packages, deliveries, or carried items (e.g., 'brown parcel').\n"
                "- Include notable objects or scene elements only if they contribute relevant context (e.g., 'yellow bicycle parked near mailbox').\n"
                "- Mention lighting conditions (e.g., 'daylight' or 'night') if they impact scene clarity.\n\n"
                
                "4. **Branding and Identifiable Features**:\n"
                "- Highlight any recognizable brand logos or markings on vehicles, uniforms, or packages, as these are essential for searchability (e.g., 'DPD logo on van,' 'Royal Mail uniform').\n\n"
                
                "Format the description as a single, clear paragraph, focusing on elements that are present, identifiable, and enhance searchability. "
                "Avoid extraneous details and redundant observations.\n\n"
                
                "Example: 'Five vehicles are visible: a white Ford Transit DPD van (plate AB12 CDE) with a DPD logo on the side, a red Tesla Model 3, a blue Toyota Prius, a dark gray BMW X5 with a small dent on the rear bumper, and a yellow DHL delivery truck parked along the curb. "
                "Three individuals are present: one person in a high-vis yellow jacket with a Royal Mail logo, holding a brown package, standing by the entrance and facing north; a second person wearing a dark blue coat with a hood and a red scarf, walking westbound while holding a black umbrella; and a third person in a green jacket and jeans, leaning against the blue Toyota Prius and appearing to be looking at a smartphone. "
                "Scene occurs in daylight with mild cloud cover. Nearby, a yellow bicycle is parked near a green mailbox on the left side of the frame, and a small red shopping cart is positioned close to the DHL truck. The background includes a visible lamppost and a row of bushes along the sidewalk. No other pedestrians are visible.'"
            )

            payload = {
                "model": "gpt-4o",
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}
                            }
                        ]
                    }
                ],
                "max_tokens": 700,
            }
    
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {openai.api_key}"
            }
    
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers=headers,
                    json=payload
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        description = result['choices'][0]['message']['content']
                        _LOGGER.debug(f"OpenAI response for image: {description}")
                        return description
                    else:
                        error_text = await response.text()
                        _LOGGER.error(f"OpenAI API error: {response.status} - {error_text}")
                        return None
    
        except Exception as e:
            _LOGGER.error(f"Error in get_openai_description: {e}")
            return None

    async def async_load_descriptions(self) -> Dict[str, Any]:
        """Load stored descriptions from Home Assistant storage."""
        store = self.hass.helpers.storage.Store(1, f"{DOMAIN}_descriptions")
        try:
            data = await store.async_load()
            return data if data is not None else {}
        except Exception as e:
            _LOGGER.error(f"Error loading descriptions: {str(e)}")
            return {}

    async def async_save_descriptions(self, descriptions: Dict[str, Any]) -> None:
        """Save descriptions to Home Assistant storage."""
        store = self.hass.helpers.storage.Store(1, f"{DOMAIN}_descriptions")
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