"""
This test suits focus on the exposed RPC calls.
It utilizes a vip agent to evoke the RPC calls.
The volltron instance and dnp3-agent is start manually.
Note: several fixtures are used
    volttron_platform_wrapper
    vip_agent
    dnp3_outstation_agent
"""
import pathlib
import random

import gevent
import pytest
import os

from volttron.client.known_identities import CONFIGURATION_STORE, PLATFORM_DRIVER
from volttron.utils import jsonapi
from dnp3_python.dnp3station.outstation_new import MyOutStationNew
from pydnp3 import opendnp3
import time

import logging

logging_logger = logging.getLogger(__name__)

DNP3_VIP_ID = "dnp3_outstation"
PLATFORM_DRIVER_ID = PLATFORM_DRIVER
PORT = 30000
PORT40000 = 40000
PORT40001 = 40001


@pytest.fixture(scope="module")
def vip_agent(volttron_instance):
    # build a vip agent
    a = volttron_instance.build_agent()
    print(a)
    return a


@pytest.fixture(scope="module")
def install_platform_driver(volttron_instance) -> dict:
    """
    Install and start a dnp3-outstation-agent, return its vip-identity
    """
    # install a dnp3-outstation-agent
    # TODO: improve the following hacky path resolver
    parent_path = pathlib.Path(__file__)
    dnp3_outstation_package_path = pathlib.Path(parent_path).parent.parent
    dnp3_agent_config_path = str(os.path.join(parent_path, "dnp3-outstation-config.json"))
    config = {
        "driver_scrape_interval": 0.05,
        "publish_breadth_first_all": "false",
        "publish_depth_first": "false",
        "publish_breadth_first": "false"
    }
    uuid = volttron_instance.install_agent(
        # agent_dir=dnp3_outstation_package_path,
        agent_dir="volttron-platform-driver",
        config_file=config,
        start=False,  # Note: for some reason, need to set to False, then start
        vip_identity=PLATFORM_DRIVER_ID)
    # start agent with retry
    # pid = retry_call(volttron_instance.start_agent, f_kwargs=dict(agent_uuid=uuid), max_retries=5, delay_s=2,
    #                  wait_before_call_s=2)

    # # check if running with retry
    # retry_call(volttron_instance.is_agent_running, f_kwargs=dict(agent_uuid=uuid), max_retries=5, delay_s=2,
    #            wait_before_call_s=2)
    gevent.sleep(5)
    # pid = volttron_instance.start_agent(uuid)
    # gevent.sleep(5)
    logging_logger.info(
        f"=========== volttron_instance.is_agent_running(uuid): {volttron_instance.is_agent_running(uuid)}")
    # TODO: get retry_call back
    return uuid


def get_device_name(port):
    """
    Construct devices name based on port number
    example:
    get_device_name(30000)
    >> "devices/campus/building/dnp3-30000")
    """
    _device_name = "devices/campus/building/dnp3"
    return _device_name + f"-{port}"


