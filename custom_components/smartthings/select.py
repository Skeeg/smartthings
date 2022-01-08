"""Support for select through the SmartThings cloud API."""
from __future__ import annotations

from collections.abc import Sequence

from homeassistant.components.select import SelectEntity

import json
import asyncio

from pysmartthings import Capability, Attribute

from . import SmartThingsEntity
from .const import DATA_BROKERS, DOMAIN

# Create a better system for generating selects. Similar to sensor. All Select Entities have the same or similar properties

CAPABILITY_TO_SELECT = {
    "samsungce.dustFilterAlarm",
}


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Add select for a config entries."""
    broker = hass.data[DOMAIN][DATA_BROKERS][config_entry.entry_id]
    selects = []
    for device in broker.devices.values():
        for capability in broker.get_assigned(device.device_id, "select"):
            if capability == "samsungce.dustFilterAlarm":
                selects.extend([SmartThingsSelect(device)])

        if broker.any_assigned(device.device_id, "climate"):
            if (
                device.status.attributes[Attribute.mnmn].value == "Samsung Electronics"
                and device.type == "OCF"
            ):
                model = device.status.attributes[Attribute.mnmo].value
                model = model.split("|")[0]
                if Capability.execute and model in ("ARTIK051_PRAC_20K",):
                    selects.extend([SamsungACMotionSensorSaver(device)])
    async_add_entities(selects)


def get_capabilities(capabilities: Sequence[str]) -> Sequence[str] | None:
    """Return all capabilities supported if minimum required are present."""
    # Must have a value that is selectable.
    return [
        capability for capability in CAPABILITY_TO_SELECT if capability in capabilities
    ]


MOTION_SENSOR_SAVER_MODES = [
    "MotionMode_PowerSave",
    "MotionMode_Default",
    "MotionMode_Cooling",
    "MotionMode_PowerSaveOff",
    "MotionMode_DefaultOff",
    "MotionMode_CoolingOff",
]

MOTION_SENSOR_SAVER_TO_STATE = {
    "MotionMode_PowerSave": "Eco (Keeping Cool)",
    "MotionMode_Default": "Normal (Keeping Cool)",
    "MotionMode_Cooling": "Comfort (Keeping Cool)",
    "MotionMode_PowerSaveOff": "Eco (Off)",
    "MotionMode_DefaultOff": "Normal (Off)",
    "MotionMode_CoolingOff": "Comfort (Off)",
}
STATE_TO_MOTION_SENSOR_SAVER = {
    "Eco (Keeping Cool)": "MotionMode_PowerSave",
    "Normal (Keeping Cool)": "MotionMode_Default",
    "Comfort (Keeping Cool)": "MotionMode_Cooling",
    "Eco (Off)": "MotionMode_PowerSaveOff",
    "Normal (Off)": "MotionMode_DefaultOff",
    "Comfort (Off)": "MotionMode_CoolingOff",
}


class SmartThingsSelect(SmartThingsEntity, SelectEntity):
    """Define a SmartThings Select"""

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        await self._device.command(
            "main", "samsungce.dustFilterAlarm", "setAlarmThreshold", [int(option)]
        )
        # State is set optimistically in the command above, therefore update
        # the entity state ahead of receiving the confirming push updates
        self.async_write_ha_state()

    @property
    def name(self) -> str:
        """Return the name of the select entity."""
        return f"{self._device.label} Filter Alarm Threshold"

    @property
    def unique_id(self) -> str:
        """Return a unique ID."""
        return f"{self._device.device_id}_filter_alarm_threshold"

    @property
    def options(self) -> list[str]:
        """return valid options"""
        return [
            str(x)
            for x in self._device.status.attributes["supportedAlarmThresholds"].value
        ]

    @property
    def current_option(self) -> str | None:
        """return current option"""
        return str(self._device.status.attributes["alarmThreshold"].value)

    @property
    def unit_of_measurement(self) -> str | None:
        """Return unti of measurement"""
        return self._device.status.attributes["alarmThreshold"].unit


class SamsungACMotionSensorSaver(SmartThingsEntity, SelectEntity):
    """Define Samsung AC Motion Sensor Saver"""

    execute_state = str

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        print(option)
        result = await self._device.execute(
            "mode/vs/0",
            {"x.com.samsung.da.options": [STATE_TO_MOTION_SENSOR_SAVER[option]]},
        )
        if result:
            self._device.status.update_attribute_value("data", option)
            self.execute_state = option
        # State is set optimistically in the command above, therefore update
        # the entity state ahead of receiving the confirming push updates
        self.async_write_ha_state()

    @property
    def name(self) -> str:
        """Return the name of the select entity."""
        return f"{self._device.label} Motion Sensor Saver"

    @property
    def unique_id(self) -> str:
        """Return a unique ID."""
        return f"{self._device.device_id}_motion_sensor_saver"

    @property
    def options(self) -> list[str]:
        """return valid options"""
        modes = []
        for mode in MOTION_SENSOR_SAVER_MODES:
            if (state := MOTION_SENSOR_SAVER_TO_STATE.get(mode)) is not None:
                modes.append(state)
        return list(modes)

    @property
    def current_option(self) -> str | None:
        """return current option"""
        tasks = []
        tasks.append(self._device.execute("mode/vs/0"))
        asyncio.gather(*tasks)
        output = json.dumps(self._device.status.attributes[Attribute.data].value)
        mode = [
            str(mode)
            for mode in MOTION_SENSOR_SAVER_MODES
            if '"' + mode + '"' in output
        ]
        if len(mode) > 0:
            self.execute_state = MOTION_SENSOR_SAVER_TO_STATE[mode[0]]
        return self.execute_state
