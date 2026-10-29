.. _DNP3-Driver:

===========
DNP3 Driver
===========

VOLTTRON's DNP3 driver reads and operates points on a DNP3 (IEEE 1815-2012) outstation as a DNP3 master. The protocol
runs in a separate DNP3 Protocol Proxy process built on the pure Python `dnp3py <https://github.com/craigpnnl/dnp3py>`_
library; the driver interface registers the outstation and its points with that proxy, polls and operates points
through it, and publishes the unsolicited responses it pushes back.

Requirements
============

The interface depends on ``protocol-proxy-dnp3``, which installs ``protocol-proxy`` and ``dnp3py``. Python 3.11 or
later is required. No C libraries are involved.

Driver Configuration
====================

The device configuration follows the :ref:`Device Configuration File <Device-Configuration-File>` convention. Its
``remote_config`` (``driver_config`` is still accepted) names the outstation and how to read and operate it:

    - **outstation_ip** (or ``host``) - outstation address.
    - **port** - outstation TCP port (20000).
    - **master_id** - DNP3 link address of this master (2).
    - **outstation_id** - DNP3 link address of the outstation (1).
    - **control_mode** - ``direct`` (DIRECT_OPERATE, the default) or ``sbo`` (SELECT then OPERATE).
    - **read_mode** - ``class`` (read ``poll_classes``, default ``[0]``), ``integrity`` or ``points``.
    - **integrity_poll_interval** - seconds between integrity polls (3600; 0 disables, one always runs on connect).
    - **unsolicited** - enable unsolicited reporting of ``unsolicited_classes`` (``[1, 2, 3]``); events are published as pushes.
    - **link_reset**, **response_timeout**, **reply_timeout**, **registration_timeout**, **proxy_group** - see the README.

.. code-block:: json

    {
      "remote_config": {
        "driver_type": "dnp3",
        "outstation_ip": "127.0.0.1",
        "port": 20000,
        "master_id": 2,
        "outstation_id": 1,
        "control_mode": "direct",
        "read_mode": "class",
        "integrity_poll_interval": 3600
      },
      "registry_config": "config://dnp3.csv",
      "interval": 5,
      "timezone": "UTC",
      "publish_depth_first_all": true
    }

DNP3 Registry Configuration File
================================

Every DNP3 value is identified by its object group, variation and index. The registry names each point's position
and how the driver should handle it:

    - **Volttron Point Name** - the name used by the platform and agents. Required.
    - **Point Name** - the point's name on the outstation (an IEC 61850 object in a MESA profile). Informational.
    - **Group**, **Variation**, **Index** - groups 1, 2, 3, 4, 10, 11, 20, 21, 22, 30, 32, 40 and 42 are read. A blank
      variation takes the usual one for the group. For a writable analog output the group 40 variation also selects
      the group 41 command variation (1 INT32, 2 INT16, 3 FLT32, 4 FLT64).
    - **Scaling** - multiplier applied by the proxy: published value = outstation value x scaling; writes divide by it.
    - **Units** - units reported in the publish metadata.
    - **Writable** - TRUE for outputs (groups 10 and 40 only).
    - **Control Mode** - per-point override of ``control_mode``: ``direct`` or ``sbo``.
    - **Control Code** - for binary outputs, ``latch`` (default) or ``pulse`` with **On Time**, **Off Time** and **Count**.
    - **Default Value** - the value ``revert`` writes when the point has no clean value yet.

.. csv-table:: DNP3
    :header: Point Name,Volttron Point Name,Group,Variation,Index,Scaling,Units,Writable,Control Mode,Control Code,Notes

    DGEN.VMinRtg,AI_2,30,6,2,0.1,Volts,FALSE,,,Nameplate Minimum Voltage Rating
    DVVR.VVArCrv,AO_217,40,4,217,1,,TRUE,sbo,,Volt-VAr curve edit selector
    DOPR.PermOp,BO_3,10,2,3,,,TRUE,,latch,Permit service
    DGEN.WHrtg,CTR_5000,20,1,5000,1,Wh,FALSE,,,Energy counter

Binary groups publish as booleans, counters as integers and analog groups as floats. A point whose quality lacks the
ONLINE flag is reported as an error for that poll. Refused controls carry the status the outstation echoed.