@pytest.fixture(scope="module")
def configure_platform_driver(install_platform_driver, vip_agent, volttron_instance, request):
    # Note: make sure existing port not conflict with each other.
    uuid = install_platform_driver

    capabilities = {"edit_config_store": {"identity": PLATFORM_DRIVER}}
    volttron_instance.add_capabilities(vip_agent.core.publickey, capabilities)

    # Add Fake Driver to Platform Driver
    registry_config_string = """Point Name,Volttron Point Name,Group,Variation,Index,Scaling,Units,Writable,Notes
    AnalogInput_index0,AnalogInput_index0,30,6,0,1,NA,FALSE,Double Analogue input without status
    AnalogInput_index1,AnalogInput_index1,30,6,1,1,NA,FALSE,Double Analogue input without status
    AnalogInput_index2,AnalogInput_index2,30,6,2,1,NA,FALSE,Double Analogue input without status
    AnalogInput_index3,AnalogInput_index3,30,6,3,1,NA,FALSE,Double Analogue input without status
    BinaryInput_index0,BinaryInput_index0,1,2,0,1,NA,FALSE,Single bit binary input with status
    BinaryInput_index1,BinaryInput_index1,1,2,1,1,NA,FALSE,Single bit binary input with status
    BinaryInput_index2,BinaryInput_index2,1,2,2,1,NA,FALSE,Single bit binary input with status
    BinaryInput_index3,BinaryInput_index3,1,2,3,1,NA,FALSE,Single bit binary input with status
    AnalogOutput_index0,AnalogOutput_index0,40,4,0,1,NA,TRUE,Double-precision floating point with flags
    AnalogOutput_index1,AnalogOutput_index1,40,4,1,1,NA,TRUE,Double-precision floating point with flags
    AnalogOutput_index2,AnalogOutput_index2,40,4,2,1,NA,TRUE,Double-precision floating point with flags
    AnalogOutput_index3,AnalogOutput_index3,40,4,3,1,NA,TRUE,Double-precision floating point with flags
    BinaryOutput_index0,BinaryOutput_index0,10,2,0,1,NA,TRUE,Binary Output with flags
    BinaryOutput_index1,BinaryOutput_index1,10,2,1,1,NA,TRUE,Binary Output with flags
    BinaryOutput_index2,BinaryOutput_index2,10,2,2,1,NA,TRUE,Binary Output with flags
    BinaryOutput_index3,BinaryOutput_index3,10,2,3,1,NA,TRUE,Binary Output with flags"""
    # Note: vctl config store <platform_driver_id> <config-name> <config-content-path> --csv
    config_name = "dnp3.csv"
    config_content = registry_config_string
    try:
        port = int(request.param)
    except Exception as e:
        print(e)
        port = PORT
    vip_agent.vip.rpc.call(CONFIGURATION_STORE,
                           "manage_store",
                           PLATFORM_DRIVER_ID,
                           config_name,
                           config_content,
                           config_type="csv")
    driver_config = {
        "driver_config": {"master_ip": "0.0.0.0", "outstation_ip": "127.0.0.1",
                          "master_id": 2, "outstation_id": 1,
                          "port": port},
        "registry_config": "config://dnp3.csv",
        "driver_type": "dnp3",
        "interval": 5,  # Note: interval affects scrape_all
        "timezone": "UTC",
        "heart_beat_point": "random_bool"
    }
    gevent.sleep(2)
    # Note: vctl config store <platform_driver_id> <config-name> <config-content-path> --json
    config_name = get_device_name(port)  # Note: the config_name has format devices/<path>
    config_content = driver_config
    vip_agent.vip.rpc.call(CONFIGURATION_STORE,
                           "manage_store",
                           PLATFORM_DRIVER_ID,
                           config_name,
                           jsonapi.dumps(config_content),  # Note: need to use jsonapi.dump, not json.dump
                           config_type='json')
    gevent.sleep(2)
    # TODO: added retry_call, i.e., flexible retry and sleep here.
    pid = volttron_instance.start_agent(uuid)
    return pid


@pytest.fixture(
    scope="module"
)
def outstation_app(request):
    """
    outstation using default configuration (including default database)
    Note: since outstation cannot shut down gracefully,
    outstation_app fixture need to in "module" scope to prevent interrupting pytest during outstation shut-down
    """
    # Note: allow parsing argument to fixture change port number using `request.param`
    # Note: verified that there is no port conflict during Github Action multi python version test, {{ matrix.python }}
    # Note: make sure the port is not conflicting
    try:
        port = int(request.param)
    except Exception as e:
        print(e)
        port = PORT
    outstation_appl = MyOutStationNew(port=port)  # Note: using default port 30000
    outstation_appl.start()
    # Note: Use retry to make sure connection established
    retry_max = 20
    for n in range(retry_max):
        if outstation_appl.is_connected:
            break
        gevent.sleep(1)
    yield outstation_appl
    # clean-up
    outstation_appl.shutdown()


