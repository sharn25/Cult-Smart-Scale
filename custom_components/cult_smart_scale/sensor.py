"""Sensor platform for Cult Smart Scale integration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    EntityCategory,
    PERCENTAGE,
    UnitOfMass,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .body_metrics import UserProfile
from .const import CONF_MAC, DEFAULT_SCALE_NAME, DOMAIN
from .coordinator import CultScaleDataUpdateCoordinator


@dataclass(frozen=True, kw_only=True)
class CultPersonSensorEntityDescription(SensorEntityDescription):
    """Description for person-specific body composition sensors."""

    value_fn: Callable[[Dict[str, Any]], Any] = lambda metrics: None


PERSON_SENSOR_DESCRIPTIONS: List[CultPersonSensorEntityDescription] = [
    CultPersonSensorEntityDescription(
        key="weight",
        name="Weight",
        native_unit_of_measurement=UnitOfMass.KILOGRAMS,
        device_class=SensorDeviceClass.WEIGHT,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:scale-bathroom",
        value_fn=lambda m: m.get("weight_kg"),
    ),
    CultPersonSensorEntityDescription(
        key="bmi",
        name="BMI",
        native_unit_of_measurement="kg/m²",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:calculator-variant-outline",
        value_fn=lambda m: m.get("bmi"),
    ),
    CultPersonSensorEntityDescription(
        key="body_fat",
        name="Body Fat",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:human-handsdown",
        value_fn=lambda m: m.get("body_fat_percentage"),
    ),
    CultPersonSensorEntityDescription(
        key="body_fat_mass",
        name="Body Fat Mass",
        native_unit_of_measurement=UnitOfMass.KILOGRAMS,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:human-handsdown",
        value_fn=lambda m: m.get("body_fat_kg"),
    ),
    CultPersonSensorEntityDescription(
        key="fat_free_mass",
        name="Fat-Free Mass",
        native_unit_of_measurement=UnitOfMass.KILOGRAMS,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:scale",
        value_fn=lambda m: m.get("fat_free_mass_kg"),
    ),
    CultPersonSensorEntityDescription(
        key="muscle_mass",
        name="Muscle Mass",
        native_unit_of_measurement=UnitOfMass.KILOGRAMS,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:arm-flex",
        value_fn=lambda m: m.get("muscle_mass_kg"),
    ),
    CultPersonSensorEntityDescription(
        key="muscle_percentage",
        name="Muscle Rate",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:arm-flex-outline",
        value_fn=lambda m: m.get("muscle_percentage"),
    ),
    CultPersonSensorEntityDescription(
        key="skeletal_muscle",
        name="Skeletal Muscle",
        native_unit_of_measurement=UnitOfMass.KILOGRAMS,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:arm-flex",
        value_fn=lambda m: m.get("skeletal_muscle_kg"),
    ),
    CultPersonSensorEntityDescription(
        key="body_water",
        name="Total Body Water",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:water-percent",
        value_fn=lambda m: m.get("water_percentage"),
    ),
    CultPersonSensorEntityDescription(
        key="water_mass",
        name="Water Mass",
        native_unit_of_measurement=UnitOfMass.KILOGRAMS,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:water",
        value_fn=lambda m: m.get("water_kg"),
    ),
    CultPersonSensorEntityDescription(
        key="bone_mass",
        name="Bone Mass",
        native_unit_of_measurement=UnitOfMass.KILOGRAMS,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:bone",
        value_fn=lambda m: m.get("bone_mass_kg"),
    ),
    CultPersonSensorEntityDescription(
        key="protein",
        name="Protein",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:food-drumstick-outline",
        value_fn=lambda m: m.get("protein_percentage"),
    ),
    CultPersonSensorEntityDescription(
        key="subcutaneous_fat",
        name="Subcutaneous Fat",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:human-handsup",
        value_fn=lambda m: m.get("subcutaneous_fat_percentage"),
    ),
    CultPersonSensorEntityDescription(
        key="visceral_fat",
        name="Visceral Fat Level",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:circle-slice-8",
        value_fn=lambda m: m.get("visceral_fat_level"),
    ),
    CultPersonSensorEntityDescription(
        key="bmr",
        name="Basal Metabolic Rate",
        native_unit_of_measurement="kcal",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:fire",
        value_fn=lambda m: m.get("bmr_kcal"),
    ),
    CultPersonSensorEntityDescription(
        key="metabolic_age",
        name="Metabolic Body Age",
        native_unit_of_measurement="years",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:calendar-account",
        value_fn=lambda m: m.get("body_age"),
    ),
    CultPersonSensorEntityDescription(
        key="ideal_weight",
        name="Ideal Weight",
        native_unit_of_measurement=UnitOfMass.KILOGRAMS,
        icon="mdi:target",
        value_fn=lambda m: m.get("ideal_weight_kg"),
    ),
    CultPersonSensorEntityDescription(
        key="body_type",
        name="Body Classification",
        icon="mdi:account-details",
        value_fn=lambda m: m.get("body_type"),
    ),
]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Cult Smart Scale sensors from a config entry."""
    coordinator: CultScaleDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: List[SensorEntity] = []

    # 1. Add Device-level sensors for the Scale hardware
    entities.append(CultScaleBatterySensor(coordinator, entry))
    entities.append(CultScaleLastWeightSensor(coordinator, entry))
    entities.append(CultScaleLastImpedanceSensor(coordinator, entry))
    entities.append(CultScaleLastHeartRateSensor(coordinator, entry))
    entities.append(CultScaleLastUserSensor(coordinator, entry))
    entities.append(CultScaleUnassignedWeightSensor(coordinator, entry))

    # 2. Add Person-level sensors for each configured User Profile
    for user in coordinator.users.values():
        for description in PERSON_SENSOR_DESCRIPTIONS:
            entities.append(CultPersonMetricSensor(coordinator, entry, user, description))
        entities.append(CultPersonHeartRateSensor(coordinator, entry, user))

    async_add_entities(entities)

    # 3. Clean up orphaned entities from deleted user profiles
    ent_reg = er.async_get(hass)
    active_unique_ids = {entity.unique_id for entity in entities if entity.unique_id}
    for entity_entry in er.async_entries_for_config_entry(ent_reg, entry.entry_id):
        if entity_entry.unique_id not in active_unique_ids:
            ent_reg.async_remove(entity_entry.entity_id)

    # 4. Clean up orphaned devices from deleted user profiles
    dev_reg = dr.async_get(hass)
    mac = entry.data[CONF_MAC].lower()
    active_device_identifiers = {
        (DOMAIN, mac),
        *{(DOMAIN, f"{mac}_{u.user_id}") for u in coordinator.users.values()},
    }
    for device_entry in dr.async_entries_for_config_entry(dev_reg, entry.entry_id):
        if not any(ident in active_device_identifiers for ident in device_entry.identifiers):
            dev_reg.async_remove_device(device_entry.id)


