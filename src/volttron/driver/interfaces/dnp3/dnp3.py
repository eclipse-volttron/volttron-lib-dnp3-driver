# -*- coding: utf-8 -*- {{{
# ===----------------------------------------------------------------------===
#
#                 Installable Component of Eclipse VOLTTRON
#
# ===----------------------------------------------------------------------===
#
# Copyright 2022 Battelle Memorial Institute
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may not
# use this file except in compliance with the License. You may obtain a copy
# of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.
#
# ===----------------------------------------------------------------------===
# }}}

import datetime
import logging
from volttron.driver.base.interfaces import (BaseInterface, BaseRegister, BasicRevert)
from dnp3_python.dnp3station.master_new import MyMasterNew

from typing import List, Type, Dict, Union, Optional, TypeVar
from time import sleep

_log = logging.getLogger(__name__)
type_mapping = {
    "string": str,
    "int": int,
    "integer": int,
    "float": float,
    "bool": bool,
    "boolean": bool
}

# Type alias
RegisterValue = Union[int, str, float, bool]
Register = TypeVar("Register", bound=BaseRegister)


class Dnp3Register(BaseRegister):
    # TODO: developed more robust logic when not connecting with an outstation.

    def __init__(self, read_only, pointName, units, reg_type, default_value=None, description='',
                 reg_definition=None, master_application=None):
        # Note: the most important arguments are regDef and master_application
        # read_only determine whether the set_point logic can be implemented
        # (associated with "Writable" field in config-csv)
        # (Keep other arguments by following fake driver example convention)
        self.reg_def = reg_definition
        self.master_application = master_application
        self.reg_type = reg_type
        self.pointName = pointName

        self._value = None  # use _value as cache
        self.group = int(reg_definition.get("Group"))
        self.variation = int(reg_definition.get("Variation"))
        self.index = int(reg_definition.get("Index"))

        super().__init__("byte", read_only, pointName, units, description='')

    @property
    def value(self) -> RegisterValue:
        try:
            value = self._get_outstation_pt(master_application=self.master_application,
                                            group=self.group,
                                            variation=self.variation,
                                            index=self.index)
            if value is None:
                _log.warning(f"Register value for pointName {self.pointName} is None.")
                # raise ValueError(f"Register value for pointName {self.pointName} is None. Hence not publish.")
                # TODO: figure out an elegant way to not publish None values.
            self._value = value
            return self._value
        except Exception as e:
            _log.exception(e, stack_info=True)
            _log.warning("udd_dnp3 driver (master) couldn't get value from the outstation.")

    @staticmethod
    def _get_outstation_pt(master_application, group, variation, index) -> RegisterValue:
        """
        Core logic to retrieve register value by polling a dnp3 outstation
        Note: using def get_db_by_group_variation_index
        Returns
        -------
        """
        return_point_value = master_application.get_val_by_group_variation_index(group=group,
                                                                                 variation=variation,
                                                                                 index=index)
        return return_point_value

    @value.setter
    def value(self, _val):
        try:
            self._set_outstation_pt(master_application=self.master_application,
                                    group=self.group,
                                    variation=self.variation,
                                    index=self.index,
                                    set_value=_val)
            self._value = _val
        except Exception as e:
            _log.exception(e, stack_info=True)
            _log.warning("udd_dnp3 driver (master) couldn't set value for the outstation.")

    @staticmethod
    def _set_outstation_pt(master_application, group, variation, index, set_value) -> None:
        """
        Core logic to send point operate command to outstation
        Note: using def send_direct_point_command
        Returns None
        -------
        """
        master_application.send_direct_point_command(group=group, variation=variation, index=index,
                                                     val_to_set=set_value)


class Dnp3Driver(BasicRevert, BaseInterface):
    # Note: the name of the driver_instance doesn't matter,
    # as long as it inherit from BasicRevert, BaseInterface

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.master_application = None  # place-holder: configuration happen in def config(self, ...)

    def configure(self, config_dict, registry_config_str):
        # Note: this method is wired to def get_interface in volttron.driver.base.driver,
        # used `interface.configure(driver_config, registry_config)`
        # Consider this as post_init since config_dict, registry_config_str are not accessible in __init__
        if self.master_application is None:
            driver_config = config_dict
            self.master_application = MyMasterNew(
                masterstation_ip_str=driver_config.get("master_ip"),
                outstation_ip_str=driver_config.get("outstation_ip"),
                port=driver_config.get("port"),
                masterstation_id_int=driver_config.get("master_id"),
                outstation_id_int=driver_config.get("outstation_id"),
            )
            self.master_application.start()  # TODO: complete the self.master_application.stop() logic
        self.parse_config(registry_config_str)

    def get_point(self, point_name):
        register: Dnp3Register = self.get_register_by_name(point_name)

        return register.value

    def _set_point(self, point_name, value: RegisterValue):
        register: Dnp3Register = self.get_register_by_name(point_name)
        if register.read_only:
            raise ValueError("Trying to write to a point configured read only: " + point_name)
        # register.value = register.reg_type(value)  # old logic to cast value to reg_type value (not robust)
        register.value = value
        return register._value
        # # Note: simple retry logic
        # # TODO: make retry attempt configurable
        # retry_max = 3
        # for n in range(retry_max):
        #     if register._value == value:  # use _value as cache
        #         return register.value
        #     register.value = value  # otherwise, retry
        #     sleep(1)
        #     # _log.info(f"Starting set_point {n}th RETRY for {point_name}")
        # _log.warning(f"Failed to set_point for {point_name} after {retry_max} retry.")
        # return None

    def _scrape_all(self):
        result = {}
        read_registers = self.get_registers_by_type("byte", True)
        write_registers = self.get_registers_by_type("byte", False)
        for register in read_registers + write_registers:
            result[register.point_name] = register.value

        return result

    def parse_config(self, configDict):
        if configDict is None:
            return

        for regDef in configDict:
            # Skip lines that have no address yet.
            if not regDef['Point Name']:
                continue

            read_only = regDef['Writable'].lower() != 'true'
            point_name = regDef['Volttron Point Name']
            description = regDef.get('Notes', '')
            units = regDef['Units']
            default_value = regDef.get("Starting Value", 'sin').strip()
            if not default_value:
                default_value = None
            # Note: logic to pass data type from csv config to Python type (by default using string/str)
            type_name = regDef.get("Type", 'string')
            reg_type = type_mapping.get(type_name, str)

            register_type = Dnp3Register
            register = register_type(read_only,
                                     point_name,
                                     units,
                                     reg_type,
                                     default_value=default_value,
                                     description=description,
                                     reg_definition=regDef,
                                     master_application=self.master_application)

            if default_value is not None:
                self.set_default(point_name, register.value)

            self.insert_register(register)