@pytest.mark.skip(reason="Only for debugging purpose")
class TestFixtures:

    def test_volttron_instance_fixture(self, volttron_instance):
        print(volttron_instance)
        logging_logger.info(f"=========== volttron_instance_new.volttron_home: {volttron_instance.volttron_home}")
        logging_logger.info(f"=========== volttron_instance_new.skip_cleanup: {volttron_instance.skip_cleanup}")
        logging_logger.info(f"=========== volttron_instance_new.vip_address: {volttron_instance.vip_address}")

    def test_vip_agent_fixture(self, vip_agent):
        print(vip_agent)
        logging_logger.info(f"=========== vip_agent: {vip_agent}")
        logging_logger.info(f"=========== vip_agent.core.identity: {vip_agent.core.identity}")
        logging_logger.info(f"=========== vip_agent.vip.peerlist().get(): {vip_agent.vip.peerlist().get()}")

    def test_install_platform_driver_fixture(self, install_platform_driver, vip_agent, volttron_instance):
        uuid = install_platform_driver
        print(uuid)
        logging_logger.info(f"=========== dnp3_outstation_agent ids: {uuid}")
        logging_logger.info(f"=========== vip_agent.vip.peerlist().get(): {vip_agent.vip.peerlist().get()}")
        # logging_logger.info(f"=========== volttron_instance_new.is_agent_running(puid): "
        #                     f"{volttron_instance.is_agent_running(install_platform_driver['uuid'])}")

    @pytest.mark.parametrize('configure_platform_driver', [20002, 20003], indirect=['configure_platform_driver'])
    def test_configure_platform_driver_fixture(self, configure_platform_driver, install_platform_driver, vip_agent,
                                               volttron_instance):

        uuid = install_platform_driver
        pid = configure_platform_driver
        logging_logger.info(f"=========== uuid: {uuid}")
        logging_logger.info(f"=========== volttron_instance_new.is_agent_running(puid): "
                            f"{volttron_instance.is_agent_running(uuid)}")
        logging_logger.info(f"=========== vip_agent.vip.peerlist().get(): {vip_agent.vip.peerlist().get()}")
        logging_logger.info(f"=========== pid: {pid}")

        res = vip_agent.vip.rpc.call(CONFIGURATION_STORE, "manage_list_stores").get(5)
        logging_logger.info(f"=========== manage_list_stores {res}")

        res = vip_agent.vip.rpc.call(CONFIGURATION_STORE, "manage_list_configs", PLATFORM_DRIVER_ID).get(5)
        logging_logger.info(f"=========== manage_list_configs {res}")

        for port in [20002, 20003]:
            try:
                res = vip_agent.vip.rpc.call(CONFIGURATION_STORE, "manage_get",
                                             PLATFORM_DRIVER_ID, get_device_name(port)).get(5)
                logging_logger.info(f"=========== manage_get port {port}: {res}")
            except BaseException as e:  # capture gevent timeout when using rpc call
                pass

    @pytest.mark.skip(reason="Only for debugging purpose (may conflict with TestRPC)")
    @pytest.mark.parametrize('outstation_app', [20002, 20003], indirect=['outstation_app'])
    def test_outstation_app_fixture_single(self, outstation_app):
        outstation: MyOutStationNew = outstation_app
        logging.info(f"============ outstation.port {outstation.get_config()}")
        logging.info(f"============ outstation.is_connected {outstation.is_connected}")

    @pytest.mark.skip(reason="Only for debugging purpose (may conflict with TestRPC)")
    @pytest.mark.parametrize('configure_platform_driver', [PORT + 1], indirect=['configure_platform_driver'])
    def test_outstation_app_fixture_w_platform_driver(self, configure_platform_driver, outstation_app):
        outstation: MyOutStationNew = outstation_app
        logging.info(f"============ outstation.port {outstation.get_config()}")
        logging.info(f"============ outstation.is_connected {outstation.is_connected}")


# TODO: added try except "<gevent-timeout-except>" for the following rpc get calls.


