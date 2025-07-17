# camera.py

"""Camera platform for the Videoloft integration."""

import asyncio
import logging
import time
from datetime import datetime

from typing import Any, Dict, Optional, List

from aiohttp import web, ClientResponseError, ClientError
from homeassistant.components.camera import Camera, CameraEntityFeature
from homeassistant.components.http import HomeAssistantView
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import aiohttp_client
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.network import get_url
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC
from homeassistant.util import dt as dt_util

from .api import VideoloftAPI
from .const import (
    DOMAIN,
    ICON_CAMERA,
)
from .device_info import create_device_info, get_camera_capabilities, get_technical_specs

_LOGGER = logging.getLogger(__name__)

# ----------------------------------------------------------
# PLATFORM SETUP
# ----------------------------------------------------------


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Videoloft cameras based on a config entry."""
    api: VideoloftAPI = hass.data[DOMAIN][entry.entry_id]["api"]
    devices: Dict[str, Any] = hass.data[DOMAIN][entry.entry_id]["devices"]

    entities = []

    # The 'devices' now directly contains the list of camera objects
    for device_data in devices:
        uidd = f"{device_data['uid']}.{device_data['id']}" # Construct uidd from flat data
        camera = VideoloftCamera(hass, api, uidd, device_data)
        entities.append(camera)

    async_add_entities(entities)

# ----------------------------------------------------------
# CAMERA ENTITY CLASS
# ----------------------------------------------------------


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
        self._stream_available: bool = False

        self._attr_supported_features = CameraEntityFeature.STREAM

        # Enhanced device registry information using device_info module
        self._attr_device_info = create_device_info(uidd, device_data)

        # Initialize variables for live streaming
        self.logger_server = device_data.get("logger")
        self.wowza = None
        self.live_stream_name = None

        # Start the initialization process
        if self.hass:
            self.hass.loop.create_task(self.initialize_stream())

    async def initialize_stream(self) -> None:
        """Initialize the camera stream."""
        if not self.logger_server:
            _LOGGER.error(f"No logger server found for {self._attr_name}")
            return

        # Start keep-alive task only if not already running
        if not hasattr(self, "_keep_alive_task") or self._keep_alive_task is None or self._keep_alive_task.done():
            if self.hass:
                self._keep_alive_task = self.hass.loop.create_task(self.keep_stream_alive())
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
                    self._stream_available = True
                    self.async_write_ha_state()  # Update Home Assistant state
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
                self._stream_available = True
                self.async_write_ha_state()  # Update Home Assistant state
                return True
            else:
                # Stream is not available
                if self._stream_available:
                    self._stream_available = False
                    self.async_write_ha_state()  # Update Home Assistant state
                    _LOGGER.info("Stream became unavailable for %s", self._attr_name)
            return False
        except Exception as e:
            _LOGGER.error("Error updating stream URL for %s: %s", self._attr_name, e)
            return False

    async def keep_stream_alive(self):
        """Optimized keep-alive with fixed intervals for low latency."""
        consecutive_failures = 0
        interval = 30  # Fixed interval in seconds

        while True:
            try:
                # Send live command with timeout
                await asyncio.wait_for(
                    self.api.send_live_command(self.uidd, self.logger_server),
                    timeout=8.0
                )
                if self.hass:
                    self.last_live_command_time = self.hass.loop.time()
                _LOGGER.debug(f"Live command sent to {self._attr_name}")

                # Quick stream status check with timeout
                try:
                    status_data = await asyncio.wait_for(
                        self.api.get_camera_status(self.uidd, self.logger_server),
                        timeout=5.0
                    )
                    owner_uid, device_uid = self.uidd.split('.')
                    device_status = status_data.get("result", {}).get(owner_uid, {}).get("devices", {}).get(device_uid, {})
                    if device_status.get("status") == "live" and device_status.get("live"):
                        new_wowza = device_status.get("wowza")
                        new_stream_name = device_status.get("liveStreamName")
                        # Only update stream URL if wowza or stream name changed
                        if (new_wowza != self.wowza or new_stream_name != self.live_stream_name) and new_wowza and new_wowza != "wowza1" and new_stream_name:
                            new_stream_url = await self.api.get_live_stream_url(
                                self.uidd, self.logger_server, new_wowza, new_stream_name
                            )
                            if new_stream_url != self._stream_url:
                                self._stream_url = new_stream_url
                                _LOGGER.debug(f"Stream URL updated for {self._attr_name}")
                            self.wowza = new_wowza
                            self.live_stream_name = new_stream_name
                        # Update stream availability
                        if not self._stream_available:
                            self._stream_available = True
                            self.async_write_ha_state()
                            _LOGGER.info(f"Stream became available for {self._attr_name}")
                    else:
                        # Stream is not live
                        if self._stream_available:
                            self._stream_available = False
                            self.async_write_ha_state()
                            _LOGGER.info(f"Stream became unavailable for {self._attr_name}")
                    consecutive_failures = 0
                except asyncio.TimeoutError:
                    _LOGGER.warning(f"Status check timeout for {self._attr_name}")

                await asyncio.sleep(interval)

            except asyncio.TimeoutError:
                consecutive_failures += 1
                _LOGGER.warning(f"Live command timeout for {self._attr_name} (attempt {consecutive_failures})")
                await asyncio.sleep(interval)

            except Exception as e:
                consecutive_failures += 1
                _LOGGER.error(f"Keep-alive error for {self._attr_name}: {e} (attempt {consecutive_failures})")
                await asyncio.sleep(interval)

    async def stream_source(self) -> Optional[str]:
        """Return the current stream source URL."""
        # Only return stream URL if it's actually available
        if not self._stream_available:
            return None
            
        if not self._stream_url or "wowza1" in self._stream_url:
            _LOGGER.debug("Invalid stream URL for %s, attempting update", self._attr_name)
            await self.update_stream_url()

        if self._stream_available and self._stream_url and "wowza1" not in self._stream_url:
            hass_url = get_url(self.hass, require_ssl=False)
            return f"{hass_url}/api/videoloft/stream/{self.uidd}/index.m3u8"
        return None

    @property
    def available(self) -> bool:
        """Return True if the camera stream is available."""
        return self._stream_available

    async def async_camera_image(self, width: Optional[int] = None, height: Optional[int] = None) -> Optional[bytes]:
        """Return camera image for Home Assistant with enhanced caching and robust error handling."""
        try:
            # Defensive programming: ensure this method always returns bytes or None, never a coroutine
            _LOGGER.debug(f"Fetching camera image for {self.uidd}")
            
            # Get coordinator from hass data
            coordinator = None
            for entry_id, entry_data in self.hass.data.get(DOMAIN, {}).items():
                if "coordinator" in entry_data:
                    coordinator = entry_data["coordinator"]
                    break
            
            if coordinator:
                # Try to get thumbnail immediately, even if slightly stale for faster display
                thumbnail_data = await coordinator.get_cached_thumbnail_immediate(self.uidd)
                if thumbnail_data and isinstance(thumbnail_data, bytes):
                    # Start background refresh if cache is getting old
                    cache_entry = coordinator._thumbnail_cache.get(self.uidd)
                    if cache_entry:
                        cached_time = cache_entry.get("timestamp")
                        if cached_time:
                            cache_age = dt_util.utcnow() - cached_time
                            # If cache is older than refresh interval, trigger background refresh
                            if cache_age > coordinator._thumbnail_refresh_interval:
                                self.hass.async_create_task(coordinator.refresh_thumbnail(self.uidd, force=True))
                    _LOGGER.debug(f"Returning cached thumbnail for {self.uidd} ({len(thumbnail_data)} bytes)")
                    return thumbnail_data
                
                # If no cached thumbnail available, get fresh one
                thumbnail_data = await coordinator.ensure_thumbnail_available(self.uidd)
                if thumbnail_data and isinstance(thumbnail_data, bytes):
                    _LOGGER.debug(f"Returning fresh thumbnail for {self.uidd} ({len(thumbnail_data)} bytes)")
                    return thumbnail_data
            
            # Fallback to direct API call if coordinator not available
            if self.logger_server:
                _LOGGER.debug(f"Fallback: Fetching thumbnail directly for {self.uidd}")
                thumbnail_data = await self.api.get_camera_thumbnail(self.uidd, self.logger_server)
                if thumbnail_data and isinstance(thumbnail_data, bytes):
                    _LOGGER.debug(f"Returning direct API thumbnail for {self.uidd} ({len(thumbnail_data)} bytes)")
                    return thumbnail_data
            
        except asyncio.CancelledError:
            _LOGGER.debug(f"Camera image request cancelled for {self.uidd}")
            raise
        except Exception as e:
            _LOGGER.error(f"Error getting camera image for {self.uidd}: {e}", exc_info=True)
        
        _LOGGER.warning(f"No thumbnail data available for {self.uidd}")
        return None

    async def reinitialize_stream(self) -> None:
        """Force reinitialization of the stream."""
        _LOGGER.warning("Reinitializing stream for %s", self._attr_name)
        self._stream_available = False
        self.async_write_ha_state()  # Update Home Assistant immediately
        await self.initialize_stream()

    async def force_stream_refresh(self) -> None:
        """Force refresh of stream availability state."""
        _LOGGER.info("Forcing stream refresh for %s", self._attr_name)
        success = await self.update_stream_url()
        if success:
            _LOGGER.info("Stream refresh successful for %s", self._attr_name)
        else:
            _LOGGER.warning("Stream refresh failed for %s", self._attr_name)

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return enhanced state attributes with rich camera data."""
        capabilities = get_camera_capabilities(self.device_data)
        technical_specs = get_technical_specs(self.device_data)
        
        attributes = {
            "device_id": self.uidd,
            # Technical specifications
            "recording_resolution": technical_specs["recording_resolution"],
            "video_codec": technical_specs["video_codec"],
            "analytics_scheme": technical_specs["analytics_scheme"],
            "timezone": technical_specs["timezone"],
            "cloud_adapter_version": technical_specs["cloud_adapter_version"],
            # Capabilities
            "ptz_enabled": capabilities["ptz"],
            "talkback_enabled": capabilities["talkback"],
            "audio_enabled": capabilities["audio"],
            "rom_enabled": capabilities["rom"],
            "analytics_enabled": capabilities["analytics"],
            "cloud_recording_enabled": capabilities["cloud_recording"],
            "mainstream_live": capabilities["mainstream_live"],
            # Network info
            "mac_address": self.device_data.get("macAddress", "Unknown"),
            "logger_server": self.device_data.get("logger", ""),
            "wowza_server": self.device_data.get("wowza", ""),
            "local_live_hosts": self.device_data.get("localLiveHosts", []),
            "tags": self.device_data.get("tags", []),
        }
        return attributes
    
    async def async_will_remove_from_hass(self) -> None:
        """Called when entity will be removed from hass."""
        _LOGGER.debug("Cleaning up camera entity: %s", self._attr_name)
        
        # Stop the keep-alive task by canceling current tasks
        try:
            # Get all running tasks for this entity
            current_task = asyncio.current_task()
            all_tasks = [task for task in asyncio.all_tasks() if task != current_task]
            
            # Cancel tasks that might be related to this camera
            for task in all_tasks:
                if hasattr(task, '_context') and self.uidd in str(task):
                    task.cancel()
                    _LOGGER.debug("Cancelled task for camera %s", self._attr_name)
                    
        except Exception as e:
            _LOGGER.debug("Error during camera cleanup: %s", e)

    @property
    def should_poll(self) -> bool:
        """Return if entity should be polled."""
        return False

