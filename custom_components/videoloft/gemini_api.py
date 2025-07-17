"""Google Gemini AI integration for Videoloft surveillance image analysis."""
import base64
import asyncio
import logging
import re
import json
import time
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers import storage
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

# ----------------------------------------------------------
# QUOTA TRACKING CLASS
# ----------------------------------------------------------

class GeminiQuotaTracker:
    """Track and manage Gemini API quota usage and rate limits."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self._lock = asyncio.Lock()
        self._request_times = []
        self._daily_requests = 0
        self._daily_reset_time = None
        self._circuit_breaker_until = None
        self.DAILY_LIMIT = 200
        self.MINUTE_LIMIT = 10
        self.WINDOW_SECONDS = 60

    async def load_quota_state(self) -> None:
        """Load quota state from storage."""
        store = storage.Store(self.hass, 1, f"{DOMAIN}_quota_state")
        try:
            data = await store.async_load() or {}
            self._daily_requests = data.get("daily_requests", 0)
            self._daily_reset_time = data.get("daily_reset_time")
            
            if data.get("circuit_breaker_until"):
                self._circuit_breaker_until = datetime.fromisoformat(data["circuit_breaker_until"])
            
            # Reset daily count if it's a new day
            if self._daily_reset_time:
                reset_time = datetime.fromisoformat(self._daily_reset_time)
                if datetime.utcnow() >= reset_time:
                    self._daily_requests = 0
                    self._daily_reset_time = None
        except Exception as e:
            _LOGGER.error(f"Error loading quota state: {e}")

    async def save_quota_state(self) -> None:
        """Save quota state to storage."""
        store = storage.Store(self.hass, 1, f"{DOMAIN}_quota_state")
        try:
            data = {
                "daily_requests": self._daily_requests,
                "daily_reset_time": self._daily_reset_time,
                "circuit_breaker_until": self._circuit_breaker_until.isoformat() if self._circuit_breaker_until else None,
                "last_updated": datetime.utcnow().isoformat()
            }
            await store.async_save(data)
        except Exception as e:
            _LOGGER.error(f"Error saving quota state: {e}")

    async def check_request_allowed(self) -> tuple[bool, str]:
        """Check if a request is allowed based on current quota and rate limits."""
        async with self._lock:
            now = datetime.utcnow()
            
            # Check circuit breaker
            if self._circuit_breaker_until and now < self._circuit_breaker_until:
                remaining = (self._circuit_breaker_until - now).total_seconds()
                return False, f"Circuit breaker active for {remaining:.0f} more seconds"
            
            # Reset circuit breaker if expired
            if self._circuit_breaker_until and now >= self._circuit_breaker_until:
                self._circuit_breaker_until = None
                await self.save_quota_state()
            
            # Check daily quota
            if self._daily_requests >= self.DAILY_LIMIT:
                return False, f"Daily quota exhausted ({self._daily_requests}/{self.DAILY_LIMIT})"
            
            # Check rate limit
            current_time = time.time()
            self._request_times = [t for t in self._request_times if current_time - t < self.WINDOW_SECONDS]
            
            if len(self._request_times) >= self.MINUTE_LIMIT:
                oldest_request = min(self._request_times)
                wait_time = self.WINDOW_SECONDS - (current_time - oldest_request)
                return False, f"Rate limit reached, wait {wait_time:.1f} seconds"
            
            return True, "Request allowed"

    async def record_request(self) -> None:
        """Record a successful API request."""
        async with self._lock:
            self._request_times.append(time.time())
            self._daily_requests += 1
            
            if not self._daily_reset_time:
                tomorrow = datetime.utcnow() + timedelta(days=1)
                self._daily_reset_time = tomorrow.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
            
            await self.save_quota_state()

    async def handle_429_error(self, error_response: Dict[str, Any]) -> int:
        """Handle 429 error and return retry delay in seconds."""
        async with self._lock:
            retry_delay = 60  # Default 1 minute
            
            try:
                details = error_response.get("error", {}).get("details", [])
                for detail in details:
                    if detail.get("@type") == "type.googleapis.com/google.rpc.RetryInfo":
                        retry_delay_str = detail.get("retryDelay", "")
                        if retry_delay_str.endswith("s"):
                            retry_delay = int(retry_delay_str[:-1])
                        elif retry_delay_str.isdigit():
                            retry_delay = int(retry_delay_str)
            except Exception:
                pass
            
            self._circuit_breaker_until = datetime.utcnow() + timedelta(seconds=retry_delay)
            await self.save_quota_state()
            return retry_delay

    def get_quota_status(self) -> Dict[str, Any]:
        """Get current quota status."""
        now = datetime.utcnow()
        current_time = time.time()
        
        self._request_times = [t for t in self._request_times if current_time - t < self.WINDOW_SECONDS]
        
        circuit_breaker_remaining = 0
        if self._circuit_breaker_until and now < self._circuit_breaker_until:
            circuit_breaker_remaining = (self._circuit_breaker_until - now).total_seconds()
        
        return {
            "daily_requests": self._daily_requests,
            "daily_limit": self.DAILY_LIMIT,
            "daily_remaining": max(0, self.DAILY_LIMIT - self._daily_requests),
            "minute_requests": len(self._request_times),
            "minute_limit": self.MINUTE_LIMIT,
            "minute_remaining": max(0, self.MINUTE_LIMIT - len(self._request_times)),
            "circuit_breaker_active": circuit_breaker_remaining > 0,
            "circuit_breaker_remaining": circuit_breaker_remaining,
            "daily_reset_time": self._daily_reset_time
        }

# ----------------------------------------------------------
# MAIN GEMINI API CLASS
# ----------------------------------------------------------

class GeminiAPI:
    """Handle Google Gemini AI API interactions for image analysis."""

    def __init__(self, hass: HomeAssistant, api_handler) -> None:
        self.hass = hass
        self.api = api_handler
        self.quota_tracker = GeminiQuotaTracker(hass)
        self._ai_progress = {}
        
    async def initialize(self) -> None:
        """Initialize the API handler and load quota state."""
        await self.quota_tracker.load_quota_state()

    async def process_ai_search(self, selected_cameras: List[str]) -> None:
        """Process events and get descriptions from Google Gemini."""
        api_key = self.hass.data[DOMAIN].get("gemini_api_key")
        if not api_key:
            _LOGGER.error("Google Gemini API key not set.")
            return

        await self.quota_tracker.load_quota_state()
        quota_status = self.quota_tracker.get_quota_status()
        
        if quota_status["daily_remaining"] <= 0 or quota_status["circuit_breaker_active"]:
            _LOGGER.warning("Cannot process AI search due to quota limits")
            return

        descriptions = await self.async_load_descriptions()
        events_processed = 0
        now = datetime.utcnow()
        start_time = int((now - timedelta(days=5)).replace(hour=0, minute=0, second=0, microsecond=0).timestamp() * 1000)
        end_time = int(now.timestamp() * 1000)

        for camera_uidd in selected_cameras:
            try:
                logger_server = await self.api.get_logger_server(camera_uidd)
                if not logger_server:
                    continue

                events = await self.api.get_recent_events_paginated(logger_server, camera_uidd, start_time, end_time)
                if not events:
                    continue

                # Filter events (6am-8pm, no existing descriptions)
                filtered_events = []
                for event in events:
                    event_id = event.get("alert")
                    if not event_id or event_id in descriptions:
                        continue
                    
                    event_ts = event.get('startt')
                    if event_ts:
                        dt_utc = datetime.utcfromtimestamp(event_ts / 1000)
                        if not (6 <= dt_utc.hour < 20):
                            continue
                    
                    filtered_events.append(event)

                # Process events with quota checking
                for event in filtered_events:
                    quota_status = self.quota_tracker.get_quota_status()
                    if quota_status["daily_remaining"] <= 0 or quota_status["circuit_breaker_active"]:
                        break
                    
                    if quota_status["minute_remaining"] <= 0:
                        await asyncio.sleep(60)
                        continue

                    event_id = event.get("alert")
                    try:
                        image_data = await self.api.download_event_thumbnail(logger_server, camera_uidd, event_id)
                        if not image_data:
                            continue
                            
                        description = await self.get_gemini_description(image_data, api_key)
                        description = self._clean_description(description)
                        
                        if description:
                            descriptions[event_id] = {
                                'description': description,
                                'uidd': camera_uidd,
                                'logger_server': logger_server,
                                'startt': event.get('startt')
                            }
                            events_processed += 1
                            await self.async_save_descriptions(descriptions)
                            
                    except Exception as e:
                        _LOGGER.error(f"Error processing event {event_id}: {e}")
                        continue

            except Exception as e:
                _LOGGER.error(f"Error processing camera {camera_uidd}: {e}")
                continue

        _LOGGER.info(f"Processed {events_processed} new events")

    async def get_gemini_description(self, image_bytes: bytes, api_key: str, max_retries: int = 3) -> Optional[str]:
        """Get description from Google Gemini API with retry logic."""
        for attempt in range(max_retries + 1):
            try:
                allowed, reason = await self.quota_tracker.check_request_allowed()
                if not allowed:
                    _LOGGER.warning(f"Request blocked: {reason}")
                    return None

                base64_image = base64.b64encode(image_bytes).decode('utf-8')
                url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"
                
                data = {
                    "contents": [{
                        "parts": [
                            {"inline_data": {"mime_type": "image/jpeg", "data": base64_image}},
                            {"text": self._get_analysis_prompt()}
                        ]
                    }]
                }

                async with aiohttp.ClientSession() as session:
                    async with session.post(f"{url}?key={api_key}", json=data) as response:
                        if response.status == 200:
                            result = await response.json()
                            description = result["candidates"][0]["content"]["parts"][0]["text"]
                            await self.quota_tracker.record_request()
                            return description
                            
                        elif response.status == 429:
                            error_data = await response.json()
                            retry_delay = await self.quota_tracker.handle_429_error(error_data)
                            
                            if attempt < max_retries:
                                await asyncio.sleep(retry_delay)
                                continue
                            return None
                            
                        elif response.status in [500, 502, 503, 504] and attempt < max_retries:
                            await asyncio.sleep(2 ** attempt)
                            continue
                        else:
                            error_text = await response.text()
                            _LOGGER.error(f"Gemini API error: {response.status} - {error_text}")
                            return None
                            
            except Exception as e:
                _LOGGER.error(f"Error in get_gemini_description (attempt {attempt + 1}): {e}")
                if attempt < max_retries:
                    await asyncio.sleep(2 ** attempt)
                    continue
                return None
        
        return None

    def _get_analysis_prompt(self) -> str:
        """Get prompt for CCTV image analysis."""
        return (
            "Analyze this CCTV footage image with maximum detail for security purposes. "
            "Provide a comprehensive, factual description in ONE detailed paragraph. "
            "Include ALL observable details about people (gender, age, clothing, actions), "
            "vehicles (make, model, color, license plates), objects, environment, "
            "time of day, weather, and specific actions being performed. "
            "Use specific, searchable terms. Only describe what is clearly visible. "
            "Do not use headings, bullet points, or markdown formatting."
        )

    def _clean_description(self, description: Optional[str]) -> Optional[str]:
        """Clean the AI-generated description."""
        if not description:
            return None

        # Remove markdown formatting and common prefixes
        desc = re.sub(r'\*\*(.*?):\*\*', '', description).strip()
        
        prefixes = [
            "here's a description of the surveillance image:",
            "description of the surveillance image:",
            "analyzing this cctv footage image:",
            "the cctv image shows:",
            "this surveillance image depicts:"
        ]
        
        for prefix in prefixes:
            if desc.lower().startswith(prefix):
                desc = desc[len(prefix):].lstrip(' .:').strip()
        
        desc = desc.lstrip(' .:').strip()
        desc = re.sub(r'^(the image shows|this shows|the scene depicts)\s*:?\s*', '', desc, flags=re.IGNORECASE)
        
        if desc and desc[0].islower():
            desc = desc[0].upper() + desc[1:]

        return desc

    async def async_load_descriptions(self) -> Dict[str, Any]:
        """Load stored descriptions from storage."""
        store = storage.Store(self.hass, 1, f"{DOMAIN}_descriptions")
        try:
            return await store.async_load() or {}
        except Exception as e:
            _LOGGER.error(f"Error loading descriptions: {e}")
            return {}

    async def async_save_descriptions(self, descriptions: Dict[str, Any]) -> None:
        """Save descriptions to storage."""
        store = storage.Store(self.hass, 1, f"{DOMAIN}_descriptions")
        try:
            await store.async_save(descriptions)
        except Exception as e:
            _LOGGER.error(f"Error saving descriptions: {e}")

    async def clear_descriptions(self) -> None:
        """Clear all stored event descriptions."""
        try:
            store = storage.Store(self.hass, 1, f"{DOMAIN}_descriptions")
            await store.async_save({})
            _LOGGER.info("All event descriptions cleared.")
        except Exception as e:
            _LOGGER.error(f"Error clearing descriptions: {e}")

    async def search_descriptions(self, query: str) -> List[Dict[str, Any]]:
        """Search through stored descriptions for matches."""
        descriptions = await self.async_load_descriptions()
        results = []
        
        query_lower = query.lower()
        for event_id, data in descriptions.items():
            description = data.get('description', '').lower()
            if query_lower in description:
                results.append({
                    'event_id': event_id,
                    'description': data.get('description'),
                    'camera_uidd': data.get('uidd'),
                    'logger_server': data.get('logger_server'),
                    'timestamp': data.get('startt')
                })
        
        return results

    async def process_ai_search_enhanced(self, selected_cameras: List[str], start_date: str, end_date: str, 
                                       start_time: int = 8, end_time: int = 20) -> Dict[str, Any]:
        """Enhanced AI search processing with progress tracking."""
        api_key = self.hass.data[DOMAIN].get("gemini_api_key")
        if not api_key:
            return {"error": "API key not configured"}

        import uuid
        task_id = str(uuid.uuid4())
        
        self._ai_progress[task_id] = {
            "processed": 0, "total": 0, "status": "initializing",
            "message": "Preparing to process events...", "start_time": datetime.utcnow()
        }

        try:
            start_dt = datetime.strptime(f"{start_date} {start_time:02d}:00:00", "%Y-%m-%d %H:%M:%S")
            end_dt = datetime.strptime(f"{end_date} {end_time:02d}:59:59", "%Y-%m-%d %H:%M:%S")
            
            start_time_ms = int(start_dt.timestamp() * 1000)
            end_time_ms = int(end_dt.timestamp() * 1000)

            asyncio.create_task(self._process_cameras_background(
                task_id, selected_cameras, start_time_ms, end_time_ms, start_time, end_time, api_key
            ))
            
            return {"task_id": task_id, "status": "started"}
            
        except Exception as e:
            self._ai_progress[task_id] = {"status": "error", "message": f"Failed to start: {e}"}
            return {"error": str(e)}

    async def _process_cameras_background(self, task_id: str, selected_cameras: List[str], 
                                        start_time_ms: int, end_time_ms: int, start_hour: int, 
                                        end_hour: int, api_key: str):
        """Background processing of cameras."""
        _LOGGER.info(f"AI Analysis Background: Starting processing for {len(selected_cameras)} cameras")
        _LOGGER.info(f"AI Analysis Background: Time range {start_time_ms} to {end_time_ms}")
        
        await self.quota_tracker.load_quota_state()
        descriptions = await self.async_load_descriptions()
        total_processed = 0
        
        try:
            # Get all events first
            all_events = []
            for camera_uidd in selected_cameras:
                try:
                    _LOGGER.info(f"AI Analysis Background: Processing camera {camera_uidd}")
                    logger_server = await self.api.get_logger_server(camera_uidd)
                    if not logger_server:
                        _LOGGER.warning(f"AI Analysis Background: No logger server found for camera {camera_uidd}")
                        continue

                    _LOGGER.info(f"AI Analysis Background: Found logger server {logger_server} for camera {camera_uidd}")
                    events = await self.api.get_recent_events_paginated(
                        logger_server, camera_uidd, start_time_ms, end_time_ms
                    )

                    _LOGGER.info(f"AI Analysis Background: Found {len(events) if events else 0} events for camera {camera_uidd}")
                    
                    if events:
                        filtered_events = []
                        for event in events:
                            event_id = event.get("alert")
                            if event_id and event_id not in descriptions:
                                filtered_events.append((event, camera_uidd, logger_server))
                        
                        _LOGGER.info(f"AI Analysis Background: {len(filtered_events)} events remain after filtering for camera {camera_uidd} (removed {len(events) - len(filtered_events)} already processed)")
                        all_events.extend(filtered_events)
                        
                except Exception as e:
                    _LOGGER.warning(f"Failed to get events for camera {camera_uidd}: {e}")
                    continue

            total_events = len(all_events)
            _LOGGER.info(f"AI Analysis Background: Total events to process: {total_events}")
            
            self._ai_progress[task_id].update({
                "total": total_events, "status": "processing",
                "message": f"Processing {total_events} events..."
            })

            if total_events == 0:
                _LOGGER.info("AI Analysis Background: No events found to process")
                self._ai_progress[task_id].update({
                    "status": "completed", "message": "No events found in the specified time range"
                })
                return

            # Process events
            _LOGGER.info(f"AI Analysis Background: Starting to process {total_events} events")
            for i, (event, camera_uidd, logger_server) in enumerate(all_events):
                try:
                    _LOGGER.info(f"AI Analysis Background: Processing event {i+1}/{total_events} from camera {camera_uidd}")
                    
                    quota_status = self.quota_tracker.get_quota_status()
                    _LOGGER.debug(f"AI Analysis Background: Quota status - daily remaining: {quota_status.get('daily_remaining', 'unknown')}")
                    
                    self._ai_progress[task_id].update({
                        "processed": total_processed, "current_camera": camera_uidd,
                        "message": f"Processing event {i+1}/{total_events} from {camera_uidd}"
                    })
                    
                    if quota_status["daily_remaining"] <= 0:
                        _LOGGER.warning(f"AI Analysis Background: Daily quota exhausted after processing {total_processed} events")
                        self._ai_progress[task_id].update({
                            "status": "quota_exhausted",
                            "message": f"Daily quota exhausted after processing {total_processed} events"
                        })
                        break
                    
                    if quota_status["circuit_breaker_active"]:
                        _LOGGER.info(f"AI Analysis Background: Circuit breaker active, waiting {quota_status['circuit_breaker_remaining']} seconds")
                        await asyncio.sleep(quota_status["circuit_breaker_remaining"] + 1)
                        continue
                    
                    if quota_status["minute_remaining"] <= 0:
                        _LOGGER.info("AI Analysis Background: Minute quota exhausted, waiting 60 seconds")
                        await asyncio.sleep(60)
                        continue

                    event_id = event.get("alert")
                    if not event_id:
                        _LOGGER.warning(f"AI Analysis Background: Event has no alert ID, skipping")
                        continue
                    
                    _LOGGER.info(f"AI Analysis Background: Downloading thumbnail for event {event_id}")
                    image_data = await self.api.download_event_thumbnail(logger_server, camera_uidd, event_id)
                    if not image_data:
                        _LOGGER.warning(f"AI Analysis Background: Failed to download thumbnail for event {event_id}")
                        continue

                    _LOGGER.info(f"AI Analysis Background: Getting Gemini description for event {event_id}")
                    description = await self.get_gemini_description(image_data, api_key)
                    description = self._clean_description(description)
                    
                    if description:
                        _LOGGER.info(f"AI Analysis Background: Successfully processed event {event_id}")
                        descriptions[event_id] = {
                            'description': description, 'uidd': camera_uidd,
                            'logger_server': logger_server, 'startt': event.get('startt')
                        }
                        
                        await self.async_save_descriptions(descriptions)
                        total_processed += 1
                        self._ai_progress[task_id].update({"processed": total_processed})
                    else:
                        _LOGGER.warning(f"AI Analysis Background: Empty description returned for event {event_id}")

                except Exception as e:
                    _LOGGER.warning(f"Failed to process event {event.get('alert', 'unknown')}: {e}")
                    continue

            _LOGGER.info(f"AI Analysis Background: Processing complete - {total_processed} events processed successfully")
            self._ai_progress[task_id].update({
                "status": "completed", "message": f"Successfully processed {total_processed} events"
            })

        except Exception as e:
            _LOGGER.error(f"AI Analysis Background: Processing failed with error: {e}")
            self._ai_progress[task_id].update({"status": "error", "message": f"Processing failed: {e}"})

    async def estimate_processing_cost(self, selected_cameras: List[str], start_date: str, end_date: str, 
                                     start_time: int = 8, end_time: int = 20) -> Dict[str, Any]:
        """Estimate the cost and time for AI processing."""
        try:
            start_dt = datetime.strptime(f"{start_date} {start_time:02d}:00:00", "%Y-%m-%d %H:%M:%S")
            end_dt = datetime.strptime(f"{end_date} {end_time:02d}:59:59", "%Y-%m-%d %H:%M:%S")
            
            start_time_ms = int(start_dt.timestamp() * 1000)
            end_time_ms = int(end_dt.timestamp() * 1000)

            descriptions = await self.async_load_descriptions()
            total_events = 0

            for camera_uidd in selected_cameras:
                try:
                    logger_server = await self.api.get_logger_server(camera_uidd)
                    if not logger_server:
                        continue

                    events = await self.api.get_recent_events_paginated(
                        logger_server, camera_uidd, start_time_ms, end_time_ms
                    )

                    if events:
                        filtered_count = sum(1 for event in events 
                                           if event.get("alert") and event.get("alert") not in descriptions)
                        total_events += filtered_count

                except Exception as e:
                    _LOGGER.warning(f"Failed to count events for camera {camera_uidd}: {e}")
                    continue

            return {
                "event_count": total_events,
                "estimated_tokens": total_events * 650,
                "estimated_time_minutes": max(1, total_events / 15),
                "cameras_count": len(selected_cameras),
                "date_range": f"{start_date} to {end_date}",
                "time_range": f"{start_time:02d}:00 to {end_time:02d}:59"
            }

        except Exception as e:
            return {"event_count": 0, "estimated_tokens": 0, "estimated_time_minutes": 0, "error": str(e)}

    async def get_quota_status(self) -> Dict[str, Any]:
        """Get current Gemini API quota status."""
        await self.quota_tracker.load_quota_state()
        return self.quota_tracker.get_quota_status()

    async def reset_quota_state(self) -> Dict[str, Any]:
        """Reset quota state."""
        self.quota_tracker._daily_requests = 0
        self.quota_tracker._daily_reset_time = None
        self.quota_tracker._circuit_breaker_until = None
        self.quota_tracker._request_times = []
        await self.quota_tracker.save_quota_state()
        return {"status": "reset", "message": "Quota state has been reset"}

    async def force_circuit_breaker_reset(self) -> Dict[str, Any]:
        """Force reset the circuit breaker."""
        self.quota_tracker._circuit_breaker_until = None
        await self.quota_tracker.save_quota_state()
        return {"status": "reset", "message": "Circuit breaker manually reset"}