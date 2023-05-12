.. _DNP3-Driver:

===========
DNP3 Driver
===========

VOLTTRON's DNP3 driver enables the use of `DNP3 <https://en.wikipedia.org/wiki/DNP3>`_ (Distributed Network Protocol)
communications as a DNP3 master, reading and writing points to a remote server (DNP3 Outstation).

Requirements
============

The DNP3 driver requires the `dnp3-python <https://github.com/VOLTTRON/dnp3-python>`_ library, a DNP3 Python
implementation wrapping the `opendnp3 <https://github.com/dnp3/opendnp3>`_ library.
This library can be installed in an activated environment with:

.. code-block:: bash

    pip install dnp3-python


Driver Configuration
====================

The DNP3 driver configuration file follows :ref:`Device Configuration File <Device-Configuration-File>` convention.
Within the DNP3 driver configuration file, the "driver_config" argument is a key-value dictionary used to establish
communication with a DNP3 outstation:

    - **master_ip** - master_ip: master station (driver host) ip address
    - **outstation_ip** - outstation (remote host) ip address
    - **master_id** - master station ID
    - **outstation_id** - outstation ID
    - **port** - port number

Here is a sample DNP3 driver configuration file:

.. code-block:: json

    {
      "driver_config": {
        "master_ip": "0.0.0.0",
        "outstation_ip": "127.0.0.1",
        "master_id": 2,
        "outstation_id": 1,
        "port": 20000
      },
      "registry_config": "config://dnp3.csv",
      "driver_type": "dnp3",
      "interval": 5,
      "timezone": "UTC",
      "publish_depth_first_all": true,
      "heart_beat_point": "random_bool"
    }

A sample DNP3 driver configuration file can be found `here <https://github.com/eclipse-volttron/volttron-lib-dnp3-driver/blob/main/example-config/dnp3.config>`_.


DNP3 Registry Configuration File
================================

All valid data types and formats in DNP3 are identified by group and variation numbers. When a DNP3 outstation
transmits a message containing response data, the message identifies the group number and variation of every value within
the message. The group-variation pair numbers provide sufficient information for the receiver to parse and
properly interpret the data. DNP3’s basic documentation contains a `table <https://docs.stepfunc.io/dnp3/0.9.0/dotnet/namespacednp3.html#a467a3b6f7d543e90374b39c8088cadfbaff335165a793b52dafbd928a8864f607>`_
of valid groups and their variations.

The driver's registry configuration file specifies information related to each point on the device, in a CSV or JSON file.
More detailed information of driver registry files may be found :ref:`here <Registry-Configuration-File>`.
The driver’s registry configuration must contain the following items for each point:

    - **Volttron Point Name** - The name used by the VOLTTRON platform and agents to refer to the point.
    - **Group** - The point's DNP3 group number.
    - **Variation** - The point's DNP3 variation number.
    - **Index** - The point's index number within its DNP3 data type.
    - **Scaling** - A factor by which to multiply point values.
    - **Units** - Point value units.
    - **Writable** - TRUE or FALSE, indicating whether the point can be written by the driver (FALSE = read-only).

Point definitions in the DNP3 driver's registry should look similar as following:

.. csv-table:: DNP3
    :header: Point Name,Volttron Point Name,Group,Variation,Index,Scaling,Units,Writable,Notes

    AnalogInput_index0,AnalogInput_index0,30,6,0,1,NA,FALSE,Double Analogue input without status
    BinaryInput_index0,BinaryInput_index0,1,2,0,1,NA,FALSE,Single bit binary input with status
    AnalogOutput_index0,AnalogOutput_index0,40,4,0,1,NA,TRUE,Double-precision floating point with flags
    BinaryOutput_index0,BinaryOutput_index0,10,2,0,1,NA,TRUE,Binary Output with flags


A sample DNP3 driver registry configuration file is available
in `dnp3.csv <https://github.com/eclipse-volttron/volttron-lib-dnp3-driver/blob/main/example-config/dnp3.csv>`_.

For more information about Group Variation definition, please refer to `dnp3.Variation <https://docs.stepfunc.io/dnp3/0.9.0/dotnet/namespacednp3.html#a467a3b6f7d543e90374b39c8088cadfbaff335165a793b52dafbd928a8864f607>`_.