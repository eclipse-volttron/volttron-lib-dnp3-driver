"""Unit tests for the DNP3 interface: configuration, registers, and every message to and from the proxy."""
import logging

import pytest

from gevent import Timeout
from pydantic import ValidationError

from volttron.driver.base.config import RemoteConfig
from volttron.driver.base.interfaces import DriverInterfaceError
from volttron.driver.interfaces.dnp3.config import ControlCode, ControlMode, Dnp3PointConfig, Dnp3RemoteConfig, DriverRole, ReadMode
from volttron.driver.interfaces.dnp3.dnp3 import Dnp3

from volttron.driver.base.proxy_interface import READ_ONLY as READ_ONLY_MESSAGE

from tests.conftest import IDENTITY, STANDARD_POINTS, TOPIC, point, reading, serialized


class TestPointConfig:
    def test_csv_row_as_the_discovery_tool_writes_it(self):
        row = {'Point Name': 'DGEN.VMinRtg', 'Volttron Point Name': 'AI_2', 'Group': '30', 'Variation': '6', 'Index': '2',
               'Scaling': '0.1', 'Units': 'Volts', 'Writable': 'FALSE', 'Transform': 'scale(0.1)', 'Notes': 'Nameplate'}
        cfg = Dnp3PointConfig(**row)
        assert (cfg.point_name, cfg.volttron_point_name, cfg.object_group, cfg.variation, cfg.index) == ('DGEN.VMinRtg', 'AI_2', 30, 6, 2)
        assert cfg.scaling == 0.1 and cfg.writable is False and cfg.transform == 'scale(0.1)' and cfg.notes == 'Nameplate'
        assert cfg.control_mode is None and cfg.control_code is ControlCode.latch and cfg.resolved_variation == 6

    def test_blank_optional_columns_take_defaults(self):
        cfg = Dnp3PointConfig(**{'Volttron Point Name': 'BO_3', 'Group': '10', 'Variation': '', 'Index': '3', 'Scaling': '',
                                 'Writable': 'TRUE', 'Control Mode': '', 'Control Code': '', 'On Time': '', 'Count': ''})
        assert cfg.variation is None and cfg.resolved_variation == 2 and cfg.scaling == 1.0
        assert cfg.control_mode is None and cfg.control_code is ControlCode.latch and cfg.on_time == 0 and cfg.count == 1

    def test_control_columns(self):
        cfg = Dnp3PointConfig(**{'Volttron Point Name': 'AO_1', 'Group': 40, 'Index': 1, 'Writable': True,
                                 'Control Mode': 'SBO', 'Control Code': 'Pulse', 'On Time': 250, 'Off Time': 50, 'Count': 3})
        assert cfg.control_mode is ControlMode.sbo and cfg.control_code is ControlCode.pulse
        assert (cfg.on_time, cfg.off_time, cfg.count) == (250, 50, 3)
        assert Dnp3PointConfig(volttron_point_name='x', object_group=40, index=1, multiplier='0.5').scaling == 0.5

    def test_object_group_column_names_and_polling_group(self, caplog):
        # `object_group` / `Object Group` name the DNP3 object group; `polling_group` is the platform driver's group.
        cfg = Dnp3PointConfig(**{'Volttron Point Name': 'x', 'Object Group': '30', 'Index': '1', 'polling_group': 'fast'})
        assert (cfg.object_group, cfg.polling_group) == (30, 'fast')
        # `Group`, the column of earlier registry files, still reads as the object group with a deprecation warning.
        import volttron.driver.interfaces.dnp3.config as config_module
        config_module._group_column_warned = False
        with caplog.at_level('WARNING'):
            cfg = Dnp3PointConfig(**{'Volttron Point Name': 'x', 'Group': '30', 'Index': '1'})
        assert (cfg.object_group, cfg.polling_group) == (30, None) and 'deprecated' in caplog.text
        # `group` is refused: in a DNP3 registry it could mean either.
        with pytest.raises(ValueError, match='object_group'):
            Dnp3PointConfig(volttron_point_name='x', group=30, index=1)

    def test_rejections(self):
        with pytest.raises(ValidationError, match='not one the DNP3 driver reads'):
            Dnp3PointConfig(volttron_point_name='x', object_group=12, index=0)
        with pytest.raises(ValidationError, match='not an output and cannot be writable'):
            Dnp3PointConfig(volttron_point_name='x', object_group=30, index=0, writable=True)
        with pytest.raises(ValidationError):
            Dnp3PointConfig(volttron_point_name='x', object_group=10, index=0, writable=True, control_mode='maybe')
        with pytest.raises(ValidationError):
            Dnp3PointConfig(volttron_point_name='x', object_group=10, index=0, count=0)


