# camera.py

"""Camera platform for the Videoloft integration."""

import asyncio
import logging
import time
from datetime import datetime

from typing import Any, Dict, Optional, List

from aiohttp import web, ClientSession, ClientResponseError, ClientError, TCPConnector
from homeassistant.components.camera import Camera, CameraEntityFeature
from homeassistant.components.http import HomeAssistantView
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import aiohttp_client
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.network import get_url

from .api import VideoloftAPI
from .const import (
    DOMAIN,
    ICON_CAMERA,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Videoloft cameras based on a config entry."""
    api: VideoloftAPI = hass.data[DOMAIN][entry.entry_id]["api"]
    devices: Dict[str, Any] = hass.data[DOMAIN][entry.entry_id]["devices"]

    entities = []

    for owner_uid, owner_data in devices.get("result", {}).items():
        for device_uid, device_data in owner_data.get("devices", {}).items():
            uidd = f"{owner_uid}.{device_uid}"
            camera = VideoloftCamera(hass, api, uidd, device_data)
            entities.append(camera)

    async_add_entities(entities)


class VideoloftCamera(Camera):
    """Representation of a Videoloft camera."""

    def __init__(
        self,
        hass: HomeAssistant,
        api: VideoloftAPI,
        uidd: str,
        device_data: Dict[str, Any],
    ) -> None:
        """Initialize the camera."""
        super().__init__()
        self.last_live_command_time = 0
        self.hass = hass
        self.api = api
        self.uidd = uidd
        self.device_data = device_data

        self._attr_name = device_data.get("phonename", f"Camera {uidd}")
        self._attr_unique_id = f"videoloft_camera_{uidd}"
        self._attr_icon = ICON_CAMERA
        self._stream_url: Optional[str] = None

        self._attr_supported_features = CameraEntityFeature.STREAM

        # Initialize variables for live streaming
        self.logger_server = device_data.get("logger")
        self.wowza = None
        self.live_stream_name = None

        # Start the initialization process
        self.hass.loop.create_task(self.initialize_stream())

    async def initialize_stream(self) -> None:
        """Initialize the camera stream."""
        if not self.logger_server:
            _LOGGER.error(f"No logger server found for {self._attr_name}")
            return

        # Start keep-alive task first and wait for it to send initial command
        keep_alive_task = self.hass.loop.create_task(self.keep_stream_alive())
        await asyncio.sleep(2)  # Give keep-alive task time to start

        retry_delay = 10
        while True:
            try:
                status_data = await self.api.get_camera_status(self.uidd, self.logger_server)
                owner_uid, device_uid = self.uidd.split('.')
                device_status = status_data.get("result", {}).get(owner_uid, {}).get("devices", {}).get(device_uid, {})
                
                self.wowza = device_status.get("wowza")
                self.live_stream_name = device_status.get("liveStreamName")
                is_live = device_status.get("status") == "live" and device_status.get("live")

                if self.wowza and self.wowza != "wowza1" and is_live and self.live_stream_name:
                    self._stream_url = await self.api.get_live_stream_url(
                        self.uidd, self.logger_server, self.wowza, self.live_stream_name
                    )
                    _LOGGER.info(f"Stream initialized for {self._attr_name}")
                    return
                
                await asyncio.sleep(retry_delay)
            except Exception as e:
                _LOGGER.error(f"Stream initialization error for {self._attr_name}: {e}")
                await asyncio.sleep(retry_delay)

    async def update_stream_url(self) -> bool:
        """Update the stream URL from current camera status."""
        try:
            status_data = await self.api.get_camera_status(self.uidd, self.logger_server)
            owner_uid, device_uid = self.uidd.split('.')
            device_status = status_data.get("result", {}).get(owner_uid, {}).get("devices", {}).get(device_uid, {})
            
            self.wowza = device_status.get("wowza")
            self.live_stream_name = device_status.get("liveStreamName")
            is_live = device_status.get("status") == "live" and device_status.get("live")

            if self.wowza and self.wowza != "wowza1" and is_live and self.live_stream_name:
                new_url = await self.api.get_live_stream_url(
                    self.uidd, self.logger_server, self.wowza, self.live_stream_name
                )
                if new_url != self._stream_url:
                    self._stream_url = new_url
                    _LOGGER.info("Updated stream URL for %s: %s", self._attr_name, self._stream_url)
                return True
            return False
        except Exception as e:
            _LOGGER.error("Error updating stream URL for %s: %s", self._attr_name, e)
            return False

    async def keep_stream_alive(self):
        """Keep stream alive with periodic live commands."""
        while True:
            try:
                await self.api.send_live_command(self.uidd, self.logger_server)
                self.last_live_command_time = self.hass.loop.time()
                _LOGGER.debug(f"Live command sent to {self._attr_name}")
                
                # Wait for stream to become available after live command
                await asyncio.sleep(13)
                
                # Check and update stream URL
                status_data = await self.api.get_camera_status(self.uidd, self.logger_server)
                owner_uid, device_uid = self.uidd.split('.')
                device_status = status_data.get("result", {}).get(owner_uid, {}).get("devices", {}).get(device_uid, {})
                
                if device_status.get("status") == "live" and device_status.get("live"):
                    new_wowza = device_status.get("wowza")
                    new_stream_name = device_status.get("liveStreamName")
                    
                    if new_wowza and new_wowza != "wowza1" and new_stream_name:
                        self._stream_url = await self.api.get_live_stream_url(
                            self.uidd, self.logger_server, new_wowza, new_stream_name
                        )
                
                await asyncio.sleep(20)  # Wait remaining time to maintain 30s interval
                
            except Exception as e:
                _LOGGER.error(f"Keep-alive error for {self._attr_name}: {e}")
                await asyncio.sleep(30)

    async def stream_source(self) -> Optional[str]:
        """Return the current stream source URL."""
        if not self._stream_url or "wowza1" in self._stream_url:
            _LOGGER.debug("Invalid stream URL for %s, attempting update", self._attr_name)
            await self.update_stream_url()

        if self._stream_url and "wowza1" not in self._stream_url:
            hass_url = get_url(self.hass, require_ssl=False)
            return f"{hass_url}/api/videoloft/stream/{self.uidd}/index.m3u8"
        return None

    async def reinitialize_stream(self) -> None:
        """Force reinitialization of the stream."""
        _LOGGER.warning("Reinitializing stream for %s", self._attr_name)
        await self.initialize_stream()

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return the state attributes."""
        attributes = {
            "device_id": self.uidd,
            "model": self.device_data.get("model", "Unknown Model"),
            "mac_address": self.device_data.get("macAddress", "Unknown MAC"),
            "resolution": self.device_data.get("recordingResolution", "Unknown"),
            "cloud_recording": self.device_data.get("cloudRecordingEnabled", False),
            "audio_enabled": self.device_data.get("audioEnabled", False),
            "ptz_enabled": self.device_data.get("ptzEnabled", False),
            "analytics_enabled": self.device_data.get("analyticsEnabled", False),
        }
        return attributes
    
class VideoloftCameraStreamView(HomeAssistantView):
    """A view that proxies the camera stream and handles HLS streams efficiently."""

    url = "/api/videoloft/stream/{uidd}/{path:.*}"
    name = "api:videoloft:stream"
    requires_auth = False

    def __init__(self, hass, api, max_connections=100):
        """Initialize the stream view with connection limits."""
        self.hass = hass
        self.api = api
        connector = TCPConnector(limit=max_connections)  # Limit concurrent connections
        self.session = ClientSession(connector=connector)

    async def get(self, request, uidd: str, path: str) -> web.StreamResponse:
        """Handle GET request to proxy the stream and manage 404 errors by reinitializing the stream."""
        _LOGGER.debug(f"Proxying stream for {uidd}, path: {path}")

        camera_entity = next(
            (entity for entity in self.hass.data["camera"].entities if getattr(entity, "uidd", None) == uidd),
            None,
        )
        if not camera_entity or not camera_entity._stream_url:
            _LOGGER.error(f"Unable to get stream URL for {uidd}")
            return web.HTTPInternalServerError()

        target_url = self.construct_target_url(camera_entity._stream_url, path)
        if "wowza1" in target_url:
            _LOGGER.warning(f"Stream URL for {uidd} is still a placeholder (wowza1), waiting for valid URL.")
            return web.HTTPServiceUnavailable(text="Placeholder URL; waiting for valid stream.")

        headers = await self.get_auth_headers()

        try:
            async with self.session.get(target_url, headers=headers, timeout=10) as upstream_resp:
                if upstream_resp.status == 200:
                    content_type = upstream_resp.headers.get("Content-Type", "application/vnd.apple.mpegurl")

                    if "mpegurl" in content_type or target_url.endswith(".m3u8"):
                        playlist_content = await upstream_resp.text()
                        rewritten_playlist = self.rewrite_m3u8_playlist(playlist_content, uidd)
                        return web.Response(body=rewritten_playlist, content_type=content_type)
                    else:
                        return await self.stream_segment(request, upstream_resp)
                elif upstream_resp.status == 404:
                    _LOGGER.warning(f"Received 404 for stream of camera {uidd}. Reinitializing stream.")
                    await camera_entity.reinitialize_stream()
                    return web.HTTPServiceUnavailable(text="Stream unavailable, reinitializing...")
                else:
                    return await self.handle_upstream_error(upstream_resp, uidd)

        except (ClientResponseError, ClientError) as e:
            _LOGGER.exception(f"Error fetching {target_url} for {uidd}: {e}")
            return web.HTTPInternalServerError()

    def construct_target_url(self, stream_url: str, path: Optional[str]) -> str:
        """Construct the target URL based on the path provided."""
        return f"{stream_url.rsplit('/', 1)[0]}/{path}" if path else stream_url

    async def get_auth_headers(self) -> dict:
        """Get authorization headers using the current API token."""
        token = await self.api.get_token()
        return {"Authorization": f"ManythingToken {token}"}

    async def stream_segment(self, request, upstream_resp):
        # Create the response object without content_type
        resp = web.StreamResponse(status=200)
        
        # Set the content type after creation
        content_type = upstream_resp.headers.get("Content-Type")
        if content_type:
            resp.headers["Content-Type"] = content_type

        # Start the response and proceed with streaming
        await resp.prepare(request)
        
        async for chunk in upstream_resp.content.iter_chunked(1024):
            await resp.write(chunk)
        
        return resp

    async def handle_upstream_error(self, upstream_resp, uidd) -> web.Response:
        """Handle errors from upstream responses."""
        error_text = await upstream_resp.text()
        _LOGGER.error(f"Failed to fetch stream for {uidd}: {upstream_resp.status} - {error_text}")
        return web.Response(status=upstream_resp.status, text=error_text)

    def rewrite_m3u8_playlist(self, playlist_content: str, uidd: str) -> bytes:
        """Rewrite URLs in the M3U8 playlist to proxy through our endpoint."""
        lines = playlist_content.splitlines()
        new_lines = []
        for line in lines:
            if line.startswith("#"):
                new_lines.append(line)
            else:
                filename = line.split("/")[-1]
                new_url = f"/api/videoloft/stream/{uidd}/{filename}"
                new_lines.append(new_url)
        rewritten_playlist = "\n".join(new_lines).encode("utf-8")
        _LOGGER.debug(f"Rewritten playlist for {uidd}:\n{rewritten_playlist.decode()}")
        return rewritten_playlist