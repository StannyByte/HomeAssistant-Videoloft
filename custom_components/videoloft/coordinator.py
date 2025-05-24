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
        try:
            # Make sure self._triggers is always a list
            if not isinstance(self._triggers, list):
                self._triggers = []
            return self._triggers
        except Exception as e:
            _LOGGER.error("Error loading triggers: %s", e)
            return []

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
        """Get an ultra-detailed, highly structured forensic VMS event summary using Google Gemini Flash-2.0-lite."""
        try:
            base64_image = base64.b64encode(image_bytes).decode('utf-8')
            prompt = (
                "Perform an ultra-detailed forensic analysis of the provided CCTV thumbnail image. Extract every discernible entity, its precise attributes, dynamic relationships, and contextual information to generate an exhaustive, highly structured textual description. This output is intended for the most granular search queries within a Video Management System (VMS).\n\n"
                "**Core Analysis Directives & Granularity:**\n\n"
                "For each identified element, provide specific, measurable, and observable details. Do not include any attributes or information that are not clearly visible or discernible in the image. Do not state that information is \"not visible\" or \"not discernible\"; simply omit it.\n\n"
                "* **Human Subjects (if present):**\n"
                "* **Count:** State the exact number of individuals.\n"
                "* **Apparent Demographics:** Detail observable traits (e.g., \"adult male, approx. 30-45 years old,\" \"child, approx. 8-10 years old,\" \"elderly female\").\n"
                "* **Clothing & Accessories (Be specific on texture, pattern, fit):**\n"
                "* **Headwear:** Type, color, material, and fit (e.g., \"tight-fitting red baseball cap,\" \"loose black knitted beanie,\" \"grey hood pulled up over head\").\n"
                "* **Upper Body:** Garment type, primary and secondary colors, pattern, material, fit (e.g., \"baggy blue denim jacket,\" \"fitted grey hooded sweatshirt with white drawstrings,\" \"reflective yellow high-visibility vest,\" \"long black formal wool coat,\" \"striped red and white t-shirt\").\n"
                "* **Lower Body:** Garment type, color, pattern, fit (e.g., \"dark wash skinny jeans,\" \"loose beige cargo trousers,\" \"black athletic leggings,\" \"pleated floral print midi-skirt\").\n"
                "* **Footwear:** Type, color, style (e.g., \"clean white athletic trainers with black sole,\" \"worn brown leather work boots,\" \"shiny black dress shoes\").\n"
                "* **Bags/Luggage:** Type, color, material, approximate size, how carried (e.g., \"large black canvas backpack, worn on both shoulders,\" \"small red leather crossbody bag,\" \"brown hard-shell briefcase held in right hand\").\n"
                "* **Other Accessories:** Detail all visible accessories (e.g., \"thin-rimmed prescription glasses,\" \"silver-framed sunglasses resting on head,\" \"holding a compact black umbrella,\" \"wearing a silver wristwatch on left wrist\").\n"
                "* **Actions & Posture (Specify intensity and context):**\n"
                "* **Movement:** Precise action (e.g., \"walking briskly towards,\" \"running quickly away from,\" \"standing still, facing,\" \"sitting slumped on,\" \"entering through,\" \"exiting from\"). Specify direction relative to a fixed point or camera (e.g., \"walking towards a black BMW,\" \"moving east across the frame,\" \"facing directly into building entrance\").\n"
                "* **Interaction:** Explicit interactions (e.g., \"opening driver's side car door,\" \"exchanging a small package with another person,\" \"peering into shop window,\" \"typing on a smartphone,\" \"carrying a large white delivery box\").\n"
                "* **Body Orientation:** Detailed body and head orientation (e.g., \"body angled 45 degrees left, head turned to look right,\" \"back to camera, looking over left shoulder\").\n"
                "* **Distinguishing Features (Highlight uniqueness):** Note any unique, clearly visible features (e.g., \"large sleeve tattoo on right arm,\" \"distinctive facial scar near left eye,\" \"bright green dyed hair,\" \"limping on right leg\").\n\n"
                "* **Vehicles (if present):**\n"
                "* **Count:** State the exact number of vehicles.\n"
                "* **Type & Subtype:** Highly specific classification (e.g., \"four-door saloon,\" \"three-door compact hatchback,\" \"full-size luxury SUV,\" \"double-cab pickup truck,\" \"long-wheelbase commercial panel van,\" \"sport motorcycle,\" \"mountain bicycle,\" \"rigid heavy goods vehicle\").\n"
                "* **Make & Model:** If unambiguously identifiable (e.g., \"BMW 3 Series G20,\" \"Seat Leon Mk4,\" \"VW Golf Mk8 R-Line,\" \"Ford Transit Custom L1H1,\" \"Mercedes-Benz Sprinter 313 CDI\").\n"
                "* **Color & Finish:** Primary and secondary colors, specific finish (e.g., \"gloss black,\" \"metallic silver,\" \"matte grey,\" \"deep metallic blue,\" \"white with a red stripe\").\n"
                "* **Condition:** Describe observable condition in detail (e.g., \"immaculate bodywork,\" \"minor scuffs on front bumper,\" \"significantly dirty with mud splatter,\" \"missing front left hubcap,\" \"visible dent on rear passenger door,\" \"flat tire on front right\").\n"
                "* **State & Position:** Precise state and spatial positioning (e.g., \"parked parallel to curb,\" \"driving slowly in left lane,\" \"stationary at red traffic light,\" \"reversing into designated parking bay,\" \"engine idling, brake lights illuminated\"). Specify lane, road position, or parking alignment.\n"
                "* **Distinctive Features:** Note any visible modifications or unique attributes (e.g., \"black roof rack with two mountain bikes mounted,\" \"visible tow hitch with ball,\" \"aftermarket multi-spoke alloy wheels,\" \"prominent 'TAXI' roof sign,\" \"company livery: 'Speedy Deliveries' logo on side,\" \"tinted rear windows\").\n"
                "* **Occupants:** Number and general description of visible occupants (e.g., \"single driver, male,\" \"two occupants, driver and front passenger\").\n\n"
                "* **Objects (Non-Human, Non-Vehicle - if present):**\n"
                "* **Count:** State the exact number of significant objects.\n"
                "* **Type:** Highly specific categorization and description (e.g., \"standard public litter bin,\" \"ornamental streetlamp with LED fixture,\" \"wooden park bench with cast iron legs,\" \"orange traffic cone with reflective strip,\" \"cylindrical security camera housing mounted on wall,\" \"red plastic shopping trolley,\" \"brown corrugated cardboard parcel, sealed with tape,\" \"rectangular metal 'No Parking' sign\").\n"
                "* **Attributes:** Detail color, material, condition, any visible text/symbols/logos (e.g., \"dark green plastic bin, half full,\" \"rusted cast iron bench,\" \"damaged yellow 'Restricted Access' sign,\" \"large glass window, reflecting sky\").\n"
                "* **Position:** Precise location relative to other entities or scene boundaries (e.g., \"positioned immediately adjacent to building entrance,\" \"directly under streetlamp,\" \"to the left of the parked black sedan, 1 meter away\").\n\n"
                "* **Environment & Context:**\n"
                "* **Setting Type:** Highly specific description of the location (e.g., \"busy urban street with multiple retail storefronts,\" \"suburban residential driveway beside a detached house,\" \"multi-story underground car park, level B2,\" \"interior of a warehouse loading bay,\" \"public park pathway, near a pond,\" \"commercial loading dock with roller shutter doors\").\n"
                "* **Time of Day & Lighting:** \"Bright mid-day sunlight,\" \"overcast daytime with diffused light,\" \"dusk, with automated streetlights active and casting long shadows,\" \"dark night, illuminated solely by vehicle headlights and a single distant streetlamp.\"\n"
                "* **Weather Conditions:** \"Clear and dry, no precipitation,\" \"light drizzle, wet tarmac visible,\" \"heavy snowfall, ground partially covered,\" \"dense fog reducing visibility to 20 meters,\" \"wet ground from recent rain, puddles present.\"\n"
                "* **Key Landmarks:** Any identifiable static structures (e.g., \"distinctive red brick building facade with arched windows,\" \"mature oak tree with dense foliage,\" \"clearly visible road markings: double yellow lines,\" \"parking bay number 27\").\n"
                "* **Surface:** Describe the ground surface (e.g., \"asphalt road,\" \"concrete pavement,\" \"grass lawn,\" \"gravel driveway\").\n\n"
                "**Output String Generation:**\n\n"
                "Generate a single, continuous, comma-separated string comprising highly descriptive, keyword-rich phrases. Each phrase must be a self-contained, searchable unit of information. The string should contain *only* the extracted data, without any introductory or concluding remarks.\n\n"
                "**Example of Desired Output String (Illustrative - imagine a more detailed image):**\n\n"
                "\"adult male, approx. 35-40 years old, wearing a tight-fitting red baseball cap, baggy blue denim jacket, dark wash skinny jeans, clean white athletic trainers with black sole, carrying a large black canvas backpack, walking briskly towards, parked gloss black BMW 3 Series G20 saloon, driver's side door slightly ajar, minor scuffs on front bumper, metallic silver Seat Leon Mk4 hatchback, parallel parked, pristine bodywork, green VW Transporter T6 commercial van, stationary at traffic light, clear company livery 'Swift Logistics', busy urban street with multiple retail storefronts, bright mid-day sunlight, clear and dry weather, ornamental streetlamp with LED fixture, large glass window reflecting sky, asphalt road, double yellow lines visible\""
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