class CultScaleBaseSensor(CoordinatorEntity[CultScaleDataUpdateCoordinator], SensorEntity):
    """Base class for Cult Scale sensors."""

    _attr_has_entity_name = True

    def __init__(
        self, coordinator: CultScaleDataUpdateCoordinator, entry: ConfigEntry
    ) -> None:
        """Initialize base sensor."""
        super().__init__(coordinator)
        self.entry = entry
        self.mac = entry.data[CONF_MAC].lower()


class CultScaleBatterySensor(CultScaleBaseSensor):
    """Battery level percentage of the scale."""

    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self, coordinator: CultScaleDataUpdateCoordinator, entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator, entry)
        self._attr_name = "Battery"
        self._attr_unique_id = f"{self.mac}_battery"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self.mac)},
            name=DEFAULT_SCALE_NAME,
            manufacturer="Cult / Lefu",
            model="Cult Smart Scale (CF)",
        )

    @property
    def native_value(self) -> Optional[int]:
        return self.coordinator.battery_level


class CultScaleLastWeightSensor(CultScaleBaseSensor):
    """Last raw weight reading recorded by scale."""

    _attr_device_class = SensorDeviceClass.WEIGHT
    _attr_native_unit_of_measurement = UnitOfMass.KILOGRAMS
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:scale-bathroom"

    def __init__(
        self, coordinator: CultScaleDataUpdateCoordinator, entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator, entry)
        self._attr_name = "Last Weight"
        self._attr_unique_id = f"{self.mac}_last_weight"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self.mac)},
            name=DEFAULT_SCALE_NAME,
        )

    @property
    def native_value(self) -> Optional[float]:
        if self.coordinator.last_reading:
            return round(self.coordinator.last_reading.weight_kg, 2)
        return None


class CultScaleLastImpedanceSensor(CultScaleBaseSensor):
    """Last raw bioimpedance recorded by scale."""

    _attr_native_unit_of_measurement = "Ω"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:omega"

    def __init__(
        self, coordinator: CultScaleDataUpdateCoordinator, entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator, entry)
        self._attr_name = "Last Impedance"
        self._attr_unique_id = f"{self.mac}_last_impedance"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self.mac)},
            name=DEFAULT_SCALE_NAME,
        )

    @property
    def native_value(self) -> Optional[int]:
        if self.coordinator.last_reading and self.coordinator.last_reading.impedance_ohms > 0:
            return self.coordinator.last_reading.impedance_ohms
        return None


