import asyncio
import json
import logging
import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, List, Tuple

from aiohttp import web, WSCloseCode
from homeassistant.components.http import HomeAssistantView
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.util import dt as dt_util

from .api import VideoloftAPI
from ..const import DOMAIN
from homeassistant.components.websocket_api import (
    async_register_command,
    WebSocketCommandHandler,
    websocket_command,
)
from datetime import datetime
from .storage import GlobalStreamStateStore, ApiKeyStore

_LOGGER = logging.getLogger(__name__)

# ----------------------------------------------------------
# UTILITY FUNCTIONS
# ----------------------------------------------------------


def get_entry(hass: HomeAssistant) -> Optional[ConfigEntry]:
    """Retrieve the first configuration entry for the domain."""
    entries = hass.config_entries.async_entries(DOMAIN)
    return entries[0] if entries else None


def get_device_data(hass: HomeAssistant, uidd: str) -> Optional[Dict[str, Any]]:
    """Retrieve device data based on UIDD."""
    entry = get_entry(hass)
    if not entry:
        _LOGGER.error("No configuration entry found for domain '%s'.", DOMAIN)
        return None

    cameras_info = hass.data[DOMAIN][entry.entry_id].get("devices", []) # Changed from "devices" dict to "cameras_info" list
    
    # Iterate through the flat list to find the matching camera
    for camera_data in cameras_info:
        if f"{camera_data['uid']}.{camera_data['id']}" == uidd:
            return camera_data

    _LOGGER.error("Camera with UIDD '%s' not found.", uidd)
    return None


class VideoloftCamerasView(HomeAssistantView):
    """Handle fetching the list of cameras."""

    url = "/api/videoloft/cameras"
    name = "api:videoloft:cameras"
    requires_auth = False

    def __init__(self, hass: HomeAssistant):
        self.hass = hass

    async def get(self, request: web.Request) -> web.Response:
        """Handle the GET request."""
        entry = get_entry(self.hass)
        if not entry:
            return web.json_response({"cameras": []})

        cameras_info = self.hass.data[DOMAIN][entry.entry_id].get("devices", []) # Changed from "devices" dict to "cameras_info" list
        cameras = []
        
        for camera_data in cameras_info:
            uidd = f"{camera_data['uid']}.{camera_data['id']}"
            # Debug logging to see what fields are available
            _LOGGER.debug(f"Camera data for {uidd}: {camera_data}")
            
            camera = {
                "uidd": uidd,
                "name": camera_data.get("name", camera_data.get("phonename", f"Camera {uidd}")),
                "model": camera_data.get("model", "Unknown Model"),
                "resolution": camera_data.get("recordingResolution", "Unknown"),
                "status": "online" if camera_data.get("mainstreamLive") == 1 else "offline",
                "analytics_enabled": camera_data.get("analyticsEnabled", False),
                "logger": camera_data.get("logger", ""),
                "wowza": camera_data.get("wowza", ""),
                "stream_name": camera_data.get("recordedStreamName", "")
            }
            cameras.append(camera)

        _LOGGER.info(f"Returning {len(cameras)} cameras to frontend")
        return web.json_response({"cameras": cameras})


class VideoloftThumbnailView(HomeAssistantView):
    """A view that returns the latest thumbnail image for a camera with caching."""

    url = "/api/videoloft/thumbnail/{uidd}"
    name = "api:videoloft:thumbnail"
    requires_auth = False

    def __init__(self, hass: HomeAssistant):
        self.hass = hass

    async def get(self, request: web.Request, uidd: str) -> web.Response:
        """Handle the GET request for the thumbnail image with enhanced caching."""
        try:
            # Check for conditional request headers
            if_none_match = request.headers.get('If-None-Match')
            
            # Get coordinator for caching
            coordinator = None
            for entry_id, entry_data in self.hass.data.get(DOMAIN, {}).items():
                if "coordinator" in entry_data:
                    coordinator = entry_data["coordinator"]
                    break
            
            thumbnail_data = None
            
            if coordinator:
                # For immediate display, try to get cached thumbnail (even if slightly stale)
                thumbnail_data = await coordinator.get_cached_thumbnail_immediate(uidd)
                
                if not thumbnail_data:
                    # If no cached data at all, ensure we get a thumbnail
                    thumbnail_data = await coordinator.ensure_thumbnail_available(uidd)
                else:
                    # We have cached data - start a background refresh if needed
                    cache_entry = coordinator._thumbnail_cache.get(uidd)
                    if cache_entry:
                        cached_time = cache_entry.get("timestamp")
                        if cached_time:
                            cache_age = dt_util.utcnow() - cached_time
                            # If cache is older than 1 minute, trigger background refresh
                            if cache_age > coordinator._thumbnail_refresh_interval:
                                # Async background refresh - don't wait for it
                                self.hass.async_create_task(coordinator.refresh_thumbnail(uidd, force=True))
            
            # Fallback to direct API call if coordinator not available
            if not thumbnail_data:
                device_data = get_device_data(self.hass, uidd)
                if not device_data:
                    _LOGGER.warning(f"Device data not found for {uidd}")
                    return web.Response(status=404, text="Camera not found")

                api: VideoloftAPI = self.hass.data[DOMAIN][get_entry(self.hass).entry_id]["api"]
                logger_server = device_data.get("logger")
                
                if logger_server:
                    thumbnail_data = await api.get_camera_thumbnail(uidd, logger_server)
            
            # Ensure we have valid bytes data before returning
            if thumbnail_data and isinstance(thumbnail_data, bytes):
                # Generate ETag based on content hash
                import hashlib
                etag = f'"{hashlib.md5(thumbnail_data).hexdigest()}"'
                
                # Check if client has the same version
                if if_none_match == etag:
                    return web.Response(status=304)  # Not Modified
                
                # Set appropriate cache headers for fast loading
                headers = {
                    'Content-Type': 'image/jpeg',
                    'Cache-Control': 'public, max-age=60, stale-while-revalidate=120',  # Cache for 1 minute, allow stale for 2 minutes
                    'ETag': etag,
                    'Last-Modified': dt_util.utcnow().strftime('%a, %d %b %Y %H:%M:%S GMT')
                }
                return web.Response(body=thumbnail_data, headers=headers)
            else:
                _LOGGER.warning(f"No thumbnail data available for {uidd}")
                return web.Response(status=404, text="Thumbnail not available")
                
        except Exception as e:
            _LOGGER.error("Error fetching thumbnail for %s: %s", uidd, e)
            return web.Response(status=500, text="Internal server error")


