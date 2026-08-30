"""Constants for the Cult Smart Scale integration."""

DOMAIN = "cult_smart_scale"

# Bluetooth & GATT UUIDs
SCALE_SERVICE_UUID = "0000fff0-0000-1000-8000-00805f9b34fb"
SCALE_NOTIFY_CHAR_UUID = "0000fff4-0000-1000-8000-00805f9b34fb"
BATTERY_LEVEL_CHAR_UUID = "00002a19-0000-1000-8000-00805f9b34fb"

# Manufacturer ID (Company Identifier 0xFF50)
CULT_SCALE_MANUFACTURER_ID = 0xFF50
DEFAULT_SCALE_NAME = "Cult Smart Scale"

# Configuration Keys
CONF_MAC = "mac"
CONF_USERS = "users"
CONF_MATCHING_MODE = "matching_mode"

# User Profile Configuration Keys
CONF_USER_ID = "user_id"
CONF_USER_NAME = "name"
CONF_PERSON_ENTITY = "person_entity"
CONF_HEIGHT = "height"
CONF_AGE = "age"
CONF_GENDER = "gender"
CONF_IS_ATHLETE = "is_athlete"
CONF_TARGET_WEIGHT = "target_weight"
CONF_WEIGHT_TOLERANCE = "weight_tolerance"
CONF_TARGET_IMPEDANCE = "target_impedance"
CONF_IMPEDANCE_TOLERANCE = "impedance_tolerance"

# Matching Modes
MATCHING_MODE_AUTO = "auto"
MATCHING_MODE_MANUAL = "manual"

# Default Tolerances & Timers
DEFAULT_WEIGHT_TOLERANCE = 3.5  # kg
DEFAULT_IMPEDANCE_TOLERANCE = 60  # Ohms
HEART_RATE_TIMEOUT = 10.0  # seconds to wait for heart rate pulse measurement

# Events
EVENT_READING_RECEIVED = "cult_smart_scale_reading_received"
EVENT_UNASSIGNED_READING = "cult_smart_scale_unassigned_reading"

# Services
SERVICE_ASSIGN_READING = "assign_reading"
ATTR_USER_ID = "user_id"
