import logging
# -*- coding: utf-8 -*- {{{
# ===----------------------------------------------------------------------===
#
#                 Installable Component of Eclipse VOLTTRON
#
# ===----------------------------------------------------------------------===
#
# Copyright 2025 Battelle Memorial Institute
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
"""Configuration models for the DNP3 driver interface: one registry row and one remote, which is either an outstation
this driver reaches as a master (``driver_role: master``, the default) or an outstation this driver serves to a remote
master (``driver_role: outstation``).

Kept free of protocol_proxy imports so configuration tooling can validate registries without the proxy installed.
"""
from enum import Enum
from typing import Any

from pydantic import AliasChoices, Field, field_validator, model_validator

from volttron.driver.base.config import DataSource, PointConfig, RemoteConfig


class DriverRole(str, Enum):
    """Which side of DNP3 this remote is. ``client`` and ``server`` are accepted for the two."""
    master = 'master'
    outstation = 'outstation'


ROLE_ALIASES = {'client': 'master', 'server': 'outstation'}


class ControlMode(str, Enum):
    """How an output is operated: DIRECT_OPERATE in one step, or SELECT then OPERATE (sbo)."""
    direct = 'direct'
    sbo = 'sbo'


class ControlCode(str, Enum):
    """The control relay output block a binary output receives: latch on/off, or pulse on/off with timing."""
    latch = 'latch'
    pulse = 'pulse'


class ReadMode(str, Enum):
    """What a scheduled poll asks the outstation for."""
    class_poll = 'class'        # the data classes in poll_classes; Class 0 is the static data
    integrity = 'integrity'     # Class 0, 1, 2 and 3
    points = 'points'           # range reads of exactly the polled points


#: Object groups the proxy reads (static and event groups of inputs, outputs and counters).
SUPPORTED_GROUPS = frozenset({1, 2, 3, 4, 10, 11, 20, 21, 22, 30, 32, 40, 42})
#: Groups a master may operate: binary outputs (g12 commands) and analog outputs (g41 commands).
OUTPUT_GROUPS = frozenset({10, 40})
#: Variation assumed when a registry row leaves it blank.
DEFAULT_VARIATIONS = {1: 2, 2: 2, 3: 2, 4: 2, 10: 2, 11: 2, 20: 1, 21: 1, 22: 1, 30: 6, 32: 6, 40: 4, 42: 6}


def _blank_to_none(value):
    return None if isinstance(value, str) and value.strip() == '' else value


_log = logging.getLogger(__name__)
_group_column_warned = False