class VideoloftEventsView(HomeAssistantView):
    """A view that returns the list of events."""

    url = "/api/videoloft/events"
    name = "api:videoloft:events"
    requires_auth = False

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass

    async def get(self, request: web.Request) -> web.Response:
        """Handle the GET request for events."""
        entry = get_entry(self.hass)
        if not entry:
            return web.json_response({"events": []})

        api: VideoloftAPI = self.hass.data[DOMAIN][entry.entry_id]["api"]

        try:
            events = await api.get_last_events(num_events=20)
            _LOGGER.debug("Fetched %d events.", len(events))
            return web.json_response({"events": events})
        except Exception as e:
            _LOGGER.error("Error fetching events: %s", e)
            return web.json_response({"events": []}, status=500)

class EventThumbnailView(HomeAssistantView):
    """Serve event thumbnails."""
    url = "/api/videoloft/event_thumbnail/{event_id}"
    name = "api:videoloft:event_thumbnail"
    requires_auth = False
    
    def __init__(self, hass: HomeAssistant):
        """Initialize the view."""
        self.hass = hass
        self._cache = {}  # Simple in-memory cache
        super().__init__()

    async def get(self, request: web.Request, event_id: str) -> web.Response:
        """Handle GET request to serve event thumbnail."""
        try:
            # Try cache first
            if event_id in self._cache:
                return web.Response(
                    body=self._cache[event_id], 
                    content_type='image/jpeg'
                )

            # Get coordinator from domain data
            entry = get_entry(self.hass)
            if not entry:
                raise ValueError("Configuration entry not found")
                
            coordinator = self.hass.data[DOMAIN][entry.entry_id].get("coordinator")
            if not coordinator:
                raise ValueError("Coordinator not found")

            # Get event info from descriptions
            descriptions = await coordinator.async_load_descriptions()
            event_info = descriptions.get(event_id)
            
            if not event_info:
                _LOGGER.warning(f"No event info found for event {event_id}")
                return web.Response(status=404)

            logger_server = event_info.get('logger_server')
            uidd = event_info.get('uidd')
            
            if not logger_server or not uidd:
                _LOGGER.error(f"Missing required event info for {event_id}")
                return web.Response(status=404)

            # Get API instance from coordinator instead
            api = coordinator.api  # Changed this line
            if not api:
                raise ValueError("API not initialized")

            # Download thumbnail
            image_data = await api.download_event_thumbnail(
                logger_server, uidd, event_id
            )

            if not image_data:
                _LOGGER.warning(f"No thumbnail available for event {event_id}")
                return web.Response(status=404)

            # Cache the thumbnail
            self._cache[event_id] = image_data

            return web.Response(
                body=image_data,
                content_type='image/jpeg'
            )

        except ValueError as e:
            _LOGGER.error("Configuration error: %s", str(e))
            return web.Response(status=500)
        except Exception as e:
            _LOGGER.exception("Error serving event thumbnail: %s", str(e))
            return web.Response(status=500)

# ----------------------------------------------------------
# LPR MANAGEMENT VIEWS
# ----------------------------------------------------------

class LPRTriggersView(HomeAssistantView):
    """Handle LPR triggers management."""

    url = "/api/videoloft/lpr_triggers"
    name = "api:videoloft:lpr_triggers"
    requires_auth = False

    def __init__(self, hass: HomeAssistant):
        self.hass = hass

    async def post(self, request: web.Request) -> web.Response:
        """Handle POST request to add a new LPR trigger."""
        try:
            entry = get_entry(self.hass)
            if not entry:
                _LOGGER.error("Integration not set up")
                return web.json_response({"error": "Integration not set up."}, status=400)

            coordinator = self.hass.data[DOMAIN][entry.entry_id].get("coordinator")
            if not coordinator:
                _LOGGER.error("Coordinator not found for entry_id: %s", entry.entry_id)
                return web.json_response({"error": "Coordinator not found."}, status=400)

            data = await request.json()
            _LOGGER.info("Received LPR trigger request: %s", data)

            uidd = data.get("uidd")
            license_plate = data.get("license_plate", "").strip().lower()
            make = data.get("make", "").strip().lower()
            model = data.get("model", "").strip().lower()
            color = data.get("color", "").strip().lower()

            if not uidd:
                return web.json_response({"error": "Camera UIDD is required."}, status=400)
            if not any([license_plate, make, model, color]):
                return web.json_response({"error": "At least one attribute (license_plate, make, model, or color) is required."}, status=400)

            device_data = get_device_data(self.hass, uidd)

            if not device_data:
                return web.json_response({"error": "Specified camera does not exist."}, status=400)

            new_trigger = {
                "uidd": uidd,
                "license_plate": license_plate,
                "make": make,
                "model": model,
                "color": color,
                "enabled": True  # Assuming triggers are enabled by default
            }

            triggers = await coordinator.async_load_triggers()
            if not isinstance(triggers, list):
                triggers = []
            triggers.append(new_trigger)
            await coordinator.async_save_triggers(triggers)

            _LOGGER.info("Successfully added LPR trigger: %s", new_trigger)
            return web.json_response({"triggers": triggers}, status=201)

        except json.JSONDecodeError:
            _LOGGER.error("Invalid JSON format in LPR trigger POST request.")
            return web.json_response({"error": "Invalid JSON format."}, status=400)
        except Exception as e:
            _LOGGER.error("Error processing LPR trigger request: %s", e)
            return web.json_response({"error": str(e)}, status=500)

    async def get(self, request: web.Request) -> web.Response:
        """Handle GET request to list all LPR triggers."""
        entry = get_entry(self.hass)
        if not entry:
            return web.json_response({"triggers": []})

        triggers = self.hass.data[DOMAIN][entry.entry_id].get("lpr_triggers", [])
        return web.json_response({"triggers": triggers})

    async def delete(self, request: web.Request) -> web.Response:
        """Handle DELETE request to remove an LPR trigger."""
        try:
            data = await request.json()
            index = data.get("index")

            if index is None:
                return web.json_response({"error": "Trigger index is required."}, status=400)

            entry = get_entry(self.hass)
            if not entry:
                _LOGGER.error("Integration not set up")
                return web.json_response({"error": "Integration not set up."}, status=400)

            coordinator = self.hass.data[DOMAIN][entry.entry_id].get("coordinator")
            if not coordinator:
                _LOGGER.error("Coordinator not found for entry_id: %s", entry.entry_id)
                return web.json_response({"error": "Coordinator not found."}, status=400)

            triggers = await coordinator.async_load_triggers()
            if not (0 <= index < len(triggers)):
                return web.json_response({"error": "Invalid trigger index."}, status=400)

            removed_trigger = triggers.pop(index)
            await coordinator.async_save_triggers(triggers)

            _LOGGER.info("Successfully deleted LPR trigger: %s", removed_trigger)
            return web.json_response({
                "success": True,
                "triggers": triggers,
                "message": f"Trigger {index} deleted successfully."
            })

        except json.JSONDecodeError:
            _LOGGER.error("Invalid JSON format in LPR trigger DELETE request.")
            return web.json_response({"error": "Invalid JSON format."}, status=400)
        except Exception as e:
            _LOGGER.error("Error deleting LPR trigger: %s", e)
            return web.json_response({"error": str(e)}, status=500)

    async def put(self, request: web.Request) -> web.Response:
        """Handle PUT request to update trigger state."""
        try:
            data = await request.json()
            index = data.get("index")
            enabled = data.get("enabled")

            if index is None or enabled is None:
                return web.json_response({"error": "Both 'index' and 'enabled' are required."}, status=400)

            if not isinstance(enabled, bool):
                return web.json_response({"error": "'enabled' must be a boolean."}, status=400)

            entry = get_entry(self.hass)
            if not entry:
                _LOGGER.error("Integration not set up")
                return web.json_response({"error": "Integration not set up."}, status=400)

            coordinator = self.hass.data[DOMAIN][entry.entry_id].get("coordinator")
            if not coordinator:
                _LOGGER.error("Coordinator not found for entry_id: %s", entry.entry_id)
                return web.json_response({"error": "Coordinator not found."}, status=400)

            triggers = await coordinator.async_load_triggers()
            if not (0 <= index < len(triggers)):
                return web.json_response({"error": "Invalid trigger index."}, status=400)

            triggers[index]["enabled"] = enabled
            await coordinator.async_save_triggers(triggers)

            _LOGGER.info("Updated LPR trigger at index %d to %s.", index, "enabled" if enabled else "disabled")
            return web.json_response({
                "success": True,
                "triggers": triggers,
                "message": f"Trigger {index} {'enabled' if enabled else 'disabled'} successfully."
            })

        except json.JSONDecodeError:
            _LOGGER.error("Invalid JSON format in LPR trigger PUT request.")
            return web.json_response({"error": "Invalid JSON format."}, status=400)
        except Exception as e:
            _LOGGER.error("Error updating LPR trigger: %s", e)
            return web.json_response({"error": str(e)}, status=500)


