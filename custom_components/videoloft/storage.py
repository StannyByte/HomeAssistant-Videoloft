# storage.py
"""Storage handling for Videoloft integration."""
from homeassistant.helpers import storage
from homeassistant.core import HomeAssistant
from .const import (
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