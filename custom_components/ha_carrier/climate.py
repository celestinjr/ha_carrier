from __future__ import annotations
import logging
import asyncio

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityDescription,
    ClimateEntityFeature,
    HVACMode,
    HVACAction,
)
from homeassistant.const import (
    ATTR_TEMPERATURE,
    TEMP_CELSIUS,
    TEMP_FAHRENHEIT,
)
from homeassistant.components.climate.const import (
    ATTR_TARGET_TEMP_HIGH,
    ATTR_TARGET_TEMP_LOW,
)
from homeassistant.config_entries import ConfigEntry

from carrier_api import (
    FanModes,
    SystemModes,
    TemperatureUnits,
    ActivityNames,
    ConfigZoneActivity,
)

from .const import DOMAIN, DATA_SYSTEMS
from .carrier_data_update_coordinator import CarrierDataUpdateCoordinator
from .carrier_entity import CarrierEntity

_LOGGER = logging.getLogger(__name__)

SUPPORT_FLAGS = (
    ClimateEntityFeature.TARGET_TEMPERATURE
    | ClimateEntityFeature.TARGET_TEMPERATURE_RANGE
    | ClimateEntityFeature.FAN_MODE
    | ClimateEntityFeature.PRESET_MODE
)


async def async_setup_entry(hass, config_entry: ConfigEntry, async_add_entities):
    updaters: list[CarrierDataUpdateCoordinator] = hass.data[DOMAIN][
        config_entry.entry_id
    ][DATA_SYSTEMS]
    entities = []
    for updater in updaters:
        entities.extend(
            [
                ThermostatStatus(updater),
                ThermostatConfig(updater),
            ]
        )
    async_add_entities(entities)


class ThermostatStatus(CarrierEntity, ClimateEntity):
    _attr_supported_features = SUPPORT_FLAGS
    _attr_hvac_modes = []
    _attr_fan_modes = []
    _attr_preset_modes = []

    def __init__(self, updater):
        self.entity_description = ClimateEntityDescription(
            key=f"#{updater.carrier_system.serial}-climate-status",
        )
        super().__init__("Climate Status (read only)", updater)
        self._attr_max_temp = self._updater.carrier_system.config.limit_max
        self._attr_min_temp = self._updater.carrier_system.config.limit_min

    @property
    def current_humidity(self) -> int | None:
        return self._updater.carrier_system.status.zones[0].humidity

    @property
    def temperature_unit(self) -> str:
        if (
            self._updater.carrier_system.status.temperature_unit
            == TemperatureUnits.FAHRENHEIT
        ):
            return TEMP_FAHRENHEIT
        else:
            return TEMP_CELSIUS

    @property
    def current_temperature(self) -> float | None:
        return self._updater.carrier_system.status.zones[0].temperature

    @property
    def hvac_mode(self) -> HVACMode | str | None:
        return self._updater.carrier_system.config.mode

    @property
    def hvac_action(self) -> HVACAction | str | None:
        return self._updater.carrier_system.status.mode

    @property
    def target_temperature(self) -> float | None:
        if self.hvac_mode == SystemModes.HEAT:
            return self.target_temperature_low
        if self.hvac_mode == SystemModes.COOL:
            return self.target_temperature_high
        return None

    @property
    def target_temperature_high(self) -> float | None:
        return self._updater.carrier_system.status.zones[0].cool_set_point

    @property
    def target_temperature_low(self) -> float | None:
        return self._updater.carrier_system.status.zones[0].heat_set_point

    @property
    def preset_mode(self) -> str | None:
        return self._updater.carrier_system.status.zones[0].current_activity

    @property
    def fan_mode(self) -> str | None:
        return self._updater.carrier_system.status.zones[0].fan