class LPRLogsWebSocket(HomeAssistantView):
    """WebSocket handler for LPR logs."""

    name = "api:videoloft:lpr_logs"
    url = "/api/videoloft/ws/lpr_logs"
    requires_auth = False

    def __init__(self, hass: HomeAssistant):
        super().__init__()
        self.hass = hass
        self.clients: set[web.WebSocketResponse] = set()
        self._logger = logging.getLogger('custom_components.videoloft.sensor')
        self._handler = self.create_log_handler()
        self._logger.addHandler(self._handler)

    async def cleanup(self):
        """Clean up WebSocket connections and handlers."""
        try:
            # Close all WebSocket connections
            for client in set(self.clients):
                if not client.closed:
                    await client.close(code=WSCloseCode.GOING_AWAY, message=b'Server shutting down')
            self.clients.clear()
            
            # Remove log handler
            if self._handler and self._logger:
                self._logger.removeHandler(self._handler)
                
            _LOGGER.debug("LPRLogsWebSocket cleanup completed")
        except Exception as e:
            _LOGGER.error("Error during WebSocket cleanup: %s", e)

    def create_log_handler(self) -> logging.Handler:
        """Create a logging handler that forwards to websocket clients."""
        handler = logging.Handler()
        handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        handler.emit = self.log_handler
        return handler

    def log_handler(self, record: logging.LogRecord) -> None:
        """Handle log records and send to websocket clients."""
        try:
            log_entry = {
                "timestamp": datetime.fromtimestamp(record.created).strftime("%Y-%m-%d %H:%M:%S,%f")[:-3],
                "level": record.levelname,
                "message": record.getMessage()
            }

            for client in set(self.clients):
                if not client.closed:
                    asyncio.create_task(client.send_json(log_entry))
                else:
                    self.clients.discard(client)
        except Exception as e:
            _LOGGER.error("Error in log handler: %s", e)

    async def get(self, request: web.Request) -> web.WebSocketResponse:
        """Handle WebSocket connections."""
        ws = web.WebSocketResponse(heartbeat=55)
        await ws.prepare(request)
        self.clients.add(ws)

        _LOGGER.info("WebSocket client connected.")

        try:
            async for msg in ws:
                if msg.type == web.WSMsgType.ERROR:
                    _LOGGER.error('WebSocket connection closed with exception %s', ws.exception())
        except Exception as e:
            _LOGGER.error("WebSocket connection error: %s", e)
        finally:
            self.clients.discard(ws)
            _LOGGER.info("WebSocket client disconnected.")
            if not ws.closed:
                await ws.close()

        return ws

# ----------------------------------------------------------
# AI INTEGRATION VIEWS
# ----------------------------------------------------------

class GeminiKeyView(HomeAssistantView):
    """Handle Google Gemini API key management."""

    url = "/api/videoloft/gemini_key"
    name = "api:videoloft:gemini_key"
    requires_auth = False

    def __init__(self, hass: HomeAssistant):
        self.hass = hass

    async def post(self, request: web.Request) -> web.Response:
        """Save Gemini API key to server-side storage (never echoed)."""
        try:
            data = await request.json()
            api_key = data.get("api_key")

            if not api_key:
                return web.json_response({"error": "API key is required."}, status=400)

            store = ApiKeyStore(self.hass)
            await store.async_set_key(api_key)
            # Keep a lightweight in-memory marker for quick checks
            self.hass.data.setdefault(DOMAIN, {})["gemini_api_key"] = "SET"
            _LOGGER.info("Gemini API key stored on server")
            return web.json_response({"success": True, "has_key": True}, status=201)
        except json.JSONDecodeError:
            _LOGGER.error("Invalid JSON format in Gemini API key POST request.")
            return web.json_response({"error": "Invalid JSON format."}, status=400)
        except Exception as e:
            _LOGGER.error("Error saving Gemini API key: %s", e)
            return web.json_response({"error": str(e)}, status=500)

    async def delete(self, request: web.Request) -> web.Response:
        """Remove Gemini API key for all devices."""
        try:
            store = ApiKeyStore(self.hass)
            await store.async_clear_key()
            self.hass.data.setdefault(DOMAIN, {})["gemini_api_key"] = None
            _LOGGER.info("Gemini API key cleared from server storage")
            return web.json_response({"success": True, "has_key": False}, status=200)
        except Exception as e:
            _LOGGER.error("Error removing Gemini API key: %s", e)
            return web.json_response({"error": str(e)}, status=500)

    async def get(self, request: web.Request) -> web.Response:
        """Check if Gemini API key exists (do not return the key)."""
        try:
            store = ApiKeyStore(self.hass)
            has_key = await store.async_has_key()
            return web.json_response({"has_key": has_key}, status=200)
        except Exception as e:
            _LOGGER.error("Error checking Gemini API key: %s", e)
            return web.json_response({"error": str(e)}, status=500)


