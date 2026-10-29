"""End-to-end harness: real interface -> real GeventProtocolProxyManager -> real DNP3 proxy subprocess -> dnp3py
outstation. Run by test_end_to_end.py in its own process (gevent's monkey patching must happen before other imports).
Exit status is non-zero if any check fails."""
from gevent import monkey; monkey.patch_all()
import gevent, logging, os, socket, subprocess, sys, time
from pathlib import Path
logging.basicConfig(filename=os.environ.get('DNP3_E2E_LOG', '/tmp/dnp3_e2e.log'), level=logging.DEBUG, format='%(asctime)s %(name)s %(levelname)s %(message)s')
from volttron.driver.base.config import RemoteConfig
from volttron.driver.interfaces.dnp3.dnp3 import Dnp3
from volttron.driver.interfaces.dnp3.config import Dnp3PointConfig

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 20010
sim = subprocess.Popen([sys.executable, str(Path(__file__).with_name('dnp3_outstation_sim.py')), str(PORT)])
for _ in range(50):
    try: socket.create_connection(('127.0.0.1', PORT), timeout=0.2).close(); break
    except OSError: time.sleep(0.1)
else: sys.exit('outstation did not start')

class Core: spawn = staticmethod(gevent.spawn)
class Agent:
    core = Core()
    def __init__(self): self.pushed = []
    def publish_push(self, result): self.pushed.append(result)
Dnp3.default_config = {}
T = 'campus/b/der/{}'.format
checks = []
def check(name, cond, detail=''):
    checks.append((name, bool(cond))); print(('PASS ' if cond else 'FAIL ') + name + (f'  {detail}' if detail else ''))

iface = None
try:
    iface = Dnp3(RemoteConfig(driver_type='dnp3', outstation_ip='127.0.0.1', port=PORT, master_id=2, outstation_id=1,
                              response_timeout=5, integrity_poll_interval=0), driver_agent=Agent())
    rows = [dict(volttron_point_name='AI_2', object_group=30, variation=6, index=2, scaling=0.1, units='Volts'),
            dict(volttron_point_name='AI_3', object_group=30, variation=6, index=3, units='W'),
            dict(volttron_point_name='AI_9', object_group=30, variation=6, index=9),                        # not on the outstation
            dict(volttron_point_name='BI_0', object_group=1, variation=2, index=0),
            dict(volttron_point_name='BI_1', object_group=1, variation=2, index=1),
            dict(volttron_point_name='BO_0', object_group=10, variation=2, index=0, writable=True),
            dict(volttron_point_name='BO_1', object_group=10, variation=2, index=1, writable=True, control_mode='sbo'),
            dict(volttron_point_name='AO_0', object_group=40, variation=1, index=0, writable=True, scaling=10, default_value='100'),
            dict(volttron_point_name='AO_1', object_group=40, variation=1, index=1, writable=True, control_mode='sbo'),
            dict(volttron_point_name='CTR_5000', object_group=20, variation=1, index=5000)]
    for row in rows:
        iface.insert_register(iface.create_register(Dnp3PointConfig(**row)), 'campus/b/der')
    t0 = time.time(); iface.finalize_setup(initial_setup=True); t_setup = time.time() - t0
    check('proxy launched and outstation registered', iface.proxy_peer is not None and iface.proxy_peer.socket_params is not None, f'{t_setup:.1f}s')

    t0 = time.time(); results, errors = iface.get_multiple_points(list(iface.point_map)); t_poll = time.time() - t0
    print('  results:', {k.split('/')[-1]: v for k, v in results.items()}); print('  errors:', {k.split('/')[-1]: v for k, v in errors.items()})
    check('poll: analog inputs scaled', abs(results.get(T('AI_2'), 0) - 240.1) < 1e-6 and results.get(T('AI_3')) == 50000.0, f'{t_poll:.2f}s')
    check('poll: binary inputs, outputs and counter', results.get(T('BI_0')) is True and results.get(T('BI_1')) is False
          and results.get(T('BO_0')) is False and results.get(T('CTR_5000')) == 42)
    check('poll: analog output status scaled', results.get(T('AO_0')) == 100.0 and results.get(T('AO_1')) == 20.0)
    check('poll: unknown index isolated to its point', T('AI_9') in errors and len(errors) == 1, str(errors.get(T('AI_9'))))

    check('get_point (range read)', iface.get_point(T('AI_3')) == 50000.0)
    check('set_point direct, scaled, returns requested value', iface.set_point(T('AO_0'), '250') == 250.0)
    check('set_point visible on outstation', iface.get_point(T('AO_0')) == 250.0)
    r, e = iface.set_multiple_points([(T('AO_1'), 33), (T('BO_0'), True), (T('BO_1'), 'on')])
    check('set_multiple_points mixes direct and sbo', r == {T('AO_1'): 33.0, T('BO_0'): True, T('BO_1'): True} and e == {}, str(e))
    results, _ = iface.get_multiple_points([T('AO_1'), T('BO_0'), T('BO_1')])
    check('writes visible on outstation', results == {T('AO_1'): 33.0, T('BO_0'): True, T('BO_1'): True}, str(results))
    r, e = iface.set_multiple_points([(T('AO_1'), 5000)])
    check('refused control reports the echoed status', r == {} and e.get(T('AO_1')) == 'status OUT_OF_RANGE', str(e))
    try:
        iface.set_point(T('AI_2'), 1); check('read-only write rejected', False)
    except Exception as ex:
        check('read-only write rejected', 'read only' in str(ex))
    iface.revert_all()
    results, _ = iface.get_multiple_points([T('AO_0'), T('AO_1'), T('BO_0')])
    check('revert_all: default and clean values restored', results.get(T('AO_0')) == 100.0 and results.get(T('AO_1')) == 20.0
          and results.get(T('BO_0')) is False, str(results))
finally:
    for peer in list(getattr(iface.ppm, 'peers', {}).values()) if iface is not None else []:
        proc = getattr(peer, 'process', None)
        if proc: proc.terminate()
    sim.terminate()
failed = [n for n, ok in checks if not ok]
print(f'\n{len(checks) - len(failed)}/{len(checks)} passed' + (f'; FAILED: {failed}' if failed else ''))
sys.exit(1 if failed else 0)
