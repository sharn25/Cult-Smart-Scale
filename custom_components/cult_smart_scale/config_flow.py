"""Config flow for Cult Smart Scale integration."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_discovered_service_info,
)
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from .const import (
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
    DEFAULT_SCALE_NAME,
    DEFAULT_WEIGHT_TOLERANCE,
    DOMAIN,
    LEFU_MANUFACTURER_ID,
    MATCHING_MODE_AUTO,
    MATCHING_MODE_MANUAL,
    SCALE_SERVICE_UUID,
)

_LOGGER = logging.getLogger(__name__)


class CultScaleConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Cult Smart Scale."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize config flow."""
        self._discovered_mac: Optional[str] = None
        self._discovered_name: Optional[str] = None

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> FlowResult:
        """Handle discovery from Home Assistant Bluetooth subsystem."""
        mac = discovery_info.address.lower()
        await self.async_set_unique_id(mac)
        self._abort_if_unique_id_configured()

        self._discovered_mac = mac
        self._discovered_name = discovery_info.name or DEFAULT_SCALE_NAME
        self.context["title_placeholders"] = {"name": self._discovered_name}
        return await self.async_step_bluetooth_confirm()

    async def async_step_bluetooth_confirm(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        """Confirm setup of a newly discovered Cult Smart Scale."""
        if user_input is not None:
            return self.async_create_entry(
                title=user_input.get("name", self._discovered_name or DEFAULT_SCALE_NAME),
                data={
                    CONF_MAC: self._discovered_mac,
                    CONF_MATCHING_MODE: user_input.get(CONF_MATCHING_MODE, MATCHING_MODE_AUTO),
                    CONF_USERS: [],
                },
            )

        schema = vol.Schema(
            {
                vol.Required("name", default=self._discovered_name or DEFAULT_SCALE_NAME): str,
                vol.Required(
                    CONF_MATCHING_MODE,
                    default=MATCHING_MODE_AUTO,
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            selector.SelectOptionDict(
                                value=MATCHING_MODE_AUTO,
                                label="Automatic (Weight & Impedance Thresholds)",
                            ),
                            selector.SelectOptionDict(
                                value=MATCHING_MODE_MANUAL,
                                label="Manual (Confirm via Mobile Notification)",
                            ),
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
            }
        )

        return self.async_show_form(
            step_id="bluetooth_confirm",
            data_schema=schema,
            description_placeholders={
                "name": self._discovered_name or DEFAULT_SCALE_NAME,
                "mac": self._discovered_mac or "",
            },
        )

    async def async_step_user(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        """Handle manual setup or selection of discovered scale."""
        errors: Dict[str, str] = {}

        if user_input is not None:
            mac = user_input[CONF_MAC].strip().lower()
            await self.async_set_unique_id(mac)
            self._abort_if_unique_id_configured()

            return self.async_create_entry(
                title=user_input.get("name", DEFAULT_SCALE_NAME),
                data={
                    CONF_MAC: mac,
                    CONF_MATCHING_MODE: user_input.get(CONF_MATCHING_MODE, MATCHING_MODE_AUTO),
                    CONF_USERS: [],
                },
            )

        # Scan for currently broadcasting Bluetooth scales
        discovered: Dict[str, str] = {}
        for service_info in async_discovered_service_info(self.hass):
            name = service_info.name or ""
            mac = service_info.address.lower()
            adv = service_info.advertisement
            if (
                DEFAULT_SCALE_NAME.lower() in name.lower()
                or SCALE_SERVICE_UUID.lower() in [s.lower() for s in adv.service_uuids]
                or LEFU_MANUFACTURER_ID in adv.manufacturer_data
                or 65360 in adv.manufacturer_data
            ):
                discovered[mac] = f"{name or DEFAULT_SCALE_NAME} ({mac})"

        schema_dict: Dict[Any, Any] = {}

        if discovered and not self._discovered_mac:
            # Present discovered scales in dropdown
            options = [
                selector.SelectOptionDict(value=mac, label=label)
                for mac, label in discovered.items()
            ]
            schema_dict[vol.Required(CONF_MAC, default=list(discovered.keys())[0])] = selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=options,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            )
        else:
            # Fallback to direct MAC input (e.g. scale is asleep)
            default_mac = self._discovered_mac or ""
            if default_mac:
                schema_dict[vol.Required(CONF_MAC, default=default_mac)] = str
            else:
                schema_dict[vol.Required(CONF_MAC)] = str

        schema_dict[vol.Required("name", default=DEFAULT_SCALE_NAME)] = str
        schema_dict[vol.Required(
            CONF_MATCHING_MODE,
            default=MATCHING_MODE_AUTO,
        )] = selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=[
                    selector.SelectOptionDict(
                        value=MATCHING_MODE_AUTO,
                        label="Automatic (Weight & Impedance Thresholds)",
                    ),
                    selector.SelectOptionDict(
                        value=MATCHING_MODE_MANUAL,
                        label="Manual (Confirm via Mobile Notification)",
                    ),
                ],
                mode=selector.SelectSelectorMode.DROPDOWN,
            )
        )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(schema_dict),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Get the options flow for this handler."""
        return CultScaleOptionsFlow(config_entry)


class CultScaleOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow for adding/editing user profiles and mode."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self._initial_config_entry = config_entry
        self._users_cache: Optional[List[Dict[str, Any]]] = None
        self._selected_user_index: Optional[int] = None

    @property
    def current_entry(self) -> config_entries.ConfigEntry:
        """Return the current config entry."""
        if hasattr(self, "config_entry") and self.config_entry is not None:
            return self.config_entry
        return self._initial_config_entry

    @property
    def users_list(self) -> List[Dict[str, Any]]:
        """Get or initialize users list."""
        if self._users_cache is None:
            entry = self.current_entry
            self._users_cache = list(
                entry.options.get(
                    CONF_USERS, entry.data.get(CONF_USERS, [])
                )
            )
        return self._users_cache

    async def async_step_init(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        """Manage main options menu."""
        if user_input is not None:
            action = user_input.get("action")
            if action == "add_user":
                return await self.async_step_user_profile()
            if action == "edit_user":
                return await self.async_step_select_user()
            if action == "settings":
                return await self.async_step_global_settings()

            # Save and exit
            return self.async_create_entry(
                title="",
                data={
                    CONF_USERS: self.users_list,
                    CONF_MATCHING_MODE: user_input.get(
                        CONF_MATCHING_MODE,
                        self.current_entry.options.get(CONF_MATCHING_MODE, MATCHING_MODE_AUTO),
                    ),
                },
            )

        user_count = len(self.users_list)
        options = [
            selector.SelectOptionDict(value="add_user", label="➕ Add New Person Profile"),
        ]
        if user_count > 0:
            options.append(
                selector.SelectOptionDict(
                    value="edit_user", label=f"✏️ Edit / Remove Person Profile ({user_count} configured)"
                )
            )
        options.append(selector.SelectOptionDict(value="settings", label="⚙️ Logging & Matching Mode Settings"))
        options.append(selector.SelectOptionDict(value="save", label="💾 Save & Finish"))

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required("action", default="add_user" if user_count == 0 else "save"): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=options,
                            mode=selector.SelectSelectorMode.LIST,
                        )
                    )
                }
            ),
        )

    async def async_step_global_settings(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        """Configure global logging and matching settings."""
        if user_input is not None:
            current_mode = user_input[CONF_MATCHING_MODE]
            return self.async_create_entry(
                title="",
                data={
                    CONF_USERS: self.users_list,
                    CONF_MATCHING_MODE: current_mode,
                },
            )

        current_mode = self.current_entry.options.get(
            CONF_MATCHING_MODE,
            self.current_entry.data.get(CONF_MATCHING_MODE, MATCHING_MODE_AUTO),
        )

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_MATCHING_MODE,
                    default=current_mode,
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            selector.SelectOptionDict(
                                value=MATCHING_MODE_AUTO,
                                label="Automatic (Weight & Impedance Thresholds)",
                            ),
                            selector.SelectOptionDict(
                                value=MATCHING_MODE_MANUAL,
                                label="Manual (Confirm via Mobile Notification)",
                            ),
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                )
            }
        )
        return self.async_show_form(step_id="global_settings", data_schema=schema)

    async def async_step_user_profile(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        """Add a new user profile linked to a Home Assistant person entity."""
        if user_input is not None:
            user_id = user_input[CONF_USER_NAME].lower().replace(" ", "_")
            profile_data = {
                CONF_USER_ID: user_id,
                CONF_USER_NAME: user_input[CONF_USER_NAME],
                CONF_PERSON_ENTITY: user_input.get(CONF_PERSON_ENTITY),
                CONF_HEIGHT: float(user_input[CONF_HEIGHT]),
                CONF_AGE: int(user_input[CONF_AGE]),
                CONF_GENDER: user_input[CONF_GENDER],
                CONF_IS_ATHLETE: bool(user_input.get(CONF_IS_ATHLETE, False)),
                CONF_TARGET_WEIGHT: float(user_input[CONF_TARGET_WEIGHT]),
                CONF_WEIGHT_TOLERANCE: float(user_input.get(CONF_WEIGHT_TOLERANCE, DEFAULT_WEIGHT_TOLERANCE)),
                CONF_TARGET_IMPEDANCE: (
                    int(user_input[CONF_TARGET_IMPEDANCE])
                    if user_input.get(CONF_TARGET_IMPEDANCE)
                    else None
                ),
                CONF_IMPEDANCE_TOLERANCE: int(
                    user_input.get(CONF_IMPEDANCE_TOLERANCE, DEFAULT_IMPEDANCE_TOLERANCE)
                ),
            }
            self.users_list.append(profile_data)
            return await self.async_step_init()

        schema = vol.Schema(
            {
                vol.Required(CONF_USER_NAME): str,
                vol.Optional(CONF_PERSON_ENTITY): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="person")
                ),
                vol.Required(CONF_HEIGHT, default=175.0): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=90.0, max=230.0, step=0.5, unit_of_measurement="cm"
                    )
                ),
                vol.Required(CONF_AGE, default=28): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=6, max=100, step=1, unit_of_measurement="years")
                ),
                vol.Required(CONF_GENDER, default="male"): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            selector.SelectOptionDict(value="male", label="Male"),
                            selector.SelectOptionDict(value="female", label="Female"),
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Required(CONF_TARGET_WEIGHT, default=75.0): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=10.0, max=200.0, step=0.1, unit_of_measurement="kg"
                    )
                ),
                vol.Required(
                    CONF_WEIGHT_TOLERANCE, default=DEFAULT_WEIGHT_TOLERANCE
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=0.5, max=15.0, step=0.5, unit_of_measurement="kg"
                    )
                ),
                vol.Optional(CONF_TARGET_IMPEDANCE): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=200, max=1200, step=1, unit_of_measurement="Ω"
                    )
                ),
                vol.Required(
                    CONF_IMPEDANCE_TOLERANCE, default=DEFAULT_IMPEDANCE_TOLERANCE
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=10, max=250, step=5, unit_of_measurement="Ω"
                    )
                ),
                vol.Optional(CONF_IS_ATHLETE, default=False): selector.BooleanSelector(),
            }
        )

        return self.async_show_form(
            step_id="user_profile",
            data_schema=schema,
        )

    async def async_step_select_user(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        """Select an existing user to edit or remove."""
        if user_input is not None:
            idx = int(user_input["selected_user"])
            if user_input.get("remove"):
                self.users_list.pop(idx)
                return await self.async_step_init()
            self._selected_user_index = idx
            return await self.async_step_edit_user()

        options = [
            selector.SelectOptionDict(
                value=str(i),
                label=f"{u[CONF_USER_NAME]} ({u[CONF_TARGET_WEIGHT]} kg, {u.get(CONF_PERSON_ENTITY, 'No HA Person')})",
            )
            for i, u in enumerate(self.users_list)
        ]

        return self.async_show_form(
            step_id="select_user",
            data_schema=vol.Schema(
                {
                    vol.Required("selected_user"): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=options,
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    ),
                    vol.Optional("remove", default=False): selector.BooleanSelector(),
                }
            ),
        )

    async def async_step_edit_user(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        """Edit selected user profile."""
        if self._selected_user_index is None or self._selected_user_index >= len(self.users_list):
            return await self.async_step_init()

        user = self.users_list[self._selected_user_index]

        if user_input is not None:
            user[CONF_USER_NAME] = user_input[CONF_USER_NAME]
            user[CONF_PERSON_ENTITY] = user_input.get(CONF_PERSON_ENTITY)
            user[CONF_HEIGHT] = float(user_input[CONF_HEIGHT])
            user[CONF_AGE] = int(user_input[CONF_AGE])
            user[CONF_GENDER] = user_input[CONF_GENDER]
            user[CONF_IS_ATHLETE] = bool(user_input.get(CONF_IS_ATHLETE, False))
            user[CONF_TARGET_WEIGHT] = float(user_input[CONF_TARGET_WEIGHT])
            user[CONF_WEIGHT_TOLERANCE] = float(user_input.get(CONF_WEIGHT_TOLERANCE, DEFAULT_WEIGHT_TOLERANCE))
            user[CONF_TARGET_IMPEDANCE] = (
                int(user_input[CONF_TARGET_IMPEDANCE])
                if user_input.get(CONF_TARGET_IMPEDANCE)
                else None
            )
            user[CONF_IMPEDANCE_TOLERANCE] = int(
                user_input.get(CONF_IMPEDANCE_TOLERANCE, DEFAULT_IMPEDANCE_TOLERANCE)
            )
            return await self.async_step_init()

        schema = vol.Schema(
            {
                vol.Required(CONF_USER_NAME, default=user.get(CONF_USER_NAME, "User")): str,
                vol.Optional(CONF_PERSON_ENTITY, default=user.get(CONF_PERSON_ENTITY)): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="person")
                ),
                vol.Required(CONF_HEIGHT, default=float(user.get(CONF_HEIGHT, 175.0))): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=90.0, max=230.0, step=0.5, unit_of_measurement="cm"
                    )
                ),
                vol.Required(CONF_AGE, default=int(user.get(CONF_AGE, 28))): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=6, max=100, step=1, unit_of_measurement="years")
                ),
                vol.Required(CONF_GENDER, default=user.get(CONF_GENDER, "male")): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            selector.SelectOptionDict(value="male", label="Male"),
                            selector.SelectOptionDict(value="female", label="Female"),
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Required(
                    CONF_TARGET_WEIGHT, default=float(user.get(CONF_TARGET_WEIGHT, 75.0))
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=10.0, max=200.0, step=0.1, unit_of_measurement="kg"
                    )
                ),
                vol.Required(
                    CONF_WEIGHT_TOLERANCE,
                    default=float(user.get(CONF_WEIGHT_TOLERANCE, DEFAULT_WEIGHT_TOLERANCE)),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=0.5, max=15.0, step=0.5, unit_of_measurement="kg"
                    )
                ),
                vol.Optional(
                    CONF_TARGET_IMPEDANCE,
                    default=user.get(CONF_TARGET_IMPEDANCE),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=200, max=1200, step=1, unit_of_measurement="Ω"
                    )
                ),
                vol.Required(
                    CONF_IMPEDANCE_TOLERANCE,
                    default=int(user.get(CONF_IMPEDANCE_TOLERANCE, DEFAULT_IMPEDANCE_TOLERANCE)),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=10, max=250, step=5, unit_of_measurement="Ω"
                    )
                ),
                vol.Optional(CONF_IS_ATHLETE, default=bool(user.get(CONF_IS_ATHLETE, False))): selector.BooleanSelector(),
            }
        )

        return self.async_show_form(
            step_id="edit_user",
            data_schema=schema,
        )