class ProcessEventsView(HomeAssistantView):
    """Handle processing events and getting descriptions from OpenAI."""

    url = "/api/videoloft/process_events"
    name = "api:videoloft:process_events"
    requires_auth = False

    def __init__(self, hass: HomeAssistant):
        self.hass = hass

    async def post(self, request: web.Request) -> web.Response:
        """Handle POST request to process events."""
        try:
            entry = get_entry(self.hass)
            if not entry:
                _LOGGER.error("No configuration entry found for domain '%s'.", DOMAIN)
                return web.json_response({"error": "No configuration entry found."}, status=400)

            coordinator = self.hass.data[DOMAIN][entry.entry_id].get("coordinator")
            if not coordinator:
                _LOGGER.error("Coordinator not found for entry_id: %s", entry.entry_id)
                return web.json_response({"error": "Coordinator not found."}, status=400)

            api_key = self.hass.data[DOMAIN].get("openai_api_key")
            # Legacy fallback: if OpenAI key isn't set, try the stored Gemini key
            gemini_store = ApiKeyStore(self.hass)
            use_gemini_fallback = not api_key and await gemini_store.async_has_key()

            try:
                data = await request.json()
                selected_cameras: List[str] = data.get("cameras", [])
            except json.JSONDecodeError:
                _LOGGER.error("Invalid JSON format in process_events POST request.")
                return web.json_response({"error": "Invalid JSON format."}, status=400)

            if not selected_cameras:
                # If no specific cameras are selected, process all available cameras
                # The 'devices' now directly contains the list of camera objects
                cameras_info = self.hass.data[DOMAIN][entry.entry_id].get("devices", [])
                selected_cameras = [
                    f"{camera_data['uid']}.{camera_data['id']}"
                    for camera_data in cameras_info
                ]

            if not selected_cameras:
                _LOGGER.warning("No cameras available to process events.")
                return web.json_response({"error": "No cameras available to process events."}, status=400)

            if use_gemini_fallback:
                _LOGGER.info("Legacy process_events fallback: using stored Gemini key")
                asyncio.create_task(coordinator.process_ai_search(selected_cameras))
                return web.json_response({"success": True, "message": "AI Search task (Gemini) initiated."}, status=202)
            else:
                if not api_key:
                    _LOGGER.error("OpenAI API key not set.")
                    return web.json_response({"error": "OpenAI API key not set."}, status=400)
                asyncio.create_task(coordinator.process_events(api_key, selected_cameras))
                _LOGGER.info("AI Search task (OpenAI) initiated for cameras: %s", selected_cameras)
                return web.json_response({"success": True, "message": "AI Search task initiated."}, status=202)

        except Exception as e:
            _LOGGER.error("Error initiating AI Search task: %s", e)
            return web.json_response({"error": str(e)}, status=500)