# ----------------------------------------------------------
# CAMERA STREAM VIEW
# ----------------------------------------------------------

class VideoloftCameraStreamView(HomeAssistantView):
    """A view that proxies the camera stream and handles HLS streams efficiently."""

    url = "/api/videoloft/stream/{uidd}/{path:.*}"
    name = "api:videoloft:stream"
    requires_auth = False

    def __init__(self, hass, api, max_connections=150):
        """Initialize the stream view with optimized connection management."""
        self.hass = hass
        self.api = api
        from aiohttp import TCPConnector, ClientSession, ClientTimeout, CookieJar
        
        # Optimized connector for low-latency surveillance streaming
        connector = TCPConnector(
            limit=200,                         # Increased connection pool for more cameras
            limit_per_host=40,                 # More connections per camera server
            ttl_dns_cache=600,                 # DNS cache for 10 minutes
            use_dns_cache=True,
            keepalive_timeout=60,              # Longer keep-alive for persistent connections
            enable_cleanup_closed=True,
            force_close=False,
        )
        
        # Aggressive timeout configuration for low latency
        timeout = ClientTimeout(
            total=10,       # Shorter total request timeout
            connect=3,      # Faster connection timeout
            sock_read=8     # Socket read timeout
        )
        
        self.session = ClientSession(
            connector=connector,
            timeout=timeout,
            read_bufsize=131072, # 128KB read buffer for smoother streaming
            cookie_jar=CookieJar(unsafe=True), # Disable cookie processing
            headers={"Connection": "keep-alive"} # Ensure keep-alive
        )

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
            # Use session-level timeout, no need to override
            async with self.session.get(target_url, headers=headers) as upstream_resp:
                if upstream_resp.status == 200:
                    content_type = upstream_resp.headers.get("Content-Type", "application/vnd.apple.mpegurl")

                    if "mpegurl" in content_type or target_url.endswith(".m3u8"):
                        playlist_content = await upstream_resp.text()
                        rewritten_playlist = self.rewrite_m3u8_playlist(playlist_content, uidd)
                        return web.Response(body=rewritten_playlist, content_type=content_type)
                    else:
                        return await self.stream_segment_optimized(request, upstream_resp)
                elif upstream_resp.status == 404:
                    _LOGGER.warning(f"Received 404 for stream of camera {uidd}. Reinitializing stream.")
                    await camera_entity.reinitialize_stream()
                    # Also trigger a quick refresh attempt
                    self.hass.async_create_task(camera_entity.force_stream_refresh())
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
        """Get optimized authorization headers for streaming requests."""
        token = await self.api.get_token()
        return {
            "Authorization": f"ManythingToken {token}",
            "User-Agent": "VideoloftHA/1.0",
            "Accept": "*/*",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive"
        }

    async def stream_segment_optimized(self, request, upstream_resp):
        """Optimized streaming of video segments with backpressure handling."""
        headers = {
            "Content-Type": upstream_resp.headers.get("Content-Type", "video/MP2T"),
            "Cache-Control": "public, max-age=10", # Slightly longer cache for stability
            "Access-Control-Allow-Origin": "*",
            "Accept-Ranges": "bytes",
        }
        if "Content-Length" in upstream_resp.headers:
            headers["Content-Length"] = upstream_resp.headers["Content-Length"]

        resp = web.StreamResponse(headers=headers)
        await resp.prepare(request)

        try:
            # Use a smaller chunk size for lower latency
            async for chunk in upstream_resp.content.iter_chunked(32768):
                await resp.write(chunk)
            await resp.write_eof()
        except asyncio.CancelledError:
            _LOGGER.debug("Stream for segment cancelled by client.")
        except Exception as e:
            _LOGGER.error(f"Error during segment streaming: {e}")
        finally:
            return resp
    
    async def stream_segment(self, request, upstream_resp):
        """Fallback method for compatibility - redirects to optimized version."""
        return await self.stream_segment_optimized(request, upstream_resp)

    async def handle_upstream_error(self, upstream_resp, uidd) -> web.Response:
        """Handle errors from upstream responses."""
        error_text = await upstream_resp.text()
        _LOGGER.error(f"Failed to fetch stream for {uidd}: {upstream_resp.status} - {error_text}")
        return web.Response(status=upstream_resp.status, text=error_text)

    def rewrite_m3u8_playlist(self, playlist_content: str, uidd: str) -> bytes:
        """Rewrite URLs in the M3U8 playlist to proxy through our endpoint."""
        base_url = f"/api/videoloft/stream/{uidd}/"
        # Efficiently replace segment URLs
        rewritten_content = "\n".join(
            f"{base_url}{line.split('/')[-1]}" if not line.startswith("#") else line
            for line in playlist_content.splitlines()
        )
        return rewritten_content.encode("utf-8")
