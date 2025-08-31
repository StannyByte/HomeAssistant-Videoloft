# storage.py
"""Storage handling for Videoloft integration."""
from homeassistant.helpers import storage
from homeassistant.core import HomeAssistant
from ..const import (
    LPR_STORAGE_VERSION,
    LPR_STORAGE_KEY,
    DOMAIN,
)

# ----------------------------------------------------------
# STORAGE CLASSES
# ----------------------------------------------------------

class TriggersStore:
    """Class to handle storage of LPR triggers."""
    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the storage."""
        self.hass = hass
        self._store = storage.Store(
            hass,
            LPR_STORAGE_VERSION,
            f"{DOMAIN}_{LPR_STORAGE_KEY}"
        )

    async def async_load(self):
        """Load triggers from storage."""
        return await self._store.async_load() or []

    async def async_save(self, data):
        """Save triggers to storage."""
        await self._store.async_save(data)


class GlobalStreamStateStore:
    """Class to handle storage of global streaming state."""
    
    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the storage."""
        self.hass = hass
        self._store = storage.Store(
            hass,
            1,  # Version
            f"{DOMAIN}_global_stream_state"
        )
        self._default_state = {
            "enabled": True,  # Default to streams enabled
            "last_updated": None
        }

    async def async_load(self):
        """Load global stream state from storage."""
        data = await self._store.async_load()
        if data is None:
            # Return default state if no saved state exists
            return self._default_state.copy()
        return data

    async def async_save(self, data):
        """Save global stream state to storage."""
        await self._store.async_save(data)


class ApiKeyStore:
    """Store and retrieve the Gemini API key for the integration.

    The key is stored once per Home Assistant instance (domain-level),
    so it is available to all config entries and all devices/browsers.
    We never echo the key back to clients; callers should only ask for
    a boolean "has_key" state.
    """

    _STORAGE_KEY = f"{DOMAIN}_gemini_key"

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self._store = storage.Store(hass, 1, self._STORAGE_KEY)

    async def async_has_key(self) -> bool:
        try:
            data = await self._store.async_load() or {}
            return bool(data.get("gemini_api_key"))
        except Exception:
            return False

    async def async_get_key(self) -> str | None:
        try:
            data = await self._store.async_load() or {}
            return data.get("gemini_api_key")
        except Exception:
            return None

    async def async_set_key(self, key: str) -> None:
        # Persist the key with minimal metadata. Do not log the key.
        await self._store.async_save({
            "gemini_api_key": key,
            "updated": self.hass.loop.time(),
        })

    async def async_clear_key(self) -> None:
        # Remove the file entirely to keep lifecycle clean
        await self._store.async_remove()