class SearchEventsView(HomeAssistantView):
    """Handle searching events."""
    url = "/api/videoloft/search_events"
    name = "api:videoloft:search_events"
    requires_auth = False

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the view."""
        self.hass = hass

    def _tokenize_query(self, query: str) -> List[str]:
        """Split query into meaningful tokens."""
        return [word.strip() for word in query.lower().split() if len(word) > 2]

    def _score_match(self, text: str, query_tokens: List[str]) -> Tuple[bool, float]:
        """Score how well text matches query tokens."""
        text = text.lower()
        words = text.split()
        
        # No match if any required word is missing
        for token in query_tokens:
            # Check for exact word match
            word_pattern = f"\\b{token}\\b"
            if not re.search(word_pattern, text):
                # Check if token is part of a compound word that makes sense
                # e.g., "red" in "red-car" or "redcar"
                compound_matches = [
                    word for word in words 
                    if token in word and len(word) < len(token) + 5
                ]
                if not compound_matches:
                    return False, 0.0

        score = 0.0
        
        # Score based on word proximity
        for i in range(len(query_tokens) - 1):
            current = query_tokens[i]
            next_token = query_tokens[i + 1]
            
            # Find positions of words
            current_pos = text.find(current)
            next_pos = text.find(next_token)
            
            if current_pos >= 0 and next_pos >= 0:
                # Higher score for words that appear closer together
                distance = abs(next_pos - current_pos)
                score += 1.0 / (1.0 + (distance / 10.0))

        # Bonus for exact phrase matches
        phrase = " ".join(query_tokens)
        if phrase in text:
            score += 2.0

        return True, min(1.0, score / len(query_tokens))

    async def get(self, request: web.Request) -> web.Response:
        try:
            query = request.query.get("query", "").lower().strip()
            if not query:
                return web.json_response({"error": "Missing search query."}, status=400)

            query_tokens = self._tokenize_query(query)
            if not query_tokens:
                return web.json_response({"error": "Query too short or contains only stop words."}, status=400)

            entry = get_entry(self.hass)
            if not entry:
                return web.json_response({"error": "Configuration not found."}, status=400)
            
            coordinator = self.hass.data[DOMAIN][entry.entry_id].get("coordinator")
            if not coordinator:
                return web.json_response({"error": "Coordinator not found."}, status=400)

            descriptions = await coordinator.async_load_descriptions()
            matching_events = []
            # Reuse a single thumbnail token per request
            thumb_token = await self.get_thumbnail_token(coordinator)

            for event_id, info in descriptions.items():
                description = info.get("description", "")
                if not description:
                    continue

                matches, score = self._score_match(description, query_tokens)
                if matches and score > 0.3:  # Minimum relevance threshold
                    recording_url = (
                        f"https://app.videoloft.com/cameras/{info['uidd']}?"
                        f"uidd={info['uidd']}&eventId={event_id}&"
                        f"logger={info['logger_server']}&startTime={info['startt']}"
                    )
                    matching_events.append({
                        "event_id": event_id,
                        "description": description,
                        "recording_url": recording_url,
                        "thumbnail_url": f"/api/videoloft/event_thumbnail/{event_id}",
                        "relevance": score,
                        "startt": info.get("startt", 0),
                        "matched_query": query
                    })

            # Sort by relevance score then timestamp
            matching_events.sort(key=lambda x: (-x["relevance"], -x["startt"]))

            _LOGGER.debug(
                "Search query '%s' found %d relevant matches", 
                query, 
                len(matching_events)
            )

            return web.json_response({"events": matching_events}, status=200)

        except Exception as e:
            _LOGGER.error("Error searching events: %s", e)
            return web.json_response({"error": str(e)}, status=500)

class AISearchProcessView(HomeAssistantView):
    """Handle AI Search tasks with enhanced processing."""
    
    url = "/api/videoloft/process_ai_search"
    name = "api:videoloft:process_ai_search"
    requires_auth = False
    
    def __init__(self, hass: HomeAssistant):
        """Initialize the view."""
        self.hass = hass
        super().__init__()
        _LOGGER.debug("Initialized Enhanced AISearchProcessView")
    
    async def post(self, request: web.Request) -> web.Response:
        """Handle POST request to initiate enhanced AI Search task."""
        try:
            data = await request.json()
            _LOGGER.debug("Received enhanced AI Search request: %s", data)
            
            entry = get_entry(self.hass)
            if not entry:
                _LOGGER.error("No configuration entry found")
                return web.json_response(
                    {"error": "Configuration not found"}, 
                    status=400
                )
                
            coordinator = self.hass.data[DOMAIN][entry.entry_id].get("coordinator")
            if not coordinator:
                _LOGGER.error("Coordinator not found")
                return web.json_response(
                    {"error": "Coordinator not found"}, 
                    status=400
                )
            
            # Extract parameters
            selected_camera = data.get("camera", "").strip()
            start_date = data.get("start_date")
            end_date = data.get("end_date")
            start_time = data.get("start_time", 8)
            end_time = data.get("end_time", 20)
            
            if not start_date or not end_date:
                return web.json_response(
                    {"error": "Start and end dates are required"}, 
                    status=400
                )
            
            # Get cameras to process
            cameras_to_process = []
            if selected_camera:
                cameras_to_process = [selected_camera]
            else:
                # Get all cameras
                cameras_info = self.hass.data[DOMAIN][entry.entry_id].get("devices", [])
                cameras_to_process = [f"{cam['uid']}.{cam['id']}" for cam in cameras_info]
            
            if not cameras_to_process:
                return web.json_response(
                    {"error": "No cameras available for processing"}, 
                    status=400
                )
            
            _LOGGER.debug("Processing AI Search for cameras: %s", cameras_to_process)
            
            # Start enhanced processing
            result = await coordinator.gemini_api.process_ai_search_enhanced(
                cameras_to_process, start_date, end_date, start_time, end_time
            )
            
            if "error" in result:
                return web.json_response(result, status=400)
            
            return web.json_response({
                "success": True, 
                "task_id": result["task_id"],
                "message": "Enhanced AI Search task initiated"
            })
            
        except Exception as e:
            _LOGGER.exception("Enhanced AI Search process error")
            return web.json_response({"error": str(e)}, status=500)
        
class ClearDescriptionsView(HomeAssistantView):
    """Handle clearing all event descriptions."""
    url = "/api/videoloft/clear_descriptions"
    name = "api:videoloft:clear_descriptions"
    requires_auth = False

    def __init__(self, hass: HomeAssistant):
        self.hass = hass
        super().__init__()

    async def post(self, request: web.Request) -> web.Response:
        """Handle POST request to clear descriptions."""
        try:
            entry = get_entry(self.hass)
            if not entry:
                return web.json_response({"error": "Configuration not found"}, status=400)
                
            coordinator = self.hass.data[DOMAIN][entry.entry_id].get("coordinator")
            if not coordinator:
                return web.json_response({"error": "Coordinator not found"}, status=400)

            await coordinator.clear_descriptions()
            return web.json_response({"success": True})
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

class VideoloftThumbnailStatsView(HomeAssistantView):
    """A view that returns thumbnail cache statistics."""

    url = "/api/videoloft/thumbnail_stats"
    name = "api:videoloft:thumbnail_stats"
    requires_auth = False

    def __init__(self, hass: HomeAssistant):
        self.hass = hass

    async def get(self, request: web.Request) -> web.Response:
        """Get thumbnail cache statistics."""
        try:
            # Get coordinator
            coordinator = None
            for entry_id, entry_data in self.hass.data.get(DOMAIN, {}).items():
                if "coordinator" in entry_data:
                    coordinator = entry_data["coordinator"]
                    break
            
            if coordinator:
                stats = await coordinator.get_thumbnail_cache_stats()
                return web.json_response({"status": "success", "stats": stats})
            else:
                return web.json_response({"status": "error", "message": "Coordinator not found"}, status=404)
                
        except Exception as e:
            _LOGGER.error("Error getting thumbnail stats: %s", e)
            return web.json_response({"status": "error", "message": str(e)}, status=500)

    async def post(self, request: web.Request) -> web.Response:
        """Refresh thumbnail cache for specific cameras or all."""
        try:
            data = await request.json()
            uidds = data.get("uidds", [])  # List of camera UIDs to refresh, empty means all
            
            # Get coordinator
            coordinator = None
            for entry_id, entry_data in self.hass.data.get(DOMAIN, {}).items():
                if "coordinator" in entry_data:
                    coordinator = entry_data["coordinator"]
                    break
            
            if not coordinator:
                return web.json_response({"status": "error", "message": "Coordinator not found"}, status=404)
            
            refreshed_count = 0
            
            if uidds:
                # Refresh specific cameras
                for uidd in uidds:
                    result = await coordinator.refresh_thumbnail(uidd, force=True)
                    if result:
                        refreshed_count += 1
            else:
                # Refresh all cameras
                devices = self.hass.data[DOMAIN][get_entry(self.hass).entry_id].get("devices", [])
                for device in devices:
                    uidd = f"{device['uid']}.{device['id']}"
                    result = await coordinator.refresh_thumbnail(uidd, force=True)
                    if result:
                        refreshed_count += 1
            
            return web.json_response({
                "status": "success", 
                "message": f"Refreshed {refreshed_count} thumbnails"
            })
            
        except Exception as e:
            _LOGGER.error("Error refreshing thumbnails: %s", e)
            return web.json_response({"status": "error", "message": str(e)}, status=500)


class VideoloftCameraDiagnosticView(HomeAssistantView):
    """A view that provides camera diagnostic information."""

    url = "/api/videoloft/camera_diagnostic/{uidd}"
    name = "api:videoloft:camera_diagnostic"
    requires_auth = False

    def __init__(self, hass: HomeAssistant):
        self.hass = hass

    async def get(self, request: web.Request, uidd: str) -> web.Response:
        """Get camera diagnostic information."""
        try:
            # Get coordinator
            coordinator = None
            for entry_id, entry_data in self.hass.data.get(DOMAIN, {}).items():
                if "coordinator" in entry_data:
                    coordinator = entry_data["coordinator"]
                    break
            
            # Get device data
            device_data = get_device_data(self.hass, uidd)
            
            # Get camera entity
            camera_entity = None
            for entity in self.hass.data["camera"].entities:
                if getattr(entity, "uidd", None) == uidd:
                    camera_entity = entity
                    break
            
            diagnostic_info = {
                "uidd": uidd,
                "device_found": device_data is not None,
                "entity_found": camera_entity is not None,
                "coordinator_found": coordinator is not None,
                "cache_info": None,
                "entity_state": None,
                "last_error": None
            }
            
            if device_data:
                diagnostic_info["device_info"] = {
                    "name": device_data.get("phonename", "Unknown"),
                    "logger": device_data.get("logger", "Unknown"),
                    "uid": device_data.get("uid", "Unknown"),
                    "id": device_data.get("id", "Unknown")
                }
            
            if coordinator:
                cache_entry = coordinator._thumbnail_cache.get(uidd)
                if cache_entry:
                    diagnostic_info["cache_info"] = {
                        "cached": True,
                        "timestamp": cache_entry.get("timestamp").isoformat() if cache_entry.get("timestamp") else None,
                        "size": cache_entry.get("size", 0),
                        "data_type": str(type(cache_entry.get("data", None)))
                    }
                else:
                    diagnostic_info["cache_info"] = {"cached": False}
            
            if camera_entity:
                diagnostic_info["entity_state"] = {
                    "available": camera_entity.available,
                    "state": camera_entity.state,
                    "stream_url": getattr(camera_entity, "_stream_url", None),
                    "logger_server": getattr(camera_entity, "logger_server", None)
                }
            
            return web.json_response({"status": "success", "diagnostic": diagnostic_info})
                
        except Exception as e:
            _LOGGER.error("Error getting camera diagnostic for %s: %s", uidd, e)
            return web.json_response({"status": "error", "message": str(e)}, status=500)


class VideoloftThumbnailPreloadView(HomeAssistantView):
    """A view to preload all thumbnails."""

    url = "/api/videoloft/preload_thumbnails"
    name = "api:videoloft:preload_thumbnails"
    requires_auth = False

    def __init__(self, hass: HomeAssistant):
        self.hass = hass

    async def post(self, request: web.Request) -> web.Response:
        """Preload thumbnails for all cameras."""
        try:
            # Get coordinator
            coordinator = None
            for entry_id, entry_data in self.hass.data.get(DOMAIN, {}).items():
                if "coordinator" in entry_data:
                    coordinator = entry_data["coordinator"]
                    break
            
            if not coordinator:
                return web.json_response({"status": "error", "message": "Coordinator not found"}, status=404)
            
            # Start preload task in background
            self.hass.async_create_task(coordinator.preload_all_thumbnails())
            
            return web.json_response({
                "status": "success", 
                "message": "Thumbnail preload initiated"
            })
            
        except Exception as e:
            _LOGGER.error("Error starting thumbnail preload: %s", e)
            return web.json_response({"status": "error", "message": str(e)}, status=500)

class AIEventPreviewView(HomeAssistantView):
    """Preview AI processing events and enhanced token estimation."""
    
    url = "/api/videoloft/preview_ai_events"
    name = "api:videoloft:preview_ai_events"
    requires_auth = False
    
    def __init__(self, hass: HomeAssistant):
        """Initialize the view."""
        self.hass = hass
        super().__init__()
        _LOGGER.debug("Initialized Enhanced AIEventPreviewView")
    
    async def post(self, request: web.Request) -> web.Response:
        """Handle POST request to preview enhanced AI processing."""
        try:
            data = await request.json()
            _LOGGER.debug("Received enhanced AI preview request: %s", data)
            
            entry = get_entry(self.hass)
            if not entry:
                return web.json_response({"error": "Configuration not found"}, status=400)
                
            coordinator = self.hass.data[DOMAIN][entry.entry_id].get("coordinator")
            if not coordinator:
                return web.json_response({"error": "Coordinator not found"}, status=400)
            
            # Parse parameters
            selected_camera = data.get("camera", "").strip()
            start_date = data.get("start_date")
            end_date = data.get("end_date")
            start_time = data.get("start_time", 8)  # Default 8 AM
            end_time = data.get("end_time", 20)    # Default 8 PM
            
            if not start_date or not end_date:
                return web.json_response({"error": "Start and end dates required"}, status=400)
            
            # Get cameras to process
            cameras_to_process = []
            if selected_camera:
                cameras_to_process = [selected_camera]
            else:
                # Get all cameras
                cameras_info = self.hass.data[DOMAIN][entry.entry_id].get("devices", [])
                cameras_to_process = [f"{cam['uid']}.{cam['id']}" for cam in cameras_info]
            
            # Use enhanced cost estimation
            result = await coordinator.gemini_api.estimate_processing_cost(
                cameras_to_process, start_date, end_date, start_time, end_time
            )
            
            if "error" in result:
                return web.json_response(result, status=400)
            
            return web.json_response(result)
            
        except Exception as e:
            _LOGGER.error("Error in enhanced AI preview: %s", e)
            return web.json_response({"error": str(e)}, status=500)

class AIProgressView(HomeAssistantView):
    """Track enhanced AI processing progress."""
    
    url = "/api/videoloft/ai_progress/{task_id}"
    name = "api:videoloft:ai_progress"
    requires_auth = False
    
    def __init__(self, hass: HomeAssistant):
        """Initialize the view."""
        self.hass = hass
        super().__init__()
        _LOGGER.debug("Initialized Enhanced AIProgressView")
    
    async def get(self, request: web.Request) -> web.Response:
        """Get enhanced progress for a task."""
        try:
            task_id = request.match_info.get('task_id')
            if not task_id:
                return web.json_response({"error": "Task ID required"}, status=400)
            
            # Get progress from coordinator's Gemini API
            entry = get_entry(self.hass)
            if not entry:
                return web.json_response({"error": "Configuration not found"}, status=400)
                
            coordinator = self.hass.data[DOMAIN][entry.entry_id].get("coordinator")
            if not coordinator:
                return web.json_response({"error": "Coordinator not found"}, status=400)
            
            # Get progress data from Gemini API
            gemini_api = coordinator.gemini_api
            if not hasattr(gemini_api, '_ai_progress'):
                gemini_api._ai_progress = {}
            
            progress = gemini_api._ai_progress.get(task_id, {
                "processed": 0,
                "total": 0,
                "tokens_used": 0,
                "calls_remaining": 15,
                "status": "unknown",
                "message": "No progress data available",
                "current_camera": None
            })
            
            # Add additional computed fields
            if progress.get("start_time"):
                from datetime import datetime
                elapsed_seconds = (datetime.utcnow() - progress["start_time"]).total_seconds()
                progress["elapsed_time"] = elapsed_seconds
                
                # Calculate processing rate
                if elapsed_seconds > 0 and progress.get("processed", 0) > 0:
                    rate = progress["processed"] / (elapsed_seconds / 60)  # events per minute
                    progress["processing_rate"] = round(rate, 1)
                    
                    # Estimate remaining time
                    remaining = progress.get("total", 0) - progress.get("processed", 0)
                    if remaining > 0 and rate > 0:
                        time_remaining_minutes = remaining / rate
                        progress["time_remaining_minutes"] = round(time_remaining_minutes, 1)
            
            return web.json_response(progress)
            
        except Exception as e:
            _LOGGER.error("Error getting enhanced AI progress: %s", e)
            return web.json_response({"error": str(e)}, status=500)

class AIAnalysisView(HomeAssistantView):
    """Handle AI analysis processing."""

    url = "/api/videoloft/ai_analysis"
    name = "api:videoloft:ai_analysis"
    requires_auth = False

    def __init__(self, hass: HomeAssistant):
        self.hass = hass

    async def post(self, request: web.Request) -> web.Response:
        """Start AI analysis using the persisted Gemini API key if available."""
        try:
            data = await request.json()
            _LOGGER.debug("Received AI analysis request")
            
            entry = get_entry(self.hass)
            if not entry:
                return web.json_response({"error": "Configuration not found"}, status=400)
                
            coordinator = self.hass.data[DOMAIN][entry.entry_id].get("coordinator")
            if not coordinator:
                return web.json_response({"error": "Coordinator not found"}, status=400)

            # Extract parameters
            start_date = data.get("startDate")
            end_date = data.get("endDate")
            camera = data.get("camera", "")

            if not start_date or not end_date:
                return web.json_response({"error": "Start and end dates are required"}, status=400)

            # Ensure a Gemini key exists
            store = ApiKeyStore(self.hass)
            if not await store.async_has_key():
                return web.json_response({"error": "Gemini API key not configured"}, status=400)

            # Get cameras to process
            cameras_to_process = []
            if camera and camera != "all":
                cameras_to_process = [camera]
            else:
                # Get all cameras
                cameras_info = self.hass.data[DOMAIN][entry.entry_id].get("devices", [])
                cameras_to_process = [f"{cam['uid']}.{cam['id']}" for cam in cameras_info]

            if not cameras_to_process:
                _LOGGER.warning("No cameras found to process")
                return web.json_response({"error": "No cameras available"}, status=400)

            _LOGGER.info(f"AI analysis requested for {len(cameras_to_process)} cameras")

            # Convert date strings to datetime and restrict time to 6am-8pm
            from datetime import datetime
            try:
                # Handle date-only format (YYYY-MM-DD) from date inputs
                if 'T' in start_date:
                    start_dt = datetime.fromisoformat(start_date.replace('T', ' '))
                    end_dt = datetime.fromisoformat(end_date.replace('T', ' '))
                else:
                    # Parse date-only format and set default times
                    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
                    end_dt = datetime.strptime(end_date, "%Y-%m-%d")
            except ValueError as e:
                _LOGGER.error(f"Invalid date format: {e}")
                return web.json_response({"error": "Invalid date format"}, status=400)

            # Force time restriction to 6am-8pm (6-20 in 24h format)
            start_time = 6  # 6am
            end_time = 20   # 8pm

            _LOGGER.info(f"AI Analysis: Processing events between {start_time}:00 and {end_time}:00 for date range {start_date} to {end_date} (time restricted to business hours)")

            # Process events using the enhanced method with restricted time window
            result = await coordinator.gemini_api.process_ai_search_enhanced(
                cameras_to_process,
                start_dt.strftime("%Y-%m-%d"),
                end_dt.strftime("%Y-%m-%d"),
                start_time,
                end_time
            )

            if "error" in result:
                _LOGGER.error(f"AI analysis failed: {result['error']}")
                return web.json_response(result, status=400)

            return web.json_response({"success": True, "message": "Analysis started"})

        except json.JSONDecodeError:
            _LOGGER.error("Invalid JSON in AI analysis request")
            return web.json_response({"error": "Invalid JSON format"}, status=400)
        except Exception as e:
            _LOGGER.exception("Error in AI analysis")
            return web.json_response({"error": str(e)}, status=500)


class AISearchView(HomeAssistantView):
    """Handle AI search functionality."""

    url = "/api/videoloft/ai_search"
    name = "api:videoloft:ai_search"
    requires_auth = False

    def __init__(self, hass: HomeAssistant):
        self.hass = hass

    async def get_thumbnail_token(self, coordinator):
        """Get authentication token for thumbnail URLs."""
        try:
            if hasattr(coordinator, 'api') and coordinator.api:
                return await coordinator.api.get_token()
        except Exception as e:
            _LOGGER.warning(f"Failed to get thumbnail token: {e}")
        return ""

    async def post(self, request: web.Request) -> web.Response:
        """Handle POST request to search events using stored analysis data."""
        try:
            data = await request.json()
            _LOGGER.debug("Received AI search request")
            
            entry = get_entry(self.hass)
            if not entry:
                return web.json_response({"error": "Configuration not found"}, status=400)
                
            coordinator = self.hass.data[DOMAIN][entry.entry_id].get("coordinator")
            if not coordinator:
                return web.json_response({"error": "Coordinator not found"}, status=400)

            # Extract search query
            query = data.get("query", "").strip()
            if not query:
                return web.json_response({"error": "Search query is required"}, status=400)

            # Search through stored descriptions
            descriptions = await coordinator.async_load_descriptions()
            
            # If no descriptions exist, suggest running analysis first
            if not descriptions:
                _LOGGER.warning("No AI descriptions found - analysis needs to be run first")
                return web.json_response({
                    "success": False,
                    "error": "no_analysis",
                    "message": "No AI analysis has been run yet. Please run 'Analysis' first to process your camera footage with AI, then you can search.",
                    "events": [],
                    "total_count": 0
                })
            
            matching_events = []

            # Ensure we have a valid thumbnail token for constructing URLs
            thumb_token = await self.get_thumbnail_token(coordinator)

            query_lower = query.lower()
            for event_id, info in descriptions.items():
                description = info.get("description", "")
                if not description:
                    continue

                # Simple keyword matching
                if query_lower in description.lower():
                    # Get camera name
                    camera_uidd = info.get('uidd', '')
                    camera_name = "Unknown Camera"
                    
                    # Try to find camera name from devices
                    cameras_info = self.hass.data[DOMAIN][entry.entry_id].get("devices", [])
                    for camera_data in cameras_info:
                        if f"{camera_data['uid']}.{camera_data['id']}" == camera_uidd:
                            camera_name = camera_data.get("name", camera_data.get("phonename", f"Camera {camera_uidd}"))
                            break

                    # Create event result
                    event_result = {
                        "event_id": event_id,
                        "description": description,
                        "camera_name": camera_name,
                        "timestamp": info.get("startt"),
                        "confidence": 0.8,  # Static confidence for now
                        "url": f"https://app.videoloft.com/cameras/{camera_uidd}?uidd={camera_uidd}&eventId={event_id}&logger={info.get('logger_server', '')}&startTime={info.get('startt', 0)}",
                        "thumbnail": f"https://{info.get('logger_server', '')}/alertthumb/{camera_uidd}/{event_id}/{thumb_token}"
                    }
                    matching_events.append(event_result)

            # Sort by timestamp (newest first)
            matching_events.sort(key=lambda x: x.get("timestamp", 0), reverse=True)

            _LOGGER.debug(f"Found {len(matching_events)} matching events for query '{query}'")

            return web.json_response({
                "success": True,
                "events": matching_events,
                "total_count": len(matching_events)
            })

        except json.JSONDecodeError:
            _LOGGER.error("Invalid JSON in AI search request")
            return web.json_response({"error": "Invalid JSON format"}, status=400)
        except Exception as e:
            _LOGGER.exception("Error in AI search")
            return web.json_response({"error": str(e)}, status=500)


class GeminiQuotaView(HomeAssistantView):
    """View for managing Gemini API quota."""

    url = "/api/videoloft/gemini_quota"
    name = "api:videoloft:gemini_quota"
    requires_auth = True

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the view."""
        self.hass = hass

    async def get(self, request: web.Request) -> web.Response:
        """Get quota status."""
        try:
            entry_id = list(self.hass.data[DOMAIN].keys())[0]
            coordinator = self.hass.data[DOMAIN][entry_id]["coordinator"]
            
            quota_status = await coordinator.get_gemini_quota_status()
            return web.json_response(quota_status)
            
        except Exception as e:
            _LOGGER.error(f"Error getting quota status: {e}")
            return web.json_response({"error": str(e)}, status=500)

    async def post(self, request: web.Request) -> web.Response:
        """Manage quota operations."""
        try:
            data = await request.json()
            action = data.get("action")
            
            entry_id = list(self.hass.data[DOMAIN].keys())[0]
            coordinator = self.hass.data[DOMAIN][entry_id]["coordinator"]
            
            if action == "reset_quota":
                result = await coordinator.reset_gemini_quota_state()
                return web.json_response(result)
            elif action == "reset_circuit_breaker":
                result = await coordinator.force_circuit_breaker_reset()
                return web.json_response(result)
            else:
                return web.json_response({"error": "Invalid action"}, status=400)
                
        except json.JSONDecodeError:
            return web.json_response({"error": "Invalid JSON format"}, status=400)
        except Exception as e:
            _LOGGER.error(f"Error in quota management: {e}")
            return web.json_response({"error": str(e)}, status=500)