class TestRemoteConfig:
    def test_old_driver_config_keys_still_work(self):
        cfg = Dnp3RemoteConfig(driver_type='dnp3', master_ip='0.0.0.0', outstation_ip='127.0.0.1', master_id=2,
                               outstation_id=1, port=20000)
        assert cfg.outstation_fields() == {'host': '127.0.0.1', 'port': 20000, 'master_address': 2, 'outstation_address': 1}
        assert cfg.master_ip == '0.0.0.0'      # accepted, unused

    def test_defaults_aliases_and_derived_values(self):
        cfg = Dnp3RemoteConfig(driver_type='dnp3', host='10.0.0.5', master_address=7, outstation_address=4,
                               control_mode='SBO', read_mode='Integrity', poll_classes='0 1', unsolicited_classes=[3, 1])
        assert cfg.outstation_ip == '10.0.0.5' and cfg.master_id == 7 and cfg.outstation_id == 4 and cfg.port == 20000
        assert cfg.control_mode is ControlMode.sbo and cfg.read_mode is ReadMode.integrity
        assert cfg.poll_classes == [0, 1] and cfg.unsolicited_classes == [1, 3]
        assert cfg.integrity_poll_interval == 3600.0 and cfg.unsolicited is False and cfg.link_reset is True
        assert cfg.resolved_reply_timeout == 30.0 and Dnp3RemoteConfig(driver_type='dnp3', host='h', response_timeout=20).resolved_reply_timeout == 60.0
        assert cfg.proxy_key() == ('dnp3',) and Dnp3RemoteConfig(driver_type='dnp3', host='h', proxy_group='site').proxy_key() == ('dnp3', 'site')
        assert cfg.connection_fields() == {'response_timeout': 5.0, 'link_reset': True, 'integrity_poll_interval': 3600.0,
                                           'unsolicited': False, 'unsolicited_classes': [1, 3]}

    def test_rejections(self):
        with pytest.raises(ValidationError, match='needs the outstation_ip'):
            Dnp3RemoteConfig(driver_type='dnp3')
        with pytest.raises(ValidationError, match='classes are 0 to 3'):
            Dnp3RemoteConfig(driver_type='dnp3', host='h', poll_classes=[4])
        with pytest.raises(ValidationError):
            Dnp3RemoteConfig(driver_type='dnp3', host='h', integrity_poll_interval=-1)


class TestRegisters:
    def test_types_and_point_fields(self, interface):
        ai, ao, bi, bo, ctr = (interface.point_map[TOPIC(n)] for n in ('AI_2', 'AO_218', 'BI_0', 'BO_3', 'CTR_5000'))
        assert (ai.python_type, ao.python_type, bi.python_type, bo.python_type, ctr.python_type) == (float, float, bool, bool, int)
        assert (ai.register_type, bi.register_type, bo.register_type) == ('byte', 'bit', 'bit')
        assert ai.read_only and not ao.read_only and ao.is_output and not ai.is_output
        assert ai.description == '' and ai.units == 'Volts'
        assert bo.point_fields(TOPIC('BO_3')) == {'topic': TOPIC('BO_3'), 'group': 10, 'variation': 2, 'index': 3,
                                                  'scaling': 1.0, 'control_code': 'pulse', 'count': 2, 'on_time': 200,
                                                  'off_time': 0}
        assert interface.get_register_names() == [TOPIC(p.volttron_point_name) for p in STANDARD_POINTS]

    def test_default_value_is_coerced_and_tracked_by_topic(self, interface):
        assert interface.point_map[TOPIC('AO_217')].default_value == 1.0
        assert interface._tracker.defaults[TOPIC('AO_217')] == 1.0

    def test_bad_default_value_is_warned_and_ignored(self, make_interface, caplog):
        with caplog.at_level(logging.WARNING):
            iface = make_interface([point('AO_1', 40, 1, writable=True, default_value='lots')])
        assert iface.point_map[TOPIC('AO_1')].default_value is None and 'bad default value' in caplog.text