class Dnp3PointConfig(PointConfig):
    """One registry row. Column headers as the discovery tooling writes them are accepted alongside snake_case."""
    # The point's name on the outstation (an IEC 61850 object such as DGEN.VMinRtg in a MESA profile); informational.
    point_name: str = Field(default='', validation_alias=AliasChoices('point_name', 'Point Name'))
    # The DNP3 object group (30 analog inputs, 40 analog outputs, ...). `Group`, the column of earlier registry files,
    # is still read with a deprecation warning; `group` is refused, since elsewhere it names the polling group.
    object_group: int = Field(validation_alias=AliasChoices('object_group', 'Object Group'))
    variation: int | None = Field(default=None, validation_alias=AliasChoices('variation', 'Variation'))
    index: int = Field(validation_alias=AliasChoices('index', 'Index'))
    # Engineering value = outstation value * scaling; writes divide by it. The proxy applies it.
    scaling: float = Field(default=1.0, validation_alias=AliasChoices('scaling', 'Scaling', 'multiplier', 'Multiplier'))
    # Per-point override of the outstation's control_mode.
    control_mode: ControlMode | None = Field(default=None, validation_alias=AliasChoices('control_mode', 'Control Mode'))
    control_code: ControlCode = Field(default=ControlCode.latch, validation_alias=AliasChoices('control_code', 'Control Code'))
    count: int = Field(default=1, ge=1, validation_alias=AliasChoices('count', 'Count'))
    on_time: int = Field(default=0, ge=0, validation_alias=AliasChoices('on_time', 'On Time'))      # milliseconds
    off_time: int = Field(default=0, ge=0, validation_alias=AliasChoices('off_time', 'Off Time'))   # milliseconds
    default_value: Any = Field(default=None, validation_alias=AliasChoices('default_value', 'Default Value', 'Starting Value'))
    # Served outstations: the event class (1 to 3; 0 for none) the point's changes are buffered in.
    event_class: int | None = Field(default=None, ge=0, le=3,
                                    validation_alias=AliasChoices('event_class', 'Event Class', 'Class'))
    description: str = Field(default='', validation_alias=AliasChoices('description', 'Description'))
    # TODO: transform is not yet implemented; it should be handled by the base driver for all interfaces.
    transform: str = Field(default='', validation_alias=AliasChoices('transform', 'Transform'))

    @model_validator(mode='before')
    @classmethod
    def _blank_optionals(cls, data):
        if isinstance(data, dict):
            data = dict(data)
            if 'group' in data:
                raise ValueError(f"Point {data.get('volttron_point_name', data.get('Volttron Point Name', '?'))}: 'group' is"
                                 f" ambiguous in a DNP3 registry; use 'object_group' for the DNP3 object group or"
                                 f" 'polling_group' for the platform driver's polling group.")
            if 'Group' in data:
                global _group_column_warned
                if not _group_column_warned:
                    _log.warning("DNP3 registry column 'Group' is deprecated; rename it 'object_group' (it is the DNP3"
                                 " object group, not the platform driver's polling group).")
                    _group_column_warned = True
                data['object_group'] = data.pop('Group')
            for key in list(data):
                if key in ('variation', 'Variation', 'scaling', 'Scaling', 'multiplier', 'Multiplier', 'control_mode',
                           'Control Mode', 'control_code', 'Control Code', 'count', 'Count', 'on_time', 'On Time',
                           'off_time', 'Off Time', 'default_value', 'Default Value', 'Starting Value', 'event_class',
                           'Event Class', 'Class') and _blank_to_none(data[key]) is None:
                    del data[key]
        return data

    @field_validator('control_mode', 'control_code', mode='before')
    @classmethod
    def _lower(cls, v):
        return v.lower().strip() if isinstance(v, str) else v

    @model_validator(mode='after')
    def _check_group(self):
        if self.object_group not in SUPPORTED_GROUPS:
            raise ValueError(f'Point {self.volttron_point_name}: group {self.object_group} is not one the DNP3 driver reads'
                             f' ({sorted(SUPPORTED_GROUPS)}).')
        if self.writable and self.object_group not in OUTPUT_GROUPS and not self.is_served:
            raise ValueError(f'Point {self.volttron_point_name}: group {self.object_group} is not an output and cannot be writable.')
        return self

    @property
    def is_served(self) -> bool:
        """A served point (``data_source: server``): the platform writes it whatever its group."""
        return self.data_source is DataSource.SERVER

    @property
    def resolved_remote_writable(self) -> bool:
        """Whether a remote master may operate this served point: as configured, else when it is an output."""
        return self.remote_writable if self.remote_writable is not None else self.object_group in OUTPUT_GROUPS

    @property
    def resolved_variation(self) -> int:
        return self.variation if self.variation else DEFAULT_VARIATIONS.get(self.object_group, 1)