class GlobalStreamStateView(HomeAssistantView):
    """Handle global streaming state management."""

    url = "/api/videoloft/global_stream_state"
    name = "api:videoloft:global_stream_state"
    requires_auth = False

    def __init__(self, hass: HomeAssistant):
        self.hass = hass
        self._state_store = GlobalStreamStateStore(hass)

    async def get(self, request: web.Request) -> web.Response:
        """Handle GET request to retrieve current streaming state."""
        try:
            # Load current state from storage
            state = await self._state_store.async_load()
            
            # Get camera count and actual streaming status
            entry = get_entry(self.hass)
            total_cameras = 0
            active_streams = 0
            
            if entry:
                cameras_info = self.hass.data[DOMAIN][entry.entry_id].get("devices", [])
                total_cameras = len(cameras_info)
                
                # Count actually active streams by checking camera entities
                camera_entities = []
                # Get camera entities from the entity registry
                from homeassistant.helpers import entity_registry as er
                entity_registry = er.async_get(self.hass)
                
                for entity_entry in entity_registry.entities.values():
                    if (entity_entry.domain == "camera" and 
                        entity_entry.platform == DOMAIN):
                        # Get the actual entity instance
                        entity_id = entity_entry.entity_id
                        camera_entity = self.hass.states.get(entity_id)
                        if camera_entity and not getattr(camera_entity, '_streaming_paused', False):
                            active_streams += 1
                
                # If global streaming is disabled, active streams should be 0
                if not state.get("enabled", True):
                    active_streams = 0
            
            response_data = {
                "enabled": state.get("enabled", True),
                "total_cameras": total_cameras,
                "active_streams": active_streams,
                "last_updated": state.get("last_updated")
            }
            
            return web.json_response(response_data)
            
        except Exception as e:
            _LOGGER.error("Error getting global stream state: %s", e)
            return web.json_response({"error": str(e)}, status=500)

    async def post(self, request: web.Request) -> web.Response:
        """Handle POST request to update streaming state."""
        try:
            data = await request.json()
            enabled = data.get("enabled")
            
            if enabled is None:
                return web.json_response({"error": "'enabled' parameter is required"}, status=400)
            
            if not isinstance(enabled, bool):
                return web.json_response({"error": "'enabled' must be a boolean"}, status=400)
            
            # Update state
            state = {
                "enabled": enabled,
                "last_updated": datetime.utcnow().isoformat()
            }
            
            # Save to storage
            await self._state_store.async_save(state)
            
            # **CONTROL ACTUAL CAMERA STREAMING TASKS**
            await self._control_camera_streaming(enabled)
            
            # Get camera count for response
            entry = get_entry(self.hass)
            total_cameras = 0
            active_streams = 0
            
            if entry:
                cameras_info = self.hass.data[DOMAIN][entry.entry_id].get("devices", [])
                total_cameras = len(cameras_info)
                if enabled:
                    active_streams = total_cameras
            
            response_data = {
                "enabled": enabled,
                "total_cameras": total_cameras,
                "active_streams": active_streams,
                "last_updated": state["last_updated"]
            }
            
            _LOGGER.info("Global streaming state updated: enabled=%s, cameras controlled=%d", enabled, total_cameras)
            return web.json_response(response_data)
            
        except json.JSONDecodeError:
            return web.json_response({"error": "Invalid JSON format"}, status=400)
        except Exception as e:
            _LOGGER.error("Error updating global stream state: %s", e)
            return web.json_response({"error": str(e)}, status=500)
    
    async def _control_camera_streaming(self, enabled: bool) -> None:
        """Control actual camera streaming tasks based on global state."""
        try:
            # Get all camera entities using the entity registry
            from homeassistant.helpers import entity_registry as er
            entity_registry = er.async_get(self.hass)
            
            camera_entities = []
            for entity_entry in entity_registry.entities.values():
                if (entity_entry.domain == "camera" and 
                    entity_entry.platform == DOMAIN):
                    # Get the actual entity instance from the entity component
                    camera_component = self.hass.data.get("camera")
                    if camera_component:
                        entity = camera_component.get_entity(entity_entry.entity_id)
                        if entity and hasattr(entity, "uidd"):
                            camera_entities.append(entity)
            
            if not camera_entities:
                _LOGGER.warning("No Videoloft camera entities found for streaming control")
                return
            
            _LOGGER.info(f"Controlling streaming for {len(camera_entities)} cameras: enabled={enabled}")
            
            # Control each camera's streaming
            control_tasks = []
            for camera in camera_entities:
                if enabled:
                    # Resume streaming
                    control_tasks.append(camera.resume_streaming())
                else:
                    # Pause streaming  
                    control_tasks.append(camera.pause_streaming())
            
            # Execute all control tasks concurrently
            if control_tasks:
                await asyncio.gather(*control_tasks, return_exceptions=True)
                _LOGGER.info(f"Streaming control completed for {len(control_tasks)} cameras")
            
        except Exception as e:
            _LOGGER.error(f"Error controlling camera streaming: {e}")
