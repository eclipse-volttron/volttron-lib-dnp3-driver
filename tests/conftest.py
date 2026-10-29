"""Shared fixtures for the DNP3 interface test suite. These run without a platform, a proxy, or an outstation."""
from unittest import mock

import pytest

from volttron.driver.base.testing import FakePPM, build_interface, serialized      # noqa: F401  (re-exported for tests)
from volttron.driver.interfaces.dnp3.dnp3 import Dnp3
from volttron.driver.interfaces.dnp3.config import Dnp3PointConfig


def reading(value, quality=1, online=True):
    return {'value': value, 'quality': quality, 'online': online, 'timestamp': None}


def point(name, group, index, variation=None, writable=False, **extra):
    return Dnp3PointConfig(volttron_point_name=name, object_group=group, index=index, variation=variation, writable=writable,
                           units=extra.pop('units', ''), **extra)


@pytest.fixture
def ppm():
    return FakePPM()


@pytest.fixture
def driver_agent():
    return mock.Mock(equipment_model=None)


@pytest.fixture
def make_interface(ppm, driver_agent):
    """Build a real Dnp3 interface whose proxy manager is the FakePPM."""
    def build(points=(), base_topic='campus/building/der', **remote):
        remote = {'driver_type': 'dnp3', 'outstation_ip': '10.0.0.5', **remote}
        return build_interface(Dnp3, remote, driver_agent=driver_agent, ppm=ppm, points=points, base_topic=base_topic)
    return build


STANDARD_POINTS = [
    point('AI_2', 30, 2, 6, scaling=0.1, units='Volts', point_name='DGEN.VMinRtg'),
    point('AI_3', 30, 3, 6),
    point('AO_217', 40, 217, 4, writable=True, control_mode='sbo', default_value='1'),
    point('AO_218', 40, 218, 1, writable=True, scaling=10),
    point('BI_0', 1, 0, 2),
    point('BO_3', 10, 3, 2, writable=True, control_code='pulse', on_time=200, count=2),
    point('CTR_5000', 20, 5000, 1),
]


@pytest.fixture
def interface(make_interface):
    iface = make_interface(STANDARD_POINTS)
    iface.proxy_peer = iface.ppm.peer
    return iface


TOPIC = 'campus/building/der/{}'.format
IDENTITY = {'host': '10.0.0.5', 'port': 20000, 'master_address': 2, 'outstation_address': 1}