class Dnp3RemoteConfig(RemoteConfig):
    """One remote: the outstation to reach (role ``master``) or the outstation to serve (role ``outstation``). Keys from
    the previous driver (`master_ip`, `outstation_ip`, `master_id`, `outstation_id`) are accepted, so existing device
    configurations keep working."""
    driver_role: DriverRole = Field(default=DriverRole.master,
                                    description='master reaches an outstation; outstation serves the registry to a '
                                                'master.',
                                    json_schema_extra={'group': 'Device', 'order': 20})
    # Master role: the outstation's address. Required in that role.
    outstation_ip: str | None = Field(default=None,
                                      validation_alias=AliasChoices('outstation_ip', 'host', 'device_address'),
                                      description="Master: the outstation's address.",
                                      json_schema_extra={'group': 'Connection',
                                                         'show_when': {'driver_role': ['client', 'master']},
                                                         'order': 10})
    # Outstation role: the interface to listen on.
    bind_host: str = Field(default='0.0.0.0', validation_alias=AliasChoices('bind_host', 'listen_host'),
                           description='Outstation: the interface to listen on.',
                           json_schema_extra={'group': 'Connection',
                                              'show_when': {'driver_role': ['server', 'slave', 'outstation']},
                                              'order': 20})
    port: int = Field(default=20000, json_schema_extra={'group': 'Connection', 'order': 30})
    master_id: int = Field(default=2, validation_alias=AliasChoices('master_id', 'master_address'),
                           description='DNP3 link address of the master.',
                           json_schema_extra={'group': 'Connection', 'order': 40})
    outstation_id: int = Field(default=1, validation_alias=AliasChoices('outstation_id', 'outstation_address'),
                               description='DNP3 link address of the outstation.',
                               json_schema_extra={'group': 'Connection', 'order': 50})
    # Accepted from old configurations and not used: dnp3py does not bind a local address.
    master_ip: str | None = Field(default=None, description='Accepted from old configurations and not used.',
                                  json_schema_extra={'group': 'Connection', 'advanced': True, 'order': 60})
    control_mode: ControlMode = Field(default=ControlMode.direct,
                                      description='direct operate or select-before-operate.',
                                      json_schema_extra={'group': 'Protocol and timing', 'order': 70})
    read_mode: ReadMode = Field(default=ReadMode.class_poll,
                                description='class polls or reads of the configured points.',
                                json_schema_extra={'group': 'Protocol and timing', 'order': 80})
    poll_classes: list[int] = Field(default=[0], description='Event classes each poll asks for.',
                                    json_schema_extra={'group': 'Protocol and timing', 'order': 90})
    # Seconds between integrity polls; 0 disables them, one always runs when the connection opens.
    integrity_poll_interval: float = Field(default=3600.0, ge=0,
                                           description='Seconds between integrity polls; 0 disables them, one always '
                                                       'runs when the connection opens.',
                                           json_schema_extra={'group': 'Protocol and timing', 'unit': 's',
                                                              'order': 100})
    unsolicited: bool = Field(default=False, description='Enable unsolicited responses from the outstation.',
                              json_schema_extra={'group': 'Protocol and timing', 'order': 110})
    unsolicited_classes: list[int] = Field(default=[1, 2, 3],
                                           json_schema_extra={'group': 'Protocol and timing', 'advanced': True,
                                                              'order': 120})
    link_reset: bool = Field(default=True,
                             json_schema_extra={'group': 'Protocol and timing', 'advanced': True, 'order': 130})
    # How long the proxy waits for the outstation to answer one request.
    response_timeout: float = Field(default=5.0, gt=0,
                                    description='How long the proxy waits for the outstation to answer one request.',
                                    json_schema_extra={'group': 'Protocol and timing', 'unit': 's', 'order': 140})
    # How long this interface waits for the proxy's reply; defaults to three response timeouts, at least 30 s.
    reply_timeout: float | None = Field(default=None, gt=0,
                                        description="How long this interface waits for the proxy's reply; defaults to "
                                                    'three response timeouts, at least 30 s.',
                                        json_schema_extra={'group': 'Proxy', 'advanced': True, 'unit': 's',
                                                           'order': 150})
    registration_timeout: float = Field(default=30.0, gt=0,
                                        json_schema_extra={'group': 'Proxy', 'advanced': True, 'unit': 's',
                                                           'order': 160})
    persistent_connection: bool = Field(default=True, description='Keep one IPC connection to the proxy open for every'
                                        ' request and push instead of one connection per message.',
                                        json_schema_extra={'group': 'Proxy', 'advanced': True, 'order': 170})
    # All outstations share one proxy process unless a group is named here.
    proxy_group: str | None = Field(default=None,
                                    description='All outstations share one proxy process unless a group is named here.',
                                    json_schema_extra={'group': 'Proxy', 'advanced': True, 'order': 180})

    @field_validator('control_mode', 'read_mode', mode='before')
    @classmethod
    def _lower(cls, v):
        return v.lower().strip() if isinstance(v, str) else v

    @field_validator('driver_role', mode='before')
    @classmethod
    def _role(cls, v):
        if isinstance(v, str):
            v = v.lower().strip() or 'master'
            return ROLE_ALIASES.get(v, v)
        return DriverRole.master if v is None else v

    @model_validator(mode='after')
    def _check_role_fields(self):
        if self.driver_role is DriverRole.master and not self.outstation_ip:
            raise ValueError('A DNP3 master needs the outstation_ip (or host) of the outstation to reach.')
        return self

    @property
    def is_server(self) -> bool:
        return self.driver_role is DriverRole.outstation

    @field_validator('poll_classes', 'unsolicited_classes', mode='before')
    @classmethod
    def _classes(cls, v):
        if isinstance(v, (int, str)):
            v = [int(c) for c in str(v).replace(',', ' ').split()]
        classes = sorted({int(c) for c in v})
        if any(c not in (0, 1, 2, 3) for c in classes):
            raise ValueError(f'DNP3 data classes are 0 to 3, got {classes}')
        return classes

    @property
    def resolved_reply_timeout(self) -> float:
        return self.reply_timeout if self.reply_timeout is not None else max(30.0, 3 * self.response_timeout)

    def proxy_key(self) -> tuple:
        """Selects the proxy process. Constant by default so all outstations share one."""
        return ('dnp3',) if self.proxy_group is None else ('dnp3', self.proxy_group)

    def outstation_fields(self) -> dict:
        """What identifies the remote to the proxy: the outstation to reach, or the listener and addresses to serve."""
        return {'host': self.bind_host if self.is_server else self.outstation_ip, 'port': self.port,
                'master_address': self.master_id, 'outstation_address': self.outstation_id}

    def connection_fields(self) -> dict:
        """Connection and polling settings sent with the registration (a served outstation uses the unsolicited ones)."""
        if self.is_server:
            return {'unsolicited': self.unsolicited, 'unsolicited_classes': list(self.unsolicited_classes)}
        return {'response_timeout': self.response_timeout, 'link_reset': self.link_reset,
                'integrity_poll_interval': self.integrity_poll_interval, 'unsolicited': self.unsolicited,
                'unsolicited_classes': list(self.unsolicited_classes)}