class TestSetup:
    def test_constructor_wires_the_shared_manager(self, interface, ppm):
        assert ppm.started == 1 and 'RECEIVE_UNSOLICITED' in ppm.callbacks
        interface.driver_agent.core.spawn.assert_called_once_with(ppm.select_loop)

    def test_finalize_setup_launches_the_proxy_and_registers_the_outstation(self, make_interface, ppm):
        iface = make_interface(STANDARD_POINTS, integrity_poll_interval=600, unsolicited=True, unsolicited_classes=[1])
        ppm.queue(serialized({'client': '10.0.0.5:20000:1:2', 'points': 7}))
        iface.finalize_setup(initial_setup=True)
        assert ppm.launch == (('dnp3',), {'persistent': True}) and ppm.registration_waits == [30.0] and iface.proxy_peer is ppm.peer
        (method, payload, expects_reply), = ppm.sent
        assert method == 'REGISTER_REMOTE' and expects_reply
        assert payload == {'role': 'master', **IDENTITY, 'response_timeout': 5.0, 'link_reset': True, 'integrity_poll_interval': 600.0,
                           'unsolicited': True, 'unsolicited_classes': [1], 'remote_id': iface.remote_id.hex,
                           'points': [iface.point_map[t].point_fields(t) for t in iface.point_map]}
        assert payload['points'][0] == {'topic': TOPIC('AI_2'), 'group': 30, 'variation': 6, 'index': 2, 'scaling': 0.1,
                                        'control_code': 'latch', 'count': 1, 'on_time': 0, 'off_time': 0}

    def test_registration_failure_is_logged(self, interface, ppm, caplog):
        ppm.queue(serialized({}, {'outstation': 'group 99 is not a point the proxy reads'}))
        with caplog.at_level(logging.WARNING):
            interface.finalize_setup()
        assert 'Failed to register' in caplog.text and 'DNP3 Proxy' in caplog.text

    def test_proxy_group_selects_the_process(self, make_interface, ppm):
        iface = make_interface(proxy_group='plant-a')
        iface.finalize_setup()
        assert ppm.launch[0] == ('dnp3', 'plant-a')

    def test_unique_remote_id(self):
        remote = RemoteConfig(driver_type='dnp3', outstation_ip='10.0.0.5', port=20001, outstation_id=3)
        assert Dnp3.unique_remote_id('devices/x', remote) == ('dnp3', 'master', '10.0.0.5', 20001, 3)

    def test_reads_before_setup_raise(self, make_interface):
        iface = make_interface(STANDARD_POINTS)
        with pytest.raises(DriverInterfaceError):
            iface.get_multiple_points([TOPIC('AI_2')])