class CultScaleLastHeartRateSensor(CultScaleBaseSensor):
    """Last heart rate recorded by scale."""

    _attr_native_unit_of_measurement = "bpm"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:heart-pulse"

    def __init__(
        self, coordinator: CultScaleDataUpdateCoordinator, entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator, entry)
        self._attr_name = "Last Heart Rate"
        self._attr_unique_id = f"{self.mac}_last_heart_rate"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self.mac)},
            name=DEFAULT_SCALE_NAME,
        )

    @property
    def native_value(self) -> Optional[int]:
        if self.coordinator.last_reading:
            return self.coordinator.last_reading.heart_rate_bpm
        return None


class CultScaleLastUserSensor(CultScaleBaseSensor):
    """Name of the person who last weighed in."""

    _attr_icon = "mdi:account-check"

    def __init__(
        self, coordinator: CultScaleDataUpdateCoordinator, entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator, entry)
        self._attr_name = "Last User"
        self._attr_unique_id = f"{self.mac}_last_user"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self.mac)},
            name=DEFAULT_SCALE_NAME,
        )

    @property
    def native_value(self) -> str:
        return self.coordinator.last_user_name


class CultScaleUnassignedWeightSensor(CultScaleBaseSensor):
    """Pending unassigned / guest reading weight."""

    _attr_device_class = SensorDeviceClass.WEIGHT
    _attr_native_unit_of_measurement = UnitOfMass.KILOGRAMS
    _attr_icon = "mdi:account-question"

    def __init__(
        self, coordinator: CultScaleDataUpdateCoordinator, entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator, entry)
        self._attr_name = "Unassigned Weight"
        self._attr_unique_id = f"{self.mac}_unassigned_weight"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self.mac)},
            name=DEFAULT_SCALE_NAME,
        )

    @property
    def native_value(self) -> Optional[float]:
        if self.coordinator.last_unassigned_reading:
            return round(self.coordinator.last_unassigned_reading.weight_kg, 2)
        return None

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        if not self.coordinator.last_unassigned_reading:
            return {}
        r = self.coordinator.last_unassigned_reading
        return {
            "weight_kg": r.weight_kg,
            "impedance_ohms": r.impedance_ohms,
            "heart_rate_bpm": r.heart_rate_bpm,
            "raw_hex": r.raw_hex,
        }


class CultPersonMetricSensor(CoordinatorEntity[CultScaleDataUpdateCoordinator], SensorEntity):
    """Sensor for a specific body metric calculated for a specific person."""

    _attr_has_entity_name = True
    entity_description: CultPersonSensorEntityDescription

    def __init__(
        self,
        coordinator: CultScaleDataUpdateCoordinator,
        entry: ConfigEntry,
        user: UserProfile,
        description: CultPersonSensorEntityDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entry = entry
        self.user = user
        self.entity_description = description
        self.mac = entry.data[CONF_MAC].lower()

        self._attr_name = description.name
        self._attr_unique_id = f"{self.mac}_{user.user_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{self.mac}_{user.user_id}")},
            name=f"Cult Scale — {user.name}",
            manufacturer="Cult / Lefu",
            model="Cult Smart Scale User Profile",
            via_device=(DOMAIN, self.mac),
        )

    @property
    def native_value(self) -> Any:
        reading = self.coordinator.user_readings.get(self.user.user_id)
        if reading and reading.body_metrics:
            return self.entity_description.value_fn(reading.body_metrics)
        return None

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return user profile metadata."""
        return {
            "user_name": self.user.name,
            "gender": self.user.gender.value if hasattr(self.user.gender, "value") else str(self.user.gender),
            "age": self.user.age,
            "height_cm": self.user.height_cm,
            "is_athlete": self.user.is_athlete,
        }


class CultPersonHeartRateSensor(CoordinatorEntity[CultScaleDataUpdateCoordinator], SensorEntity):
    """Heart rate sensor for a specific person."""

    _attr_has_entity_name = True
    _attr_native_unit_of_measurement = "bpm"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:heart-pulse"

    def __init__(
        self,
        coordinator: CultScaleDataUpdateCoordinator,
        entry: ConfigEntry,
        user: UserProfile,
    ) -> None:
        super().__init__(coordinator)
        self.entry = entry
        self.user = user
        self.mac = entry.data[CONF_MAC].lower()

        self._attr_name = "Heart Rate"
        self._attr_unique_id = f"{self.mac}_{user.user_id}_heart_rate"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{self.mac}_{user.user_id}")},
            name=f"Cult Scale — {user.name}",
            via_device=(DOMAIN, self.mac),
        )

    @property
    def native_value(self) -> Optional[int]:
        reading = self.coordinator.user_readings.get(self.user.user_id)
        if reading:
            return reading.heart_rate_bpm
        return None

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return user profile metadata."""
        return {
            "user_name": self.user.name,
            "gender": self.user.gender.value if hasattr(self.user.gender, "value") else str(self.user.gender),
            "age": self.user.age,
            "height_cm": self.user.height_cm,
            "is_athlete": self.user.is_athlete,
        }

