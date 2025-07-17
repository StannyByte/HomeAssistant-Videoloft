import asyncio
import logging
import json
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
import aiohttp
from aiohttp import ClientResponseError, ClientError
from .const import AUTH_SERVER, DEFAULT_TOKEN_EXPIRY

_LOGGER = logging.getLogger(__name__)

# ----------------------------------------------------------
# EXCEPTION CLASSES
# ----------------------------------------------------------
class VideoloftApiClientError(Exception):
    """Base exception for Videoloft API client errors."""
    pass

class VideoloftApiAuthError(VideoloftApiClientError):
    """Exception raised for authentication-related errors."""
    pass

# ----------------------------------------------------------
# MAIN API CLIENT CLASS
# ----------------------------------------------------------
class VideoloftAPI:
    """Handles communication with the Videoloft API."""

    def __init__(self, email: str, password: str, hass):
        self.email, self.password, self.hass = email, password, hass
        self.auth_token = self.web_login = self.region = self.device_info = None
        self.token_expiry = 0
        self._token_lock = asyncio.Lock()
        self._cameras_cache = {}
        self._cache_time = None
        self.session = aiohttp.ClientSession(connector=aiohttp.TCPConnector(force_close=True))

    @property
    def cameras_by_uidd(self) -> Dict[str, Dict[str, Any]]:
        return self._cameras_cache

    # ----------------------------------------------------------
    # CORE REQUEST HELPERS
    # ----------------------------------------------------------
    async def _request(self, method: str, url: str, binary: bool = False, **kwargs) -> Any:
        """Unified request method for all API calls."""
        headers = kwargs.get('headers', {})
        headers['Authorization'] = f'ManythingToken {await self.get_token()}'
        kwargs['headers'] = headers
        
        try:
            async with getattr(self.session, method)(url, **kwargs) as response:
                response.raise_for_status()
                return await response.read() if binary else await response.json()
        except Exception as e:
            if binary:
                return None
            error_msg = f"{e.status} - {e.message}" if hasattr(e, 'status') else str(e)
            _LOGGER.error(f"Request failed: {error_msg}")
            raise VideoloftApiClientError(f"Request failed: {error_msg}")

    # ----------------------------------------------------------
    # TOKEN AUTHENTICATION & MANAGEMENT
    # ----------------------------------------------------------
    async def authenticate(self) -> str:
        """Authenticate and acquire auth token with retry and redirect handling."""
        auth_url = f"{AUTH_SERVER}/login"
        data = {"email": self.email, "password": self.password}
        
        for attempt in range(3):
            try:
                async with self.session.post(auth_url, json=data, timeout=10) as response:
                    result = await response.json()
                    
                    # Handle redirect
                    if "location" in result:
                        auth_url = result["location"] + "/login"
                        continue

                    # Check for errors
                    if "error" in result or "message" in result:
                        error_msg = result.get("error") or result.get("message")
                        raise VideoloftApiAuthError(f"Authentication failed: {error_msg}")

                    auth_result = result.get("result", {})
                    self.auth_token = auth_result.get("authToken")
                    self.web_login = auth_result.get("webLogin")
                    self.region = auth_result.get("region") or auth_result.get("authenticator")

                    if self.auth_token and self.region and self.web_login:
                        self.token_expiry = self.hass.loop.time() + DEFAULT_TOKEN_EXPIRY
                        return self.auth_token

                    missing = [k for k, v in {"authToken": self.auth_token, "region": self.region, "webLogin": self.web_login}.items() if not v]
                    raise VideoloftApiAuthError(f"Missing required data: {', '.join(missing)}")

            except (ClientResponseError, ClientError, asyncio.TimeoutError, json.JSONDecodeError) as e:
                if attempt == 2:
                    raise VideoloftApiAuthError(f"Authentication failed: {e}")
                await asyncio.sleep(2 ** attempt)

        raise VideoloftApiAuthError("Authentication failed after retries")

    async def refresh_token(self):
        """Refresh the authentication token using webLogin."""
        if not self.web_login or not self.region:
            await self.authenticate()
            return

        url = f"https://{self.region}-auth-1.manything.com/login/refresh"
        try:
            async with self.session.post(url, json=self.web_login, timeout=10) as response:
                response.raise_for_status()
                result = await response.json()
                auth_result = result.get("result", {})
                self.auth_token = auth_result.get("authToken")
                self.web_login = auth_result.get("webLogin")
                
                if not self.auth_token or not self.web_login:
                    raise VideoloftApiAuthError("Token refresh failed: Missing data")
                    
                self.token_expiry = self.hass.loop.time() + DEFAULT_TOKEN_EXPIRY
        except Exception as e:
            raise VideoloftApiAuthError(f"Token refresh failed: {e}")

    async def get_token(self) -> str:
        """Retrieve and refresh auth token if expired."""
        async with self._token_lock:
            if not self.auth_token or self.hass.loop.time() > self.token_expiry:
                if self.web_login and self.region:
                    await self.refresh_token()
                else:
                    await self.authenticate()
            return self.auth_token

    # ----------------------------------------------------------
    # DEVICE & CAMERA INFORMATION
    # ----------------------------------------------------------
    async def get_device_info(self):
        """Fetch the device information after authenticating."""
        if not self.region:
            return None
        url = f"https://{self.region}-auth-1.manything.com/devices/viewerInfo"
        self.device_info = await self._request('get', url, timeout=15)
        return self.device_info

    async def get_camera_status(self, uidd, logger_server):
        """Get initial camera status from logger server."""
        url = f"https://{logger_server}/cameras/status"
        return await self._request('get', url, params={"uidd": uidd}, timeout=10)

    async def send_live_command(self, uidd, logger_server):
        """Send livecommand camera task to keep camera streaming."""
        url = f"https://{logger_server}/sendcameratask"
        await self._request('get', url, params={"uid": uidd, "action": "livecommand"}, timeout=10)
        return True

    async def get_live_stream_url(self, uidd, logger_server, wowza, live_stream_name):
        """Construct the live stream URL."""
        return f"https://{wowza}/manything/{live_stream_name}/index.m3u8"
    
    def get_cached_camera_data(self, uidd: str) -> Optional[Dict[str, Any]]:
        """Get camera data from cache without triggering API call."""
        return self._cameras_cache.get(uidd)

    async def poll_camera_status(self, uidd, logger) -> dict:
        """Poll camera status periodically."""
        url = f"https://{logger}/cameras/status"
        return await self._request('get', url, params={"uidd": uidd}, timeout=10)

    async def get_last_thumb_time(self, uidd, logger_server):
        """Get the last thumbnail time from the camera status."""
        status_data = await self.get_camera_status(uidd, logger_server)
        owner_uid, device_uid = uidd.split('.')
        device_status = status_data.get("result", {}).get(owner_uid, {}).get("devices", {}).get(device_uid, {})
        return device_status.get("lastthumb", 0)

    async def get_camera_thumbnail(self, uidd, logger_server):
        """Get the latest thumbnail image from the camera."""
        try:
            last_thumb_time = await self.get_last_thumb_time(uidd, logger_server)
            token = await self.get_token()
            url = f"https://{logger_server}/getthumb/{uidd}/{last_thumb_time}/{token}"
            return await self._request('get', url, binary=True, timeout=10)
        except Exception as e:
            _LOGGER.error(f"Error fetching thumbnail for {uidd}: {e}")
            return None

    # ----------------------------------------------------------
    # EVENT & ANALYTICS METHODS
    # ----------------------------------------------------------
    async def get_last_events(self, num_events: int = 20) -> List[Dict[str, Any]]:
        """Fetch the last events and include necessary event data."""
        url = f"https://{self.region}-auth-1.manything.com/events/latest"
        try:
            events_data = await self._request('get', url, params={"limit": num_events}, timeout=15)
            result = events_data.get("result", {})
            if result:
                first_key = next(iter(result))
                return result[first_key].get("events", [])
            return []
        except Exception as e:
            _LOGGER.error(f"Error fetching last events: {e}")
            return []

    async def get_event_thumbnail(self, event_id: str) -> Optional[bytes]:
        """Get the thumbnail for a specific event."""
        url = f"https://{self.region}-auth-1.manything.com/events/{event_id}/thumbnail"
        return await self._request('get', url, binary=True, timeout=10)

    async def get_vehicle_detections(self, uidds: List[str], start_time: int, limit: int = 10) -> List[Dict[str, Any]]:
        """Retrieves a paginated list of vehicle detections with detailed metadata."""
        if not self.region:
            return []

        url = f"https://{self.region}-analytics.manything.com/vehicles"
        payload = {
            "uidds": uidds,
            "startTime": start_time,
            "ascendingOrder": False,
            "searchWithCount": False,
            "limit": limit
        }

        try:
            return await self._request('post', url, json=payload, timeout=15)
        except Exception as e:
            _LOGGER.error(f"Error fetching vehicle detections: {e}")
            return []
        
    async def get_event_vehicle_analytics(self, logger_server: str, camera_uidd: str, event_id: str) -> Optional[List[Dict[str, Any]]]:
        """Fetch vehicle analytics data for a specific event."""
        uid, device_id = camera_uidd.split('.')
        url = f"https://{logger_server}/events/{uid}/{device_id}/{event_id}/analytics/vehicles?t={int(datetime.now().timestamp())}"
        
        try:
            data = await self._request('get', url, timeout=15)
            return data.get("result", {}).get("analytics", []) if isinstance(data, dict) else []
        except Exception as e:
            _LOGGER.error(f"Error fetching event vehicle analytics: {e}")
            return None

    # ----------------------------------------------------------
    # LPR DATA PARSING
    # ----------------------------------------------------------
    def parse_lpr_data(self, event_data: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Parse LPR data from vehicle analytics."""
        if not isinstance(event_data, list) or not event_data:
            return None
            
        for vehicle in event_data:
            lpr_info = {
                'license_plate': (vehicle.get('licencePlate') or '').lower(),
                'make': (vehicle.get('make') or '').lower(),
                'model': (vehicle.get('model') or '').lower(),
                'color': (vehicle.get('colour') or '').lower(),
                'timestamp': vehicle.get('stillTimeMs'),
                'alertid': vehicle.get('alertid'),
                'direction': (vehicle.get('direction') or 'unknown').lower()
            }
            
            if any([lpr_info['license_plate'], lpr_info['make'], lpr_info['model'], lpr_info['color']]):
                return lpr_info
                
        return None

    # ----------------------------------------------------------
    # EVENT METHODS
    # ----------------------------------------------------------
    async def get_lpr_event_thumbnail(self, owner_uid: str, device_id: str, event_ts: str, unique_id: str) -> Optional[bytes]:
        """Get the thumbnail for an LPR event."""
        url = f"https://{self.region}-video.manything.com/images/lpr/{owner_uid}/{device_id}/{event_ts}/{unique_id}"
        return await self._request('get', url, binary=True, timeout=10)

    async def get_recent_events_paginated(self, logger_server: str, uidd: str, start_time: int, end_time: int) -> List[Dict[str, Any]]:
        """Fetch recent events in paginated manner."""
        _LOGGER.info(f"API: Getting events for {uidd} from {logger_server} between {start_time} and {end_time}")
        
        all_events = []
        current_start_time = start_time
        time_increment = 30 * 60 * 1000  # 30 minutes

        while current_start_time < end_time:
            next_end_time = min(current_start_time + time_increment, end_time)
            params = {"uidd": uidd, "startt": current_start_time, "endt": next_end_time}
            url = f"https://{logger_server}/events"

            try:
                _LOGGER.debug(f"API: Requesting events from {url} with params {params}")
                data = await self._request('get', url, params=params, timeout=15)
                if isinstance(data, list):
                    _LOGGER.debug(f"API: Retrieved {len(data)} events for time slice {current_start_time} to {next_end_time}")
                    all_events.extend(data)
                else:
                    _LOGGER.warning(f"API: Unexpected response format: {type(data)}")
            except Exception as e:
                _LOGGER.error(f"Error fetching events from {url}: {e}")

            current_start_time = next_end_time

        _LOGGER.info(f"API: Total events retrieved for {uidd}: {len(all_events)}")
        return all_events
    
    async def get_recent_events(self, logger_server: str, uidd: str, start_time: Optional[int], end_time: Optional[int]) -> List[Dict[str, Any]]:
        """Fetch recent events within a time range."""
        params = {
            "uidd": uidd,
            "startt": start_time or 0,
            "endt": end_time or int(datetime.now().timestamp() * 1000)
        }
        url = f"https://{logger_server}/events"
        try:
            return await self._request('get', url, params=params, timeout=15) or []
        except Exception as e:
            _LOGGER.error(f"Error fetching events for {uidd}: {e}")
            return []
    
    async def download_event_thumbnail(self, logger_server: str, uidd: str, event_id: str) -> Optional[bytes]:
        """Download thumbnail for a specific event."""
        _LOGGER.debug(f"API: Downloading thumbnail for event {event_id} from {logger_server}")
        
        token = await self.get_token()
        if not token:
            _LOGGER.error(f"API: No token available for thumbnail download")
            return None
            
        url = f"https://{logger_server}/alertthumb/{uidd}/{event_id}/{token}"
        _LOGGER.debug(f"API: Thumbnail URL: {url}")
        
        try:
            result = await self._request('get', url, binary=True, timeout=10)
            if result:
                _LOGGER.debug(f"API: Successfully downloaded thumbnail for event {event_id} ({len(result)} bytes)")
            else:
                _LOGGER.warning(f"API: Failed to download thumbnail for event {event_id}")
            return result
        except Exception as e:
            _LOGGER.error(f"API: Error downloading thumbnail for event {event_id}: {e}")
            return None

    async def get_latest_event(self, logger_server: str, uidd: str, start_time: Optional[int]) -> Optional[Dict[str, Any]]:
        """Fetch only the most recent event starting from the last known start time."""
        current_time = int(datetime.now().timestamp() * 1000)
        params = {
            "uidd": uidd,
            "startt": start_time or (current_time - 60000),
            "endt": current_time
        }
        url = f"https://{logger_server}/events"
        
        try:
            events = await self._request('get', url, params=params, timeout=15)
            return events[0] if isinstance(events, list) and events else None
        except Exception as e:
            _LOGGER.error(f"Error fetching latest event for {uidd}: {e}")
            return None
    
    async def get_logger_server(self, uidd: str) -> Optional[str]:
        """Get logger server for a specific camera."""
        try:
            _LOGGER.debug(f"API: Getting logger server for {uidd}")
            
            if not self.device_info:
                _LOGGER.debug("API: Device info not cached, fetching...")
                await self.get_device_info()
                
            if not self.device_info or "result" not in self.device_info:
                _LOGGER.warning(f"API: No device info available for {uidd}")
                return None
                
            owner_uid, device_uid = uidd.split('.')
            device_data = (self.device_info.get("result", {})
                         .get(owner_uid, {})
                         .get("devices", {})
                         .get(device_uid, {}))
            
            logger_server = device_data.get("logger")
            _LOGGER.debug(f"API: Logger server for {uidd}: {logger_server}")
            return logger_server
            
        except Exception as e:
            _LOGGER.error(f"Error getting logger server for {uidd}: {e}")
            return None

    async def get_cameras_info(self, force_refresh: bool = False) -> List[Dict[str, Any]]:
        """Get detailed information for all cameras accessible to the authenticated user."""
        # Check cache validity (12 hours)
        if (not force_refresh and self._cameras_cache and self._cache_time and 
            datetime.now() - self._cache_time < timedelta(hours=12)):
            return list(self._cameras_cache.values())
        
        if not self.region:
            return []

        url = f"https://{self.region}-auth-1.manything.com/cameras"
        try:
            cameras_info = await self._request('get', url, timeout=15)
            
            # Update cache
            self._cameras_cache = {}
            for camera_data in cameras_info:
                uidd = f"{camera_data['uid']}.{camera_data['id']}"
                self._cameras_cache[uidd] = camera_data
            
            self._cache_time = datetime.now()
            return cameras_info
        except Exception as e:
            _LOGGER.error(f"Error fetching cameras info: {e}")
            return []

    # ----------------------------------------------------------
    # SESSION MANAGEMENT
    # ----------------------------------------------------------
    async def close(self):
        """Close the aiohttp session and connector properly."""
        if self.session and not self.session.closed:
            await self.session.close()