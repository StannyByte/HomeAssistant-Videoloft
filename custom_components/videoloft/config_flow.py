# config_flow.py

"""Config flow for Videoloft integration."""
from __future__ import annotations

import logging
import voluptuous as vol

from aiohttp import ClientError
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import storage
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD

from .const import (
    DOMAIN,
    LPR_STORAGE_VERSION,
    LPR_STORAGE_KEY,
    LPR_TRIGGER_STORAGE_KEY,
)
from .api import VideoloftAPI

_LOGGER = logging.getLogger(__name__)

# Define the storage schema for LPR triggers
LPR_TRIGGERS_STORAGE_KEY = "lpr_triggers"
LPR_TRIGGERS_STORAGE_VERSION = 1

LPR_STORAGE_VERSION = 1
LPR_STORAGE_KEY = "videoloft_lpr_triggers"

class VideoloftConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Videoloft."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self.api = None

    async def async_step_user(self, user_input=None) -> FlowResult:
        """Handle the initial step."""
        errors = {}

        if user_input is not None:
            # Check if already configured
            await self.async_set_unique_id(user_input[CONF_EMAIL])
            self._abort_if_unique_id_configured()

            self.api = VideoloftAPI(
                user_input[CONF_EMAIL], user_input[CONF_PASSWORD], self.hass
            )
            try:
                await self.api.authenticate()
            except ClientError as e:
                _LOGGER.error(f"Network error during authentication: {e}")
                errors["base"] = "cannot_connect"
            except Exception as e:
                _LOGGER.error(f"Authentication failed: {e}")
                errors["base"] = "invalid_auth"

            if not errors:
                # Initialize LPR triggers storage
                try:
                    store = storage.Store(
                        self.hass,
                        LPR_TRIGGERS_STORAGE_VERSION,
                        f"{DOMAIN}_lpr_triggers_{user_input[CONF_EMAIL]}"
                    )
                    await store.async_save([])  # Initialize with empty list
                except Exception as e:
                    _LOGGER.error(f"Failed to initialize LPR triggers storage: {e}")

                return self.async_create_entry(
                    title=user_input[CONF_EMAIL],
                    data=user_input,
                )

        data_schema = vol.Schema(
            {
                vol.Required(CONF_EMAIL): str,
                vol.Required(CONF_PASSWORD): str,
            }
        )

        return self.async_show_form(
            step_id="user", data_schema=data_schema, errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        return VideoloftOptionsFlowHandler(config_entry)


class VideoloftOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle an option flow for Videoloft."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize the options flow."""
        self.config_entry = config_entry
        # Store will be initialized in async_step_init since we need hass

    async def async_step_init(self, user_input=None) -> FlowResult:
        """Manage the options."""
        if user_input is not None:
            # Save the updated LPR triggers
            await self._save_triggers(user_input.get("lpr_triggers", []))
            return self.async_create_entry(title="", data=user_input)

        # Load existing LPR triggers
        try:
            data = await self._load_triggers()
        except Exception as e:
            _LOGGER.error(f"Error loading LPR triggers: {e}")
            data = []

        data_schema = vol.Schema({
            vol.Optional("lpr_triggers", default=data): vol.All(
                cv.ensure_list,
                [vol.Schema({
                    vol.Required("uidd"): str,
                    vol.Required("license_plate"): str,
                    vol.Optional("make", default=""): str,
                    vol.Optional("model", default=""): str, 
                    vol.Optional("color", default=""): str,
                })]
            )
        })

        return self.async_show_form(
            step_id="init",
            data_schema=data_schema,
            description_placeholders={}
        )

    async def _get_storage(self):
        store = storage.Store(
            self.hass, 
            LPR_STORAGE_VERSION,
            f"{DOMAIN}_{LPR_STORAGE_KEY}_{self.config_entry.entry_id}"
        )
        return store

    async def _load_triggers(self):
        store = await self._get_storage()
        return await store.async_load() or []

    async def _save_triggers(self, triggers):
        store = await self._get_storage()
        await store.async_save(triggers)