class TestReads:
    def test_poll_sends_the_configured_mode_and_coerces_values(self, interface, ppm):
        ppm.queue(serialized({TOPIC('AI_2'): reading(240.1), TOPIC('BI_0'): reading(True), TOPIC('CTR_5000'): reading(42),
                              TOPIC('AO_218'): reading(1200.0)}))
        results, errors = interface.get_multiple_points([TOPIC('AI_2'), TOPIC('BI_0'), TOPIC('CTR_5000'), TOPIC('AO_218')])
        assert ppm.payloads('READ_POINTS') == [{'mode': 'class', 'classes': [0],
                                                'topics': [TOPIC('AI_2'), TOPIC('BI_0'), TOPIC('CTR_5000'), TOPIC('AO_218')]}]
        assert results == {TOPIC('AI_2'): 240.1, TOPIC('BI_0'): True, TOPIC('CTR_5000'): 42, TOPIC('AO_218'): 1200.0}
        assert isinstance(results[TOPIC('CTR_5000')], int) and errors == {}

    def test_read_mode_and_classes_come_from_the_remote(self, make_interface, ppm):
        iface = make_interface(STANDARD_POINTS, read_mode='integrity', poll_classes=[0, 1])
        iface.proxy_peer = ppm.peer
        ppm.queue(serialized({TOPIC('AI_2'): reading(1)}))
        iface.get_multiple_points([TOPIC('AI_2')])
        assert ppm.payloads('READ_POINTS')[0]['mode'] == 'integrity' and ppm.payloads('READ_POINTS')[0]['classes'] == [0, 1]

    def test_get_point_reads_that_point_by_range(self, interface, ppm):
        ppm.queue(serialized({TOPIC('AI_3'): reading(5000)}))
        assert interface.get_point(TOPIC('AI_3')) == 5000.0
        assert ppm.payloads('READ_POINTS') == [{'mode': 'points', 'classes': [0], 'topics': [TOPIC('AI_3')]}]
        ppm.queue(serialized({}, {TOPIC('AI_3'): 'not reported by outstation'}))
        with pytest.raises(RuntimeError, match='not reported by outstation'):
            interface.get_point(TOPIC('AI_3'))

    def test_offline_points_and_missing_values_are_errors(self, interface, ppm):
        ppm.queue(serialized({TOPIC('AI_2'): reading(3.0, quality=0x02, online=False)}, {TOPIC('BI_0'): 'not reported by outstation'}))
        results, errors = interface.get_multiple_points([TOPIC('AI_2'), TOPIC('BI_0'), TOPIC('AI_3'), 'devices/nope'])
        assert results == {}
        assert errors == {TOPIC('AI_2'): 'point offline (quality 0x02)', TOPIC('BI_0'): 'not reported by outstation',
                          TOPIC('AI_3'): 'No value returned by the DNP3 Proxy.', 'devices/nope': 'Point not configured on device.'}

    def test_link_error_applies_to_every_point(self, interface, ppm):
        ppm.queue(serialized({}, {'link': 'LinkError: Peer closed the connection'}))
        results, errors = interface.get_multiple_points([TOPIC('AI_2'), TOPIC('BI_0')])
        assert results == {} and set(errors.values()) == {'LinkError: Peer closed the connection'}

    def test_proxy_failures(self, interface, ppm):
        ppm.queue(False)
        _, errors = interface.get_multiple_points([TOPIC('AI_2')])
        assert 'Unable to send request' in errors[TOPIC('AI_2')]
        ppm.queue(b'')
        _, errors = interface.get_multiple_points([TOPIC('AI_2')])
        assert errors[TOPIC('AI_2')] == 'Empty response from DNP3 Proxy.'
        ppm.queue(b'{"status": "error", "error": "Operation timed out", "method": "READ_POINTS"}')
        _, errors = interface.get_multiple_points([TOPIC('AI_2')])
        assert errors[TOPIC('AI_2')] == 'DNP3 Proxy READ_POINTS failed: Operation timed out'

    def test_reply_timeout_is_reported_per_point(self, interface, ppm, monkeypatch):
        def never(peer, message):
            raise Timeout()
        monkeypatch.setattr(ppm, 'send', never)
        results, errors = interface.get_multiple_points([TOPIC('AI_2'), TOPIC('BI_0')])
        assert results == {} and all(e.startswith('Timeout waiting for DNP3 Proxy') for e in errors.values())