class ThermostatConfig(CarrierEntity, ClimateEntity):
    _attr_supported_features = SUPPORT_FLAGS

    def __init__(self, updater):
        self.entity_description = ClimateEntityDescription(
            key=f"#{updater.carrier_system.serial}-climate-config",
        )
        super().__init__("Climate Config", updater)
        self._attr_max_temp = self._updater.carrier_system.config.limit_max
        self._attr_min_temp = self._updater.carrier_system.config.limit_min
        self._attr_fan_modes = list(map(lambda fan_mode: fan_mode.value, FanModes))
        self._attr_hvac_modes = list(
            map(lambda hvac_mode: hvac_mode.value, SystemModes)
        )
        self._attr_preset_modes = list(
            map(
                lambda activity: activity.api_id,
                self._updater.carrier_system.config.zones[0].activities,
            )
        )

    @property
    def current_humidity(self) -> int | None:
        return self._updater.carrier_system.status.zones[0].humidity

    @property
    def temperature_unit(self) -> str:
        if (
            self._updater.carrier_system.status.temperature_unit
            == TemperatureUnits.FAHRENHEIT
        ):
            return TEMP_FAHRENHEIT
        else:
            return TEMP_CELSIUS

    @property
    def current_temperature(self) -> float | None:
        return self._updater.carrier_system.status.zones[0].temperature

    @property
    def hvac_mode(self) -> HVACMode | str | None:
        return self._updater.carrier_system.config.mode

    @property
    def hvac_action(self) -> HVACAction | str | None:
        self._updater.carrier_system.status.mode_const
        return self._updater.carrier_system.status.mode

    @property
    def target_temperature(self) -> float | None:
        if self.hvac_mode == SystemModes.HEAT:
            return self.target_temperature_low
        if self.hvac_mode == SystemModes.COOL:
            return self.target_temperature_high
        return None

    def _current_activity(self) -> ConfigZoneActivity:
        return self._updater.carrier_system.config.zones[0].current_activity()

    @property
    def target_temperature_high(self) -> float | None:
        return self._current_activity().cool_set_point

    @property
    def target_temperature_low(self) -> float | None:
        return self._current_activity().heat_set_point

    @property
    def preset_mode(self) -> str | None:
        return self._current_activity().api_id

    @property
    def fan_mode(self) -> str | None:
        return self._current_activity().fan

    def refresh(self):
        asyncio.run_coroutine_threadsafe(asyncio.sleep(5), self.hass.loop).result()
        asyncio.run_coroutine_threadsafe(
            self._updater.async_request_refresh(), self.hass.loop
        ).result()

    def set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        _LOGGER.debug(f"set_hvac_mode; hvac_mode:{hvac_mode}")
        self._updater.carrier_system.config.mode = hvac_mode.value
        self._updater.carrier_system.api_connection.set_config_mode(
            system_serial=self._updater.carrier_system.serial, mode=hvac_mode.value
        )
        self.refresh()

    def set_preset_mode(self, preset_mode: str) -> None:
        _LOGGER.debug(f"set_preset_mode; preset_mode:{preset_mode}")
        activity_name = ActivityNames(preset_mode.strip().lower())
        zone = self._updater.carrier_system.config.zones[0]
        zone.hold = True
        zone.hold_activity = activity_name.value
        self._updater.carrier_system.api_connection.set_config_hold(
            system_serial=self._updater.carrier_system.serial,
            zone_id=zone.api_id,
            activity_name=activity_name,
        )
        self.refresh()

    def set_fan_mode(self, fan_mode: str) -> None:
        _LOGGER.debug(f"set_fan_mode; fan_mode:{fan_mode}")
        fan_mode = FanModes(fan_mode)
        zone = self._updater.carrier_system.config.zones[0]
        heat_set_point = zone.heat_set_point
        cool_set_point = zone.cool_set_point
        zone.find_activity(ActivityNames.MANUAL.value).fan = fan_mode.value

        self._updater.carrier_system.api_connection.set_config_manual_activity(
            system_serial=self._updater.carrier_system.serial,
            zone_id=zone.api_id,
            heat_set_point=heat_set_point,
            cool_set_point=cool_set_point,
            fan_mode=fan_mode,
        )
        self.refresh()

    def set_temperature(self, **kwargs) -> None:
        _LOGGER.debug(f"set_temperature; kwargs:{kwargs}")
        heat_set_point = kwargs.get(ATTR_TARGET_TEMP_LOW)
        cool_set_point = kwargs.get(ATTR_TARGET_TEMP_HIGH)
        temp = kwargs.get(ATTR_TEMPERATURE)

        if self._updater.carrier_system.config.mode == SystemModes.COOL.value:
            heat_set_point = self.min_temp
            cool_set_point = temp or cool_set_point
        elif self._updater.carrier_system.config.mode == SystemModes.HEAT.value:
            heat_set_point = temp or heat_set_point
            cool_set_point = self.max_temp

        if self.temperature_unit == TEMP_FAHRENHEIT:
            heat_set_point = int(heat_set_point)
            cool_set_point = int(cool_set_point)

        zone = self._updater.carrier_system.config.zones[0]
        manual_activity = zone.find_activity(ActivityNames.MANUAL.value)
        fan_mode = FanModes(manual_activity.fan)
        manual_activity.cool_set_point = cool_set_point
        manual_activity.heat_set_point = heat_set_point

        _LOGGER.debug(
            f"set_temperature; heat_set_point:{heat_set_point}, cool_set_point:{cool_set_point}, fan_mode:{fan_mode}"
        )
        self._updater.carrier_system.api_connection.set_config_manual_activity(
            system_serial=self._updater.carrier_system.serial,
            zone_id=self._updater.carrier_system.status.zones[0].api_id,
            heat_set_point=heat_set_point,
            cool_set_point=cool_set_point,
            fan_mode=fan_mode,
        )
        self.refresh()
