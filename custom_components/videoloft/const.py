"""Constants for the Videoloft integration."""

DOMAIN = "videoloft"
PLATFORMS = ["camera", "sensor"]

# Storage Constants
LPR_STORAGE_VERSION = 1
LPR_STORAGE_KEY = "videoloft_lpr_triggers"
LPR_TRIGGER_STORAGE_KEY = "lpr_triggers"  # Key to store LPR triggers in hass.data

# Import these from config_flow to avoid duplication
LPR_TRIGGERS_STORAGE_VERSION = 1
LPR_TRIGGERS_STORAGE_KEY = "lpr_triggers"

# Generic Storage Constants
STORAGE_VERSION = 1
STORAGE_KEY = "videoloft_triggers"

# Videoloft API Endpoints
AUTH_SERVER = "https://auth1.manything.com"

# Default timing intervals (in seconds)
DEFAULT_TOKEN_EXPIRY = 1200  # 20 minutes
KEEPALIVE_INTERVAL = 30  # Interval to send livecommand tasks

# Icons for entity representation
ICON_CAMERA = "mdi:cctv"
ICON_LPR_SENSOR = "mdi:license"

# Timeout settings
SESSION_TIMEOUT = 30  # Timeout for HTTP sessions in seconds

# Sensor Attributes
ATTR_LICENSE_PLATE = "license_plate"
ATTR_MAKE = "make"
ATTR_MODEL = "model"
ATTR_COLOR = "color"
ATTR_TIMESTAMP = "timestamp"
ATTR_ALERTID = "alertid"
ATTR_RECORDING_URL = "recording_url"

# Default Values
DEFAULT_POLL_INTERVAL = 10  # seconds
LOOKBACK_PERIOD_HOURS = 3