class TestWrites:
    def test_set_point_sends_direct_operate_by_default(self, interface, ppm):
        ppm.queue(serialized({TOPIC('AO_218'): {'status': 'SUCCESS', 'value': 1200.0}}))
        assert interface.set_point(TOPIC('AO_218'), '1200') == 1200.0
        assert ppm.payloads('WRITE_POINTS') == [{'control_mode': 'direct',
                                                 'operations': [{'topic': TOPIC('AO_218'), 'value': 1200.0}]}]

    def test_per_point_control_mode_splits_the_writes(self, interface, ppm):
        ppm.queue(serialized({TOPIC('AO_218'): {'status': 'SUCCESS', 'value': 5.0}, TOPIC('BO_3'): {'status': 'SUCCESS', 'value': True}}),
                  serialized({TOPIC('AO_217'): {'status': 'SUCCESS', 'value': 2.0}}))
        results, errors = interface.set_multiple_points([(TOPIC('AO_218'), 5), (TOPIC('AO_217'), 2), (TOPIC('BO_3'), 'on')])
        assert errors == {} and results == {TOPIC('AO_218'): 5.0, TOPIC('AO_217'): 2.0, TOPIC('BO_3'): True}
        modes = [(p['control_mode'], [o['topic'] for o in p['operations']]) for p in ppm.payloads('WRITE_POINTS')]
        assert modes == [('direct', [TOPIC('AO_218'), TOPIC('BO_3')]), ('sbo', [TOPIC('AO_217')])]

    def test_outstation_default_mode_applies_to_points_without_their_own(self, make_interface, ppm):
        iface = make_interface(STANDARD_POINTS, control_mode='sbo')
        iface.proxy_peer = ppm.peer
        ppm.queue(serialized({TOPIC('BO_3'): {'status': 'SUCCESS', 'value': False}}))
        iface.set_point(TOPIC('BO_3'), False)
        assert ppm.payloads('WRITE_POINTS')[0]['control_mode'] == 'sbo'

    def test_echoed_failure_status_and_local_rejections(self, interface, ppm):
        ppm.queue(serialized({}, {TOPIC('AO_218'): 'status NOT_SUPPORTED'}))
        results, errors = interface.set_multiple_points([(TOPIC('AO_218'), 1), (TOPIC('AI_2'), 1), (TOPIC('BO_3'), 'maybe'),
                                                         ('devices/nope', 1)])
        assert results == {}
        assert errors[TOPIC('AO_218')] == 'status NOT_SUPPORTED'
        assert errors[TOPIC('AI_2')] == 'Trying to write to a point configured read only.'
        assert errors[TOPIC('BO_3')].startswith('Unable to convert') and errors['devices/nope'] == 'Point not configured on device.'
        assert ppm.payloads('WRITE_POINTS')[0]['operations'] == [{'topic': TOPIC('AO_218'), 'value': 1.0}]
        with pytest.raises(RuntimeError, match='read only'):
            interface.set_point(TOPIC('AI_2'), 1)

    def test_unacknowledged_write(self, interface, ppm):
        ppm.queue(serialized({}))
        _, errors = interface.set_multiple_points([(TOPIC('AO_218'), 1)])
        assert errors == {TOPIC('AO_218'): 'Write not acknowledged by the DNP3 Proxy.'}

    def test_revert_uses_the_default_value(self, interface, ppm):
        ppm.queue(serialized({TOPIC('AO_217'): {'status': 'SUCCESS', 'value': 1.0}}))
        interface.revert_point(TOPIC('AO_217'))
        assert ppm.payloads('WRITE_POINTS') == [{'control_mode': 'sbo',
                                                 'operations': [{'topic': TOPIC('AO_217'), 'value': 1.0}]}]


class TestUnsolicited:
    def test_receive_push_publishes_own_points_and_drops_foreign_ones(self, interface, driver_agent, caplog):
        raw = serialized({TOPIC('AI_2'): 241.5, 'campus/other/der/BI_0': True})
        with caplog.at_level(logging.WARNING):
            interface.receive_push.__wrapped__(interface, None, raw)
        driver_agent.publish_push.assert_called_once_with({TOPIC('AI_2'): 241.5})
        assert 'does not serve' in caplog.text and 'campus/other/der/BI_0' in caplog.text

    def test_receive_push_logs_errors_and_publishes_nothing(self, interface, driver_agent, caplog):
        with caplog.at_level(logging.WARNING):
            interface.receive_push.__wrapped__(interface, None, serialized({}, {'link': 'lost'}))
            interface.receive_push.__wrapped__(interface, None, b'not json')
        assert 'Error received with pushed values from the DNP3 Proxy' in caplog.text and 'Undecodable' in caplog.text
        assert not driver_agent.publish_push.called


