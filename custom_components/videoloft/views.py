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

from .api import VideoloftAPI
from .const import DOMAIN
from homeassistant.components.websocket_api import (
    async_register_command,
    WebSocketCommandHandler,
    websocket_command,
)

_LOGGER = logging.getLogger(__name__)


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

    devices = hass.data[DOMAIN][entry.entry_id].get("devices", {})
    try:
        owner_uid, device_uid = uidd.split('.')
        return devices.get("result", {}).get(owner_uid, {}).get("devices", {}).get(device_uid)
    except ValueError:
        _LOGGER.error("Invalid UIDD format: '%s'. Expected 'owner_uid.device_uid'.", uidd)
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

        devices = self.hass.data[DOMAIN][entry.entry_id].get("devices", {})
        cameras = [
            {
                "uidd": f"{owner_uid}.{device_uid}",
                "name": device_data.get("phonename", f"Camera {owner_uid}.{device_uid}"),
                "model": device_data.get("model", "Unknown Model"),
                "resolution": device_data.get("recordingResolution", "Unknown"),
            }
            for owner_uid, owner_data in devices.get("result", {}).items()
            for device_uid, device_data in owner_data.get("devices", {}).items()
        ]

        _LOGGER.debug("Fetched %d cameras.", len(cameras))
        return web.json_response({"cameras": cameras})


class VideoloftThumbnailView(HomeAssistantView):
    """A view that returns the latest thumbnail image for a camera."""

    url = "/api/videoloft/thumbnail/{uidd}"
    name = "api:videoloft:thumbnail"
    requires_auth = False

    def __init__(self, hass: HomeAssistant):
        self.hass = hass

    async def get(self, request: web.Request, uidd: str) -> web.Response:
        """Handle the GET request for the thumbnail image."""
        device_data = get_device_data(self.hass, uidd)
        if not device_data:
            return web.Response(status=404)

        api: VideoloftAPI = self.hass.data[DOMAIN][get_entry(self.hass).entry_id]["api"]
        logger_server = device_data.get("logger")

        try:
            image_data = await api.get_camera_thumbnail(uidd, logger_server)
            return web.Response(body=image_data, content_type='image/jpeg')
        except Exception as e:
            _LOGGER.error("Error fetching thumbnail for %s: %s", uidd, e)
            return web.Response(status=500)


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

class OpenAIKeyView(HomeAssistantView):
    """Handle OpenAI API key management."""

    url = "/api/videoloft/openai_key"
    name = "api:videoloft:openai_key"
    requires_auth = False

    def __init__(self, hass: HomeAssistant):
        self.hass = hass

    async def post(self, request: web.Request) -> web.Response:
        """Handle POST request to save OpenAI API key."""
        try:
            data = await request.json()
            api_key = data.get("api_key")

            if not api_key:
                return web.json_response({"error": "API key is required."}, status=400)

            # Securely save the API key
            self.hass.data[DOMAIN]["openai_api_key"] = api_key
            _LOGGER.info("OpenAI API key saved successfully.")
            return web.json_response({"success": True}, status=201)
        except json.JSONDecodeError:
            _LOGGER.error("Invalid JSON format in OpenAI API key POST request.")
            return web.json_response({"error": "Invalid JSON format."}, status=400)
        except Exception as e:
            _LOGGER.error("Error saving OpenAI API key: %s", e)
            return web.json_response({"error": str(e)}, status=500)

    async def delete(self, request: web.Request) -> web.Response:
        """Handle DELETE request to remove OpenAI API key."""
        try:
            self.hass.data[DOMAIN]["openai_api_key"] = None
            _LOGGER.info("OpenAI API key removed successfully.")
            return web.json_response({"success": True}, status=200)
        except Exception as e:
            _LOGGER.error("Error removing OpenAI API key: %s", e)
            return web.json_response({"error": str(e)}, status=500)

    async def get(self, request: web.Request) -> web.Response:
        """Handle GET request to check if OpenAI API key exists."""
        try:
            has_key = bool(self.hass.data[DOMAIN].get("openai_api_key"))
            return web.json_response({"has_key": has_key}, status=200)
        except Exception as e:
            _LOGGER.error("Error checking OpenAI API key: %s", e)
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
            if not api_key:
                _LOGGER.error("OpenAI API key not set.")
                return web.json_response({"error": "OpenAI API key not set."}, status=400)

            try:
                data = await request.json()
                selected_cameras: List[str] = data.get("cameras", [])
            except json.JSONDecodeError:
                _LOGGER.error("Invalid JSON format in process_events POST request.")
                return web.json_response({"error": "Invalid JSON format."}, status=400)

            if not selected_cameras:
                devices = self.hass.data[DOMAIN][entry.entry_id].get("devices", {})
                selected_cameras = [
                    f"{owner_uid}.{device_uid}"
                    for owner_uid, owner_data in devices.get("result", {}).items()
                    for device_uid in owner_data.get("devices", {}).keys()
                ]

            if not selected_cameras:
                _LOGGER.warning("No cameras available to process events.")
                return web.json_response({"error": "No cameras available to process events."}, status=400)

            # Start the AI Search task asynchronously
            asyncio.create_task(coordinator.process_events(api_key, selected_cameras))
            _LOGGER.info("AI Search task initiated for cameras: %s", selected_cameras)
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
    """Handle AI Search tasks."""
    
    url = "/api/videoloft/process_ai_search"
    name = "api:videoloft:process_ai_search"
    requires_auth = False
    
    def __init__(self, hass: HomeAssistant):
        """Initialize the view."""
        self.hass = hass
        super().__init__()
        _LOGGER.debug("Initialized AISearchProcessView")
    
    async def post(self, request: web.Request) -> web.Response:
        """Handle POST request to initiate AI Search task."""
        try:
            data = await request.json()
            _LOGGER.debug("Received AI Search request: %s", data)
            
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
                
            selected_camera = data.get("camera", "").strip()
            _LOGGER.debug("Processing AI Search for camera: %s", selected_camera)
            
            await coordinator.process_ai_search(
                [selected_camera] if selected_camera else []
            )
            
            return web.json_response({
                "success": True, 
                "message": "AI Search task initiated"
            })
            
        except Exception as e:
            _LOGGER.exception("AI Search process error")
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