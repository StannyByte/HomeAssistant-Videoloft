# api.py

import asyncio
import logging
import json
from typing import Optional, Dict, Any, List
from datetime import datetime

import aiohttp
from aiohttp import ClientSession, ClientResponseError, ClientError

from .const import AUTH_SERVER, DEFAULT_TOKEN_EXPIRY

_LOGGER = logging.getLogger(__name__)


class VideoloftAPI:
    """Handles communication with the Videoloft API."""

    def __init__(self, email: str, password: str, hass):
        self.email = email
        self.password = password
        self.hass = hass
        self.auth_token: Optional[str] = None
        self.web_login: Optional[Dict[str, Any]] = None
        self.region: Optional[str] = None
        self.token_expiry = 0
        self.device_info = None
        self._token_lock = asyncio.Lock()
        self.connector = aiohttp.TCPConnector(force_close=True)
        self.session = aiohttp.ClientSession(connector=self.connector)

    async def ensure_session(self):
        """Ensure the aiohttp session is open."""
        if self.session.closed:
            self.connector = aiohttp.TCPConnector(force_close=True)
            self.session = aiohttp.ClientSession(connector=self.connector)

    async def authenticate(self) -> str:
        """Authenticate and acquire auth token."""
        await self.ensure_session()
        url = f"{AUTH_SERVER}/login"
        data = {"email": self.email, "password": self.password}

        try:
            async with self.session.post(url, json=data, timeout=10) as response:
                response.raise_for_status()
                result = await response.json()
                auth_result = result.get("result", {})
                self.auth_token = auth_result.get("authToken")
                self.web_login = auth_result.get("webLogin")
                self.region = auth_result.get("region")
                if not self.auth_token or not self.web_login or not self.region:
                    raise ValueError("Authentication failed: Missing required data in response")
                self.token_expiry = self.hass.loop.time() + DEFAULT_TOKEN_EXPIRY
                _LOGGER.debug("Authentication successful, auth_token acquired.")
                return self.auth_token
        except ClientResponseError as e:
            _LOGGER.error(f"HTTP error during authentication: {e.status} - {e.message}")
            raise
        except ClientError as e:
            _LOGGER.error(f"Network error during authentication: {e}")
            raise
        except Exception as e:
            _LOGGER.error(f"Unexpected error during authentication: {e}")
            raise

    async def refresh_token(self):
        """Refresh the authentication token using webLogin."""
        await self.ensure_session()
        if not self.web_login or not self.region:
            _LOGGER.error("Cannot refresh token: Missing webLogin or region")
            await self.authenticate()
            return

        url = f"https://{self.region}-auth-1.manything.com/login/refresh"
        data = self.web_login

        try:
            async with self.session.post(url, json=data, timeout=10) as response:
                response.raise_for_status()
                result = await response.json()
                auth_result = result.get("result", {})
                self.auth_token = auth_result.get("authToken")
                self.web_login = auth_result.get("webLogin")
                if not self.auth_token or not self.web_login:
                    raise ValueError("Token refresh failed: Missing required data in response")
                self.token_expiry = self.hass.loop.time() + DEFAULT_TOKEN_EXPIRY
                _LOGGER.debug("Token refreshed successfully.")
        except ClientResponseError as e:
            _LOGGER.error(f"HTTP error during token refresh: {e.status} - {e.message}")
            raise
        except ClientError as e:
            _LOGGER.error(f"Network error during token refresh: {e}")
            raise
        except Exception as e:
            _LOGGER.error(f"Unexpected error during token refresh: {e}")
            raise

    async def get_token(self) -> str:
        """Retrieve and refresh auth token if expired."""
        async with self._token_lock:
            current_time = self.hass.loop.time()
            if not self.auth_token or current_time > self.token_expiry:
                _LOGGER.debug("Token expired or not found, refreshing token.")
                await self.refresh_token()
            return self.auth_token

    async def get_device_info(self):
        """Fetch the device information after authenticating."""
        token = await self.get_token()
        if not self.region:
            _LOGGER.error("Region not set. Cannot get device info.")
            return None
        url = f"https://{self.region}-auth-1.manything.com/devices/viewerInfo"
        headers = {"Authorization": f"ManythingToken {token}"}
        try:
            async with self.session.get(url, headers=headers, timeout=15) as response:
                response.raise_for_status()
                self.device_info = await response.json()
                _LOGGER.debug("Device information retrieved successfully.")
                return self.device_info
        except ClientResponseError as e:
            _LOGGER.error(f"HTTP error fetching device info: {e.status} - {e.message}")
            raise
        except ClientError as e:
            _LOGGER.error(f"Network error fetching device info: {e}")
            raise
        except Exception as e:
            _LOGGER.error(f"Unexpected error fetching device info: {e}")
            raise

    async def get_camera_status(self, uidd, logger_server):
        """Get initial camera status from logger server."""
        token = await self.get_token()
        url = f"https://{logger_server}/cameras/status"
        params = {"uidd": uidd}
        headers = {"Authorization": f"ManythingToken {token}"}

        try:
            async with self.session.get(url, params=params, headers=headers, timeout=10) as response:
                response.raise_for_status()
                status_data = await response.json()
                _LOGGER.debug(f"Camera status for {uidd} retrieved successfully.")
                return status_data
        except ClientResponseError as e:
            _LOGGER.error(f"HTTP error fetching camera status: {e.status} - {e.message}")
            raise
        except ClientError as e:
            _LOGGER.error(f"Network error fetching camera status: {e}")
            raise
        except Exception as e:
            _LOGGER.error(f"Unexpected error fetching camera status: {e}")
            raise

    async def send_live_command(self, uidd, logger_server):
        """Send livecommand camera task to keep camera streaming."""
        token = await self.get_token()
        url = f"https://{logger_server}/sendcameratask"
        params = {"uid": uidd, "action": "livecommand"}
        headers = {"Authorization": f"ManythingToken {token}"}
        try:
            async with self.session.get(url, params=params, headers=headers, timeout=10) as response:
                response.raise_for_status()
                _LOGGER.debug(f"Live command sent to camera {uidd} successfully.")
                return True
        except ClientResponseError as e:
            _LOGGER.error(f"HTTP error sending live command: {e.status} - {e.message}")
            raise
        except ClientError as e:
            _LOGGER.error(f"Network error sending live command: {e}")
            raise
        except Exception as e:
            _LOGGER.error(f"Unexpected error sending live command: {e}")
            raise

    async def get_live_stream_url(self, uidd, logger_server, wowza, live_stream_name):
        """Construct the live stream URL."""
        # The stream URL is constructed as https://${wowza}/manything/${liveStreamName}/index.m3u8
        stream_url = f"https://{wowza}/manything/{live_stream_name}/index.m3u8"
        _LOGGER.debug(f"Live stream URL for {uidd}: {stream_url}")
        return stream_url

    async def poll_camera_status(self, uidd, logger) -> dict:
        """Poll camera status periodically."""
        url = f"https://{logger}/cameras/status?uidd={uidd}"
        headers = {"Authorization": f"ManythingToken {await self.get_token()}"}
        async with self.session.get(url, headers=headers) as response:
            response.raise_for_status()
            return await response.json()

    async def get_camera_thumbnail(self, uidd, logger_server):
        """Get the latest thumbnail image from the camera."""
        token = await self.get_token()
        # Fetch the last thumbnail time
        last_thumb_time = await self.get_last_thumb_time(uidd, logger_server)

        url = f"https://{logger_server}/getthumb/{uidd}/{last_thumb_time}/{token}"
        headers = {"Authorization": f"ManythingToken {token}"}

        try:
            async with self.session.get(url, headers=headers, timeout=10) as response:
                response.raise_for_status()
                image_data = await response.read()
                _LOGGER.debug(f"Thumbnail image for {uidd} retrieved successfully.")
                return image_data
        except Exception as e:
            _LOGGER.error(f"Error fetching thumbnail image for {uidd}: {e}")
            raise

    async def get_last_thumb_time(self, uidd, logger_server):
        """Get the last thumbnail time from the camera status."""
        token = await self.get_token()
        url = f"https://{logger_server}/cameras/status"
        params = {"uidd": uidd}
        headers = {"Authorization": f"ManythingToken {token}"}

        try:
            async with self.session.get(url, params=params, headers=headers, timeout=10) as response:
                response.raise_for_status()
                status_data = await response.json()
                owner_uid, device_uid = uidd.split('.')
                device_status = status_data.get("result", {}).get(owner_uid, {}).get("devices", {}).get(device_uid, {})
                last_thumb = device_status.get("lastthumb", 0)
                return last_thumb
        except Exception as e:
            _LOGGER.error(f"Error fetching last thumb time for {uidd}: {e}")
            raise

    async def get_last_events(self, num_events: int = 20) -> List[Dict[str, Any]]:
        """Fetch the last events and include necessary event data."""
        token = await self.get_token()
        url = f"https://{self.region}-auth-1.manything.com/events/latest"
        headers = {"Authorization": f"ManythingToken {token}"}
        params = {"limit": num_events}
        try:
            async with self.session.get(url, headers=headers, params=params, timeout=15) as response:
                response.raise_for_status()
                events_data = await response.json()
                events = events_data.get("events", [])
                # Include logger_server and uidd in each event
                for event in events:
                    event["logger_server"] = self.devices.get(event["device_uid"], {}).get("logger")
                    event["uidd"] = event.get("uidd")
                _LOGGER.debug(f"Retrieved the last {num_events} events successfully.")
                return events
        except Exception as e:
            _LOGGER.error(f"Error fetching events: {e}")
            return []

    async def get_event_thumbnail(self, event_id: str) -> Optional[bytes]:
        """Get the thumbnail for a specific event."""
        token = await self.get_token()
        url = f"https://{self.region}-auth-1.manything.com/events/{event_id}/thumbnail"
        headers = {"Authorization": f"ManythingToken {token}"}

        try:
            async with self.session.get(url, headers=headers, timeout=10) as response:
                response.raise_for_status()
                image_data = await response.read()
                _LOGGER.debug(f"Thumbnail for event {event_id} retrieved successfully.")
                return image_data
        except Exception as e:
            _LOGGER.error(f"Error fetching thumbnail for event {event_id}: {e}")
            raise

    async def get_event_vehicle_analytics(self, logger_server: str, camera_uidd: str, event_id: str) -> Optional[List[Dict[str, Any]]]:
        """Fetch vehicle analytics data for a specific event."""
        uid, device_id = camera_uidd.split('.')
        url = f"https://{logger_server}/events/{uid}/{device_id}/{event_id}/analytics/vehicles?t={int(datetime.now().timestamp())}"

        headers = {
            "Authorization": f"ManythingToken {self.auth_token}",
            "Content-Type": "application/json"
        }

        try:
            async with self.session.get(url, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    _LOGGER.info(f"Vehicle analytics data: {data}")
                    return data
                else:
                    _LOGGER.error(f"Failed to retrieve vehicle analytics. Status code: {response.status}")
                    _LOGGER.error(f"Response text: {await response.text()}")
        except ClientResponseError as e:
            _LOGGER.error(f"HTTP error fetching vehicle analytics: {e.status} - {e.message}")
        except ClientError as e:
            _LOGGER.error(f"Network error fetching vehicle analytics: {e}")
        except Exception as e:
            _LOGGER.error(f"Unexpected error fetching vehicle analytics: {e}")
        return None

    def parse_lpr_data(self, event_data: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Parse LPR data from vehicle analytics."""
        lpr_info = {}
        if isinstance(event_data, list) and len(event_data) > 0:
            # Loop through all detected vehicles in the event
            for vehicle in event_data:
                lpr_info['license_plate'] = (vehicle.get('licence_plate') or '').lower()
                lpr_info['make'] = (vehicle.get('make') or '').lower()
                lpr_info['model'] = (vehicle.get('model') or '').lower()
                lpr_info['color'] = (vehicle.get('colour') or '').lower()
                lpr_info['timestamp'] = vehicle.get('still_time_ms')
                lpr_info['alertid'] = vehicle.get('alertid')
                lpr_info['direction'] = (vehicle.get('direction') or 'unknown').lower()
                # If any vehicle details are present, return the data
                if any([lpr_info['license_plate'], lpr_info['make'], lpr_info['model'], lpr_info['color']]):
                    return lpr_info
        return None

    async def close(self):
        """Close the aiohttp session and connector properly."""
        if self.session and not self.session.closed:
            await self.session.close()
        if self.connector and not self.connector.closed:
            await self.connector.close()

    async def get_recent_events_paginated(self, logger_server: str, uidd: str, start_time: int, end_time: int) -> List[Dict[str, Any]]:
        """Fetch recent events in paginated manner."""
        all_events = []
        current_start_time = start_time
        time_increment = 30 * 60 * 1000  # 30 minutes in milliseconds

        token = await self.get_token()

        while current_start_time < end_time:
            next_end_time = min(current_start_time + time_increment, end_time)
            params = {
                "uidd": uidd,
                "startt": current_start_time,
                "endt": next_end_time
            }

            url = f"https://{logger_server}/events"
            headers = {
                "Authorization": f"ManythingToken {token}",
                "Content-Type": "application/json"
            }

            try:
                async with self.session.get(url, headers=headers, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        if isinstance(data, list):
                            all_events.extend(data)
                            _LOGGER.debug(f"Fetched {len(data)} events between {current_start_time} and {next_end_time}")
                        else:
                            _LOGGER.debug(f"No events found between {current_start_time} and {next_end_time}")
                    else:
                        _LOGGER.error(f"Failed to retrieve events. Status code: {response.status}")
                        _LOGGER.error(f"Response text: {await response.text()}")
            except Exception as e:
                _LOGGER.error(f"Error fetching events: {e}")

            current_start_time = next_end_time

        return all_events
    
    async def get_recent_events(self, logger_server: str, uidd: str, start_time: Optional[int], end_time: Optional[int]) -> List[Dict[str, Any]]:
        """Fetch recent events within a time range."""
        all_events = []
        params = {
            "uidd": uidd,
            "startt": start_time or 0,
            "endt": end_time or int(datetime.now().timestamp() * 1000)
        }

        url = f"https://{logger_server}/events"
        headers = {
            "Authorization": f"ManythingToken {await self.get_token()}",
            "Content-Type": "application/json"
        }

        try:
            async with self.session.get(url, headers=headers, params=params) as response:
                response.raise_for_status()
                data = await response.json()
                if isinstance(data, list):
                    all_events.extend(data)
                    _LOGGER.debug(f"Fetched {len(data)} events.")
                else:
                    _LOGGER.debug("No events found.")
        except Exception as e:
            _LOGGER.error(f"Error fetching events: {e}")

        return all_events
    
    async def download_event_thumbnail(self, logger_server: str, uidd: str, event_id: str) -> Optional[bytes]:
        """Download thumbnail for a specific event."""
        token = await self.get_token()
        headers = {"Authorization": f"ManythingToken {token}"}

        thumb_url = f"https://{logger_server}/alertthumb/{uidd}/{event_id}/{token}"
        try:
            async with self.session.get(thumb_url, headers=headers, timeout=10) as response:
                if response.status == 200:
                    image_data = await response.read()
                    _LOGGER.debug(f"Downloaded thumbnail for event {event_id}")
                    return image_data
        except Exception as e:
            _LOGGER.error(f"Error downloading thumbnail for event {event_id}: {e}")

        return None

    """1 event/realtime event fetching"""
    async def get_latest_event(self, logger_server: str, uidd: str, start_time: Optional[int]) -> Optional[Dict[str, Any]]:
        """Fetch only the most recent event starting from the last known start time."""
        current_time = int(datetime.now().timestamp() * 1000)
        start_time = start_time or (current_time - (60 * 1000))  # Default to 60 seconds look back if not provided

        params = {
            "uidd": uidd,
            "startt": start_time,
            "endt": current_time
        }

        url = f"https://{logger_server}/events"
        try:
            headers = {
                "Authorization": f"ManythingToken {await self.get_token()}",
                "Content-Type": "application/json"
            }
            
            async with self.session.get(url, headers=headers, params=params) as response:
                response_text = await response.text()
                if response.status == 200:
                    try:
                        events = json.loads(response_text)
                    except json.JSONDecodeError as decode_err:
                        _LOGGER.error(f"Failed to decode JSON response for camera {uidd}: {decode_err}")
                        return None

                    if isinstance(events, list) and events:
                        _LOGGER.debug(f"Most recent event ID for camera {uidd}: {events[0].get('alert')}")
                        return events[0]  # Return only the most recent event
                    
                    _LOGGER.debug(f"No recent events for camera {uidd}")
                    return None
                else:
                    _LOGGER.error(f"Error fetching events for camera {uidd}: {response.status} - {response_text}")
                    return None
        except aiohttp.ClientError as client_err:
            _LOGGER.error(f"Network error in get_latest_event for camera {uidd}: {client_err}")
        except Exception as e:
            _LOGGER.error(f"Unexpected error in get_latest_event for camera {uidd}: {str(e)}")
        return None
    
    async def get_logger_server(self, uidd: str) -> Optional[str]:
        """Get logger server for a specific camera."""
        try:
            # Ensure we have device info
            if not self.device_info:
                await self.get_device_info()
                
            if not self.device_info or "result" not in self.device_info:
                _LOGGER.error("No device info available")
                return None
                
            owner_uid, device_uid = uidd.split('.')
            device_data = (self.device_info.get("result", {})
                         .get(owner_uid, {})
                         .get("devices", {})
                         .get(device_uid, {}))
            
            logger_server = device_data.get("logger")
            if not logger_server:
                _LOGGER.error(f"No logger server found for camera {uidd}")
                return None
                
            _LOGGER.debug(f"Retrieved logger server for camera {uidd}: {logger_server}")
            return logger_server
            
        except Exception as e:
            _LOGGER.error(f"Error getting logger server for camera {uidd}: {str(e)}")
            return None