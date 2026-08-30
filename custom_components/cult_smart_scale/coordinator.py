"""DataUpdateCoordinator for Cult Smart Scale."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from bleak import BleakClient
from bleak.backends.characteristic import BleakGATTCharacteristic
from bleak.backends.device import BLEDevice
from bleak_retry_connector import BleakClientWithServiceCache, establish_connection

from homeassistant.components import bluetooth
from homeassistant.components.bluetooth import (
    BluetoothCallbackMatcher,
    BluetoothScanningMode,
    BluetoothServiceInfoBleak,
    async_ble_device_from_address,
    async_register_callback,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .body_metrics import (
    ScaleReading,
    UserProfile,
    calculate_body_composition,
    decode_impedance,
    verify_checksum,
)
from .const import (
    BATTERY_LEVEL_CHAR_UUID,
    CONF_AGE,
    CONF_GENDER,
    CONF_HEIGHT,
    CONF_IMPEDANCE_TOLERANCE,
    CONF_IS_ATHLETE,
    CONF_MAC,
    CONF_MATCHING_MODE,
    CONF_PERSON_ENTITY,
    CONF_TARGET_IMPEDANCE,
    CONF_TARGET_WEIGHT,
    CONF_USER_ID,
    CONF_USER_NAME,
    CONF_USERS,
    CONF_WEIGHT_TOLERANCE,
    DEFAULT_IMPEDANCE_TOLERANCE,
    DEFAULT_WEIGHT_TOLERANCE,
    DOMAIN,
    EVENT_READING_RECEIVED,
    EVENT_UNASSIGNED_READING,
    HEART_RATE_TIMEOUT,
    LEFU_MANUFACTURER_ID,
    MATCHING_MODE_AUTO,
    SCALE_NOTIFY_CHAR_UUID,
)

_LOGGER = logging.getLogger(__name__)


class CultScaleDataUpdateCoordinator(DataUpdateCoordinator[None]):
    """Coordinates scale data parsing, Bluetooth communication, and person matching."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{entry.data[CONF_MAC]}",
        )
        self.entry = entry
        self.mac = entry.data[CONF_MAC].lower()
        self.matching_mode = entry.options.get(
            CONF_MATCHING_MODE,
            entry.data.get(CONF_MATCHING_MODE, MATCHING_MODE_AUTO),
        )

        self.users: Dict[str, UserProfile] = {}
        self._load_users()

        # State tracking
        self.last_reading: Optional[ScaleReading] = None
        self.last_reading_time: Optional[datetime] = None
        self.last_user_name: str = "None"
        self.last_unassigned_reading: Optional[ScaleReading] = None
        self.battery_level: Optional[int] = None
        self.is_connected: bool = False
        self._last_stabilized_state: Optional[tuple] = None

        # Per-user latest readings: user_id -> ScaleReading
        self.user_readings: Dict[str, ScaleReading] = {}

        self._client: Optional[BleakClient] = None
        self._sub_cancel: Optional[Any] = None
        self._active_connection_task: Optional[asyncio.Task] = None
        self._active_measuring_reading: Optional[ScaleReading] = None
        self._pending_finalize_timer: Optional[asyncio.TimerHandle] = None

    def _load_users(self) -> None:
        """Load user profiles from config entry options or data."""
        raw_users = self.entry.options.get(
            CONF_USERS, self.entry.data.get(CONF_USERS, [])
        )
        self.users.clear()
        for u in raw_users:
            profile = UserProfile(
                user_id=u[CONF_USER_ID],
                name=u[CONF_USER_NAME],
                person_entity=u.get(CONF_PERSON_ENTITY),
                height_cm=float(u[CONF_HEIGHT]),
                age=int(u[CONF_AGE]),
                gender=u[CONF_GENDER],
                is_athlete=bool(u.get(CONF_IS_ATHLETE, False)),
                target_weight=float(u.get(CONF_TARGET_WEIGHT, 75.0)),
                weight_tolerance=float(u.get(CONF_WEIGHT_TOLERANCE, DEFAULT_WEIGHT_TOLERANCE)),
                target_impedance=int(u[CONF_TARGET_IMPEDANCE]) if u.get(CONF_TARGET_IMPEDANCE) else None,
                impedance_tolerance=int(u.get(CONF_IMPEDANCE_TOLERANCE, DEFAULT_IMPEDANCE_TOLERANCE)),
            )
            self.users[profile.user_id] = profile

    async def async_start(self) -> None:
        """Start listening for Bluetooth advertisements and connecting."""
        _LOGGER.debug(
            "Starting Bluetooth tracker for MAC: %s (Profiles: %s, Mode: %s)",
            self.mac,
            [u.name for u in self.users.values()],
            self.matching_mode,
        )

        # Register callback for BLE advertisements from local BLE or ESP32 Bluetooth Proxy
        self._sub_cancel = async_register_callback(
            self.hass,
            self._async_handle_bluetooth_event,
            BluetoothCallbackMatcher(),
            BluetoothScanningMode.ACTIVE,
        )

    async def async_stop(self) -> None:
        """Stop listening and disconnect BLE."""
        if self._pending_finalize_timer:
            self._pending_finalize_timer.cancel()
            self._pending_finalize_timer = None

        if self._sub_cancel:
            self._sub_cancel()
            self._sub_cancel = None

        if self._active_connection_task and not self._active_connection_task.done():
            self._active_connection_task.cancel()

        if self._client and self._client.is_connected:
            try:
                await self._client.disconnect()
            except Exception:
                pass
        _LOGGER.debug("Cult Scale Bluetooth tracker stopped.")

    @callback
    def _async_handle_bluetooth_event(
        self,
        service_info: BluetoothServiceInfoBleak,
        change: bluetooth.BluetoothChange,
    ) -> None:
        """Handle incoming Bluetooth advertisement or connection event."""
        # Filter for this scale's MAC address (case-insensitive)
        if service_info.address.lower() != self.mac.lower():
            return

        adv_data = service_info.advertisement
        device = service_info.device

        _LOGGER.debug(
            "BLE packet from %s (RSSI: %s dBm, Mfr IDs: %s)",
            service_info.address,
            service_info.rssi,
            list(adv_data.manufacturer_data.keys()),
        )

        # Check manufacturer data for broadcast live weight (both hex 0xFF50 and decimal 65360)
        m_data = adv_data.manufacturer_data.get(LEFU_MANUFACTURER_ID) or adv_data.manufacturer_data.get(65360)
        if m_data:
            if len(m_data) >= 17:
                scale_frame = m_data[6:17]
                self._handle_raw_frame(scale_frame)
            elif len(m_data) == 11:
                self._handle_raw_frame(m_data)

        # If scale is advertising, launch active GATT connection task if not already connecting
        if (
            not self.is_connected
            and (self._active_connection_task is None or self._active_connection_task.done())
        ):
            _LOGGER.debug("Scale is advertising, launching GATT connection task...")
            self._active_connection_task = self.hass.async_create_task(
                self._async_connect_and_subscribe(device)
            )

    @callback
    def _async_handle_disconnect(self, client: BleakClient) -> None:
        """Handle GATT disconnection (e.g. scale powers off after weigh-in)."""
        _LOGGER.debug("Scale GATT disconnected.")
        self.is_connected = False
        self._client = None
        if self._pending_finalize_timer:
            self._pending_finalize_timer.cancel()
            self._pending_finalize_timer = None
        if self._active_measuring_reading and not self._active_measuring_reading.is_finalized:
            self._finalize_current_reading()
        self.async_update_listeners()

    async def _async_connect_and_subscribe(self, device: BLEDevice) -> None:
        """Connect to scale GATT server and subscribe to notifications via bleak-retry-connector."""
        _LOGGER.debug("Attempting GATT connection to %s via Proxy...", device.address)
        client: BleakClient | None = None
        try:
            connectable_device = async_ble_device_from_address(
                self.hass, self.mac, connectable=True
            ) or device

            client = await establish_connection(
                BleakClientWithServiceCache,
                connectable_device,
                self.name,
                disconnected_callback=self._async_handle_disconnect,
                max_attempts=2,
                use_services_cache=True,
            )
            self._client = client
            self.is_connected = True
            _LOGGER.debug("Connected to Cult Smart Scale GATT on %s", device.address)

            # Read battery
            try:
                bat_bytes = await client.read_gatt_char(BATTERY_LEVEL_CHAR_UUID)
                if bat_bytes:
                    self.battery_level = bat_bytes[0]
                    self.async_update_listeners()
            except Exception as err:
                _LOGGER.debug("Could not read battery: %s", err)

            # Start notify for Scale data (0xFFF4)
            await client.start_notify(
                SCALE_NOTIFY_CHAR_UUID, self._gatt_notification_handler
            )
            _LOGGER.debug("Subscribed to Scale GATT notifications (0xFFF4)")

            # Keep connection alive while measuring (scale drops connection when done)
            while client.is_connected:
                await asyncio.sleep(1.0)

        except Exception as err:
            _LOGGER.debug("GATT connection to scale ended or closed: %s", err)
        finally:
            if client and client.is_connected:
                try:
                    await client.disconnect()
                except Exception:
                    pass
            self.is_connected = False
            self._client = None
            if self._pending_finalize_timer:
                self._pending_finalize_timer.cancel()
                self._pending_finalize_timer = None
            if self._active_measuring_reading and not self._active_measuring_reading.is_finalized:
                self._finalize_current_reading()
            self.async_update_listeners()

    def _gatt_notification_handler(
        self, sender: BleakGATTCharacteristic, data: bytearray
    ) -> None:
        """Handle raw GATT notifications on 0xFFF4."""
        self._handle_raw_frame(bytes(data))

    def _handle_raw_frame(self, data: bytes) -> None:
        """Process 11-byte binary scale packet."""
        if len(data) != 11 or data[0] != 0xCF or not verify_checksum(data):
            return

        byte1 = data[1]
        byte2 = data[2]

        # Heart rate packet (Byte 2 = 0xC0)
        if byte2 == 0xC0 and byte1 > 0:
            _LOGGER.debug("Scale heart rate captured: %d BPM", byte1)
            target = self._active_measuring_reading or self.last_reading
            if target and target.is_stabilized:
                target.heart_rate_bpm = byte1

                if target.is_finalized:
                    self.async_update_listeners()
                    return

                self._finalize_current_reading()
                return

        weight_raw = data[3] | (data[4] << 8)
        weight_kg = weight_raw / 100.0
        is_stabilized = (byte2 & 0x80) != 0
        has_impedance = (byte2 & 0x10) != 0

        reading = ScaleReading(
            weight_kg=weight_kg,
            is_stabilized=is_stabilized,
            raw_hex=data.hex(),
            heart_rate_bpm=None,  # Never reuse stale heart rate
        )

        if has_impedance:
            enc_imp = data[5] | (data[6] << 8) | (data[7] << 16)
            ohms = decode_impedance(enc_imp)
            reading.impedance_raw = enc_imp
            reading.impedance_ohms = ohms

        _LOGGER.debug(
            "Scale packet: Weight: %.2f kg | Stabilized: %s | Impedance: %s Ω",
            weight_kg,
            is_stabilized,
            reading.impedance_ohms,
        )

        if is_stabilized and reading.weight_kg > 0:
            self.last_reading = reading
            self.last_reading_time = datetime.now(timezone.utc)
            curr_state = (reading.weight_kg, reading.impedance_ohms)
            if self._last_stabilized_state != curr_state:
                self._last_stabilized_state = curr_state
                self._active_measuring_reading = reading

                # Wait up to HEART_RATE_TIMEOUT seconds for heart rate packet before finalizing
                if self._pending_finalize_timer:
                    self._pending_finalize_timer.cancel()
                self._pending_finalize_timer = self.hass.loop.call_later(
                    HEART_RATE_TIMEOUT, self._finalize_current_reading
                )
        else:
            # Only update live reading if not currently holding an unfinalized stabilized weigh-in
            if not self._active_measuring_reading or self._active_measuring_reading.is_finalized:
                self.last_reading = reading
                self.last_reading_time = datetime.now(timezone.utc)
                self.async_update_listeners()

    @callback
    def _finalize_current_reading(self) -> None:
        """Finalize scale reading after stabilization and heart rate capture."""
        if self._pending_finalize_timer:
            self._pending_finalize_timer.cancel()
            self._pending_finalize_timer = None

        reading = self._active_measuring_reading or self.last_reading
        if not reading or not reading.is_stabilized or reading.is_finalized:
            return

        reading.is_finalized = True
        self._active_measuring_reading = None
        self._last_stabilized_state = None

        if self.matching_mode == MATCHING_MODE_AUTO and self.users:
            matched_user = self._match_reading_to_user(reading)
            if matched_user:
                _LOGGER.info(
                    "Cult Smart Scale: %.2f kg, %d Ω, %s BPM assigned to %s",
                    reading.weight_kg,
                    reading.impedance_ohms,
                    f"{reading.heart_rate_bpm} BPM" if reading.heart_rate_bpm else "No HR",
                    matched_user.name,
                )
                self._assign_reading_to_user(matched_user, reading)
                return

        # Fallback / Manual confirmation
        _LOGGER.info(
            "Cult Smart Scale: %.2f kg, %d Ω, %s recorded (Unassigned / Guest)",
            reading.weight_kg,
            reading.impedance_ohms,
            f"{reading.heart_rate_bpm} BPM" if reading.heart_rate_bpm else "No HR",
        )
        self.last_unassigned_reading = reading
        self.last_user_name = "Unassigned / Guest"
        self.async_update_listeners()

        # Fire unassigned reading event
        self.hass.bus.async_fire(
            EVENT_UNASSIGNED_READING,
            {
                "is_assigned": False,
                "weight_kg": reading.weight_kg,
                "impedance_ohms": reading.impedance_ohms,
                "heart_rate_bpm": reading.heart_rate_bpm,
                "battery_level": self.battery_level,
                "timestamp": self.last_reading_time.isoformat() if self.last_reading_time else None,
            },
        )

    def _match_reading_to_user(self, reading: ScaleReading) -> Optional[UserProfile]:
        """Find a uniquely matching user profile based on weight and impedance."""
        matching_users: List[UserProfile] = []

        for user in self.users.values():
            w_diff = abs(reading.weight_kg - user.target_weight)
            if w_diff <= user.weight_tolerance:
                if user.target_impedance and reading.impedance_ohms > 0:
                    imp_diff = abs(reading.impedance_ohms - user.target_impedance)
                    if imp_diff <= user.impedance_tolerance:
                        matching_users.append(user)
                else:
                    matching_users.append(user)

        if len(matching_users) == 1:
            return matching_users[0]
        return None

    def _assign_reading_to_user(
        self, user: UserProfile, reading: ScaleReading
    ) -> None:
        """Calculate metrics and log reading to a specific user profile."""
        metrics = calculate_body_composition(
            weight_kg=reading.weight_kg,
            impedance_ohms=reading.impedance_ohms,
            user=user,
        )
        reading.body_metrics = metrics
        self.user_readings[user.user_id] = reading
        self.last_user_name = user.name
        self.last_unassigned_reading = None

        # Dynamically adjust target weight baseline
        user.target_weight = reading.weight_kg
        if reading.impedance_ohms > 0:
            user.target_impedance = reading.impedance_ohms

        self.async_update_listeners()

        # Fire unified measurement event with all metrics at top level for easy automation templating
        event_payload = {
            "user_id": user.user_id,
            "user_name": user.name,
            "person_entity": user.person_entity,
            "heart_rate_bpm": reading.heart_rate_bpm,
            "battery_level": self.battery_level,
            "timestamp": self.last_reading_time.isoformat() if self.last_reading_time else None,
            "is_assigned": True,
            "matching_mode": self.matching_mode,
            **metrics,
            "metrics": metrics,
        }
        self.hass.bus.async_fire(EVENT_READING_RECEIVED, event_payload)

    async def async_assign_reading(
        self,
        user_id_or_person: str,
        reading: Optional[ScaleReading] = None,
    ) -> bool:
        """Service call handler to manually assign reading to a person."""
        target_user: Optional[UserProfile] = None

        identifier = user_id_or_person.strip().lower()
        for u in self.users.values():
            if (
                u.user_id.lower() == identifier
                or (u.person_entity and u.person_entity.lower() == identifier)
                or u.name.lower() == identifier
            ):
                target_user = u
                break

        if not target_user:
            _LOGGER.warning(
                "Could not find user profile matching '%s'. Available users: %s",
                user_id_or_person,
                [u.name for u in self.users.values()],
            )
            return False

        read = reading or self.last_unassigned_reading or self._active_measuring_reading or self.last_reading
        if not read:
            _LOGGER.warning("No scale reading available to assign.")
            return False

        self._assign_reading_to_user(target_user, read)
        return True