@pytest.mark.skip(reason="Only for debugging purpose")
@pytest.mark.parametrize('configure_platform_driver', [PORT], indirect=['configure_platform_driver'])
class TestRPCDryRun:

    def test_scrape_all_dryrun(self, vip_agent, configure_platform_driver):
        """
        rpc call to "scrape_all" WITHOUT establishing connection to an outstation, no validation
        """
        res = vip_agent.vip.rpc.call(PLATFORM_DRIVER_ID, "scrape_all",
                                     "campus/building/dnp3").get(timeout=10)
        logging_logger.info(f"=========== scrape_all {res}")
        # expected res == {'AnalogInput_index0': None, 'AnalogInput_index1': None, 'AnalogInput_index2': None,
        #                'AnalogInput_index3': None, 'BinaryInput_index0': None, 'BinaryInput_index1': None,
        #                'BinaryInput_index2': None, 'BinaryInput_index3': None, 'AnalogOutput_index0': None,
        #                'AnalogOutput_index1': None, 'AnalogOutput_index2': None, 'AnalogOutput_index3': None,
        #                'BinaryOutput_index0': None, 'BinaryOutput_index1': None, 'BinaryOutput_index2': None,
        #                'BinaryOutput_index3': None}

    def test_get_point_dryrun(self, vip_agent, configure_platform_driver):
        """
            rpc call to "get_point" WITHOUT establishing connection to an outstation, no validation
            """
        res = vip_agent.vip.rpc.call(PLATFORM_DRIVER_ID, "get_point",
                                     "campus/building/dnp3", "AnalogInput_index0").get(timeout=10)
        logging_logger.info(f"=========== get_point {res}")  # expected None

    def test_set_point_dryrun(self, vip_agent, configure_platform_driver):
        """
            rpc call to "set_point" WITH establishing connection to an outstation, no validation
            """
        res = vip_agent.vip.rpc.call(PLATFORM_DRIVER_ID, "set_point",
                                     "campus/building/dnp3", "AnalogOutput_index0", 0.1234).get(timeout=20)
        logging_logger.info(f"=========== set_point {res}")  # expected None

    def test_set_point_dryrun_w_outstation(self, vip_agent, configure_platform_driver):
        """
            rpc call to "set_point" WITH establishing connection to an outstation, no validation
            """
        res = vip_agent.vip.rpc.call(PLATFORM_DRIVER_ID, "set_point",
                                     "campus/building/dnp3", "AnalogOutput_index0", 0.1234).get(timeout=20)
        logging_logger.info(f"=========== set_point {res}")  # expected None


def get_path_name(device_name: str):
    """
    Get Path name based on convention,
    example:
    get_path_name("devices/campus/building/dnp3")
    >> "campus/building/dnp3"
    """
    return device_name[len("devices/"):]


@pytest.mark.parametrize('outstation_app', [PORT40000], indirect=['outstation_app'])
@pytest.mark.parametrize('configure_platform_driver', [PORT40000], indirect=['configure_platform_driver'])
def test_get_point_set_point_w_outstation(vip_agent, configure_platform_driver, outstation_app):
    """
        rpc call to "get_point" "set_point" WITH establishing connection to an outstation, no validation
        """
    # Note: Port can easily conflict, combine get_point and set_point for simplicity
    port = PORT40000  # Note: this needs to match the @pytest.mark.parametrize('outstation_app'..)
    # Make sure the connection is established
    retry_max = 20
    for n in range(retry_max):
        if outstation_app.is_connected:
            break
        gevent.sleep(2)
    # check configuration
    try:
        res = vip_agent.vip.rpc.call(CONFIGURATION_STORE, "manage_get",
                                     PLATFORM_DRIVER_ID, get_device_name(port)).get(5)
        logging_logger.info(f"=========== manage_get port {port}: {res}")
    except BaseException as e:  # capture gevent timeout when using rpc call
        logging_logger.exception(e, stack_info=True)
        pass

    # get_point
    # outstation update
    val_update = random.random()
    outstation_app.apply_update(opendnp3.Analog(value=val_update,
                                                flags=opendnp3.Flags(24),
                                                time=opendnp3.DNPTime(3094)),
                                index=0)
    gevent.sleep(5)
    # Note: async method hence might be delayed, use retry for auto-testing
    retry_max = 20
    res = None
    for n in range(retry_max):
        try:
            res = vip_agent.vip.rpc.call(PLATFORM_DRIVER_ID, "get_point",
                                         get_path_name(get_device_name(port)),
                                         "AnalogInput_index0").get(timeout=20)
            logging_logger.info(f"=========== n: {n}, val_set: {val_update}, result get_point: {res}")
        except BaseException as e:
            print(e)
        if res == val_update:
            break
        gevent.sleep(4)
    assert res == val_update

    # set_point
    val_set = random.random()
    retry_max = 20
    res = None
    for n in range(retry_max):
        try:
            res = vip_agent.vip.rpc.call(PLATFORM_DRIVER_ID, "set_point",
                                         get_path_name(get_device_name(port)),
                                         "AnalogOutput_index1", val_set).get(timeout=20)
            logging_logger.info(f"=========== n: {n}, val_set: {val_set}, result set_point: {res}")
        except BaseException as e:
            print(e)
        if res == val_set:
            break
        gevent.sleep(5)
    assert res == val_set



