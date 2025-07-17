"""Constants for the Videoloft integration."""

# ----------------------------------------------------------
# CORE INTEGRATION CONSTANTS
# ----------------------------------------------------------

DOMAIN = "videoloft"
PLATFORMS = ["camera", "sensor", "binary_sensor", "switch", "select"]

# ----------------------------------------------------------
# STORAGE CONSTANTS
# ----------------------------------------------------------

# Storage Constants
STORAGE_VERSION = 1
LPR_STORAGE_VERSION = 1
LPR_STORAGE_KEY = "videoloft_lpr_triggers"
LPR_TRIGGER_STORAGE_KEY = "lpr_triggers"  # Key to store LPR triggers in hass.data

# ----------------------------------------------------------
# API CONFIGURATION
# ----------------------------------------------------------

# Videoloft API Endpoints
# auth1.manything.com is a global entry point that automatically redirects to the nearest regional authenticator
# The actual authenticator will be determined during the login process and stored in the API instance
AUTH_SERVER = "https://auth1.manything.com"

# Default timing intervals (in seconds)
DEFAULT_TOKEN_EXPIRY = 1200  # 20 minutes
KEEPALIVE_INTERVAL = 30  # Interval to send livecommand tasks

# Timeout settings
SESSION_TIMEOUT = 30  # Timeout for HTTP sessions in seconds

# ----------------------------------------------------------
# ENTITY ICONS
# ----------------------------------------------------------

# Icons for entity representation
ICON_CAMERA = "mdi:cctv"
ICON_LPR_SENSOR = "mdi:license"

# ----------------------------------------------------------
# SENSOR ATTRIBUTES
# ----------------------------------------------------------

# Sensor Attributes
ATTR_LICENSE_PLATE = "license_plate"
ATTR_MAKE = "make"
ATTR_MODEL = "model"
ATTR_COLOR = "color"
ATTR_TIMESTAMP = "timestamp"
ATTR_ALERTID = "alertid"
ATTR_RECORDING_URL = "recording_url"

# ----------------------------------------------------------
# DEVICE CAPABILITIES
# ----------------------------------------------------------

# Device Capabilities
ATTR_PTZ_ENABLED = "ptz_enabled"
ATTR_TALKBACK_ENABLED = "talkback_enabled"
ATTR_AUDIO_ENABLED = "audio_enabled"
ATTR_ROM_ENABLED = "rom_enabled"
ATTR_ANALYTICS_ENABLED = "analytics_enabled"

# ----------------------------------------------------------
# TECHNICAL SPECIFICATIONS
# ----------------------------------------------------------

# Technical Specifications
ATTR_RECORDING_RESOLUTION = "recording_resolution"
ATTR_VIDEO_CODEC = "video_codec"
ATTR_ANALYTICS_SCHEME = "analytics_scheme"
ATTR_CLOUD_ADAPTER_VERSION = "cloud_adapter_version"

# ----------------------------------------------------------
# NETWORK CONFIGURATION
# ----------------------------------------------------------

# Network Configuration
ATTR_LOGGER_SERVER = "logger_server"
ATTR_WOWZA_SERVER = "wowza_server"
ATTR_STREAM_NAME = "stream_name"

# ----------------------------------------------------------
# DEVICE IDENTIFICATION
# ----------------------------------------------------------

# Device Identification
ATTR_CAMERA_ID = "camera_id"
ATTR_MAC_ADDRESS = "mac_address"
ATTR_CLOUD_ADAPTER_ID = "cloud_adapter_id"

# ----------------------------------------------------------
# STATUS MONITORING
# ----------------------------------------------------------

# Status Monitoring
ATTR_MAINSTREAM_LIVE = "mainstream_live"
ATTR_CLOUD_RECORDING_ENABLED = "cloud_recording_enabled"
ATTR_LAST_LOGGER = "last_logger"

# ----------------------------------------------------------
# DEFAULT VALUES & INTERVALS
# ----------------------------------------------------------

# Default Values
DEFAULT_POLL_INTERVAL = 30  # seconds
LOOKBACK_PERIOD_HOURS = 3

# Update intervals for different sensor types
CONNECTIVITY_UPDATE_INTERVAL = 300  # 5 minutes
FIRMWARE_UPDATE_INTERVAL = 43200    # 12 hours  
STATUS_UPDATE_INTERVAL = 300        # 5 minutes