SERVED = {'driver_type': 'dnp3', 'driver_role': 'outstation', 'bind_host': '127.0.0.1', 'port': 20010, 'outstation_id': 4,
          'master_id': 3}
SERVED_POINTS = [
    point('AI_2', 30, 2, 6, scaling=0.1, units='Volts', writable=True, data_source='server', default_value='240.1'),
    point('BI_0', 1, 0, 2, writable=True, data_source='server', event_class=2),
    point('AO_1', 40, 1, 1, writable=True, data_source='server', remote_writable=False),
    point('BO_3', 10, 3, 2, writable=True, data_source='server'),
    point('CTR_5', 20, 5, 1, writable=False, data_source='server'),
]


class TestOutstationRole:
    def test_role_values_and_fields(self):
        cfg = Dnp3RemoteConfig(**SERVED)
        assert cfg.driver_role is DriverRole.outstation and cfg.is_server and cfg.outstation_ip is None
        assert Dnp3RemoteConfig(driver_type='dnp3', driver_role='Server', port=1).driver_role is DriverRole.outstation
        assert Dnp3RemoteConfig(driver_type='dnp3', driver_role='client', host='h').driver_role is DriverRole.master
        assert Dnp3RemoteConfig(driver_type='dnp3', host='h').driver_role is DriverRole.master
        assert cfg.outstation_fields() == {'host': '127.0.0.1', 'port': 20010, 'master_address': 3, 'outstation_address': 4}
        assert cfg.connection_fields() == {'unsolicited': False, 'unsolicited_classes': [1, 2, 3]}
        with pytest.raises(ValidationError):
            Dnp3RemoteConfig(driver_type='dnp3', driver_role='relay', host='h')

    def test_served_rows_may_be_writable_inputs_and_carry_class_and_remote_writable(self):
        row = Dnp3PointConfig(**{'Volttron Point Name': 'AI_2', 'Group': '30', 'Index': '2', 'Writable': 'TRUE',
                                 'Data Source': 'server', 'Class': '2', 'Remote Writable': '', 'Starting Value': '5'})
        assert row.is_served and row.event_class == 2 and row.resolved_remote_writable is False and row.default_value == '5'
        assert Dnp3PointConfig(volttron_point_name='x', object_group=10, index=0, data_source='server').resolved_remote_writable
        with pytest.raises(ValidationError, match='cannot be writable'):
            Dnp3PointConfig(volttron_point_name='x', object_group=30, index=0, writable=True)      # not served: still refused
        with pytest.raises(ValidationError):
            Dnp3PointConfig(volttron_point_name='x', object_group=30, index=0, data_source='server', event_class=4)

    def test_prepare_registry_config_defaults_served_rows(self, make_interface):
        iface = make_interface(**SERVED)
        rows = [{'Volttron Point Name': 'AI_2', 'Group': 30, 'Index': 2},
                {'Volttron Point Name': 'AI_3', 'Group': 30, 'Index': 3, 'Writable': 'FALSE', 'Data Source': 'static'}]
        prepared = iface.prepare_registry_config(rows, RemoteConfig(**SERVED))
        assert prepared[0] == {'Volttron Point Name': 'AI_2', 'Group': 30, 'Index': 2, 'data_source': 'server', 'writable': True}
        assert prepared[1] == rows[1]
        assert iface.prepare_registry_config(rows, RemoteConfig(driver_type='dnp3', outstation_ip='h')) == rows
        assert [Dnp3PointConfig(**r).is_served for r in prepared] == [True, False]

    def test_registration_payload_describes_the_served_outstation(self, make_interface, ppm):
        iface = make_interface(SERVED_POINTS, **SERVED)
        ppm.queue(serialized({'server': 'outstation:127.0.0.1:20010:4', 'points': 5, 'role': 'outstation'}))
        iface.finalize_setup(initial_setup=True)
        (method, payload, _), = ppm.sent
        assert method == 'REGISTER_REMOTE'
        assert {k: v for k, v in payload.items() if k != 'points'} == {
            'role': 'outstation', 'host': '127.0.0.1', 'port': 20010, 'master_address': 3, 'outstation_address': 4,
            'unsolicited': False, 'unsolicited_classes': [1, 2, 3], 'remote_id': iface.remote_id.hex, 'values': {}}
        by_topic = {p['topic']: p for p in payload['points']}
        assert by_topic[TOPIC('AI_2')] == {'topic': TOPIC('AI_2'), 'group': 30, 'variation': 6, 'index': 2, 'scaling': 0.1,
                                           'control_code': 'latch', 'count': 1, 'on_time': 0, 'off_time': 0,
                                           'event_class': 1, 'remote_writable': False, 'initial_value': 240.1}
        assert (by_topic[TOPIC('BI_0')]['event_class'], by_topic[TOPIC('BI_0')]['initial_value']) == (2, None)
        assert by_topic[TOPIC('AO_1')]['remote_writable'] is False and by_topic[TOPIC('BO_3')]['remote_writable'] is True

    def test_registration_carries_the_trees_current_values(self, make_interface, ppm, driver_agent):
        from types import SimpleNamespace
        nodes = {TOPIC('AI_2'): SimpleNamespace(last_value=231.0, last_updated=object()),
                 TOPIC('BI_0'): SimpleNamespace(last_value=None, last_updated=None)}
        driver_agent.equipment_model = SimpleNamespace(get_node=lambda t: nodes.get(t))
        iface = make_interface(SERVED_POINTS, **SERVED)
        iface.finalize_setup()
        assert ppm.payloads('REGISTER_REMOTE')[0]['values'] == {TOPIC('AI_2'): 231.0}
        master = make_interface(STANDARD_POINTS)
        master.finalize_setup()
        assert 'values' not in ppm.payloads('REGISTER_REMOTE')[1]

    def test_served_writes_store_values_and_are_reflected(self, make_interface, ppm, driver_agent):
        iface = make_interface(SERVED_POINTS, **SERVED)
        iface.proxy_peer = ppm.peer
        ppm.queue(serialized({TOPIC('AI_2'): {'status': 'SUCCESS', 'value': 230.0}, TOPIC('BI_0'): {'status': 'SUCCESS', 'value': True}},
                             {TOPIC('CTR_5'): 'bad value'}))
        results, errors = iface.set_multiple_points([(TOPIC('AI_2'), '230'), (TOPIC('BI_0'), 'on'), (TOPIC('CTR_5'), 1)])
        assert results == {TOPIC('AI_2'): 230.0, TOPIC('BI_0'): True} and errors == {TOPIC('CTR_5'): READ_ONLY_MESSAGE}
        [(method, payload, _)] = ppm.sent
        assert method == 'WRITE_POINTS'
        assert payload == {'operations': [{'topic': TOPIC('AI_2'), 'value': 230.0}, {'topic': TOPIC('BI_0'), 'value': True}]}
        driver_agent.publish_push.assert_called_once_with({TOPIC('AI_2'): 230.0, TOPIC('BI_0'): True})

    def test_reads_report_served_values(self, make_interface, ppm):
        iface = make_interface(SERVED_POINTS, **SERVED)
        iface.proxy_peer = ppm.peer
        ppm.queue(serialized({TOPIC('AI_2'): reading(240.1), TOPIC('BI_0'): reading(False, quality=2, online=False)}))
        results, errors = iface.get_multiple_points([TOPIC('AI_2'), TOPIC('BI_0')])
        assert results == {TOPIC('AI_2'): 240.1} and 'offline' in errors[TOPIC('BI_0')]

    def test_unique_remote_id_includes_the_role(self):
        assert Dnp3.unique_remote_id('devices/x', RemoteConfig(**SERVED)) == ('dnp3', 'outstation', '127.0.0.1', 20010, 4)
