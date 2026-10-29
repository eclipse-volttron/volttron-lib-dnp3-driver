"""End-to-end harness for the outstation role: one real proxy process serving an outstation for an interface in the
outstation role, and a second interface in the master role reaching that outstation through the same proxy. Run by
test_end_to_end.py in its own process (gevent's monkey patching must happen before other imports). Exit status is
non-zero if any check fails."""
from gevent import monkey; monkey.patch_all()
import gevent, logging, os, sys, time
logging.basicConfig(filename=os.environ.get('DNP3_E2E_LOG', '/tmp/dnp3_e2e_server.log'), level=logging.DEBUG,
                    format='%(asctime)s %(name)s %(levelname)s %(message)s')
from volttron.driver.base.config import RemoteConfig
from volttron.driver.interfaces.dnp3.dnp3 import Dnp3
from volttron.driver.interfaces.dnp3.config import Dnp3PointConfig

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 20011


class Core: spawn = staticmethod(gevent.spawn)
class Agent:
    core = Core()
    def __init__(self): self.pushed = []
    def publish_push(self, result): self.pushed.append(dict(result))
    def flat(self):
        out = {}
        for values in self.pushed: out.update(values)
        return out


Dnp3.default_config = {}
S = 'campus/b/served/{}'.format          # the served outstation's topics
M = 'campus/b/master/{}'.format          # the master's view of the same points
checks = []
def check(name, cond, detail=''):
    checks.append((name, bool(cond))); print(('PASS ' if cond else 'FAIL ') + name + (f'  {detail}' if detail else ''))


def wait_for(predicate, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate(): return True
        gevent.sleep(0.05)
    return predicate()


rows = [dict(volttron_point_name='AI_2', object_group=30, variation=6, index=2, scaling=0.1, units='Volts', default_value='240.1'),
        dict(volttron_point_name='AI_3', object_group=30, variation=6, index=3),                                   # no starting value
        dict(volttron_point_name='BI_0', object_group=1, variation=2, index=0, default_value='TRUE', event_class=1),
        dict(volttron_point_name='BO_0', object_group=10, variation=2, index=0, default_value='FALSE'),           # remote-writable
        dict(volttron_point_name='AO_0', object_group=40, variation=1, index=0, scaling=10, default_value='100'),  # remote-writable
        dict(volttron_point_name='AO_1', object_group=40, variation=1, index=1, remote_writable=False, default_value='7'),
        dict(volttron_point_name='CTR_5', object_group=20, variation=1, index=5, default_value='42')]

served_agent, master_agent = Agent(), Agent()
served = master = None
try:
    served = Dnp3(RemoteConfig(driver_type='dnp3', driver_role='outstation', bind_host='127.0.0.1', port=PORT,
                               master_id=2, outstation_id=1), driver_agent=served_agent)
    served_rows = served.prepare_registry_config([dict(r) for r in rows], served.config)
    check('served rows default to data_source server and writable', all(r['data_source'] == 'server' and r['writable'] is True for r in served_rows))
    for row in served_rows:
        served.insert_register(served.create_register(Dnp3PointConfig(**row)), 'campus/b/served')
    t0 = time.time(); served.finalize_setup(initial_setup=True); t_setup = time.time() - t0
    check('proxy launched and outstation served', served.proxy_peer is not None and served.proxy_peer.socket_params is not None, f'{t_setup:.1f}s')
    check('served table pushed on registration', wait_for(lambda: S('CTR_5') in served_agent.flat()) and
          abs(served_agent.flat().get(S('AI_2'), 0) - 240.1) < 1e-6 and served_agent.flat().get(S('AO_0')) == 100.0
          and S('AI_3') not in served_agent.flat(), str(served_agent.flat()))

    master = Dnp3(RemoteConfig(driver_type='dnp3', outstation_ip='127.0.0.1', port=PORT, master_id=2, outstation_id=1,
                               response_timeout=5, integrity_poll_interval=0), driver_agent=master_agent)
    for row in rows:
        row = {k: v for k, v in row.items() if k not in ('default_value', 'event_class', 'remote_writable')}
        row['writable'] = row['object_group'] in (10, 40)
        master.insert_register(master.create_register(Dnp3PointConfig(**row)), 'campus/b/master')
    master.finalize_setup(initial_setup=True)
    check('master registered with the same proxy', master.proxy_peer is served.proxy_peer and master.proxy_peer is not None)

    results, errors = master.get_multiple_points(list(master.point_map))
    print('  master poll:', {k.split('/')[-1]: v for k, v in results.items()}, errors)
    check('master reads the starting values', abs(results.get(M('AI_2'), 0) - 240.1) < 1e-6 and results.get(M('BI_0')) is True
          and results.get(M('AO_0')) == 100.0 and results.get(M('CTR_5')) == 42 and results.get(M('BO_0')) is False, str(results))
    check('unset served point is offline for the master', M('AI_3') in errors and 'offline' in errors[M('AI_3')], str(errors.get(M('AI_3'))))

    served_agent.pushed.clear()
    r, e = served.set_multiple_points([(S('AI_2'), 230.5), (S('AI_3'), 12), (S('BI_0'), False)])
    check('platform writes served values', r == {S('AI_2'): 230.5, S('AI_3'): 12.0, S('BI_0'): False} and e == {}, str(e))
    check('served writes are reflected at once', served_agent.flat() == {S('AI_2'): 230.5, S('AI_3'): 12.0, S('BI_0'): False}, str(served_agent.flat()))
    results, errors = master.get_multiple_points([M('AI_2'), M('AI_3'), M('BI_0')])
    check('master sees the platform write', abs(results.get(M('AI_2'), 0) - 230.5) < 1e-6 and results.get(M('AI_3')) == 12.0
          and results.get(M('BI_0')) is False, str(results))
    results, errors = served.get_multiple_points([S('AI_2'), S('AI_3')])
    check('served interface reads what the proxy holds', results == {S('AI_2'): 230.5, S('AI_3'): 12.0}, str(results))

    served_agent.pushed.clear()
    r, e = master.set_multiple_points([(M('BO_0'), True), (M('AO_0'), 250)])
    check('master operates remote-writable points', r == {M('BO_0'): True, M('AO_0'): 250.0} and e == {}, str(e))
    check('master controls are pushed to the served interface', wait_for(lambda: served_agent.flat() == {S('BO_0'): True, S('AO_0'): 250.0}),
          str(served_agent.flat()))
    results, _ = served.get_multiple_points([S('BO_0'), S('AO_0')])
    check('served values hold the master write', results == {S('BO_0'): True, S('AO_0'): 250.0}, str(results))
    r, e = master.set_multiple_points([(M('AO_1'), 1)])
    check('control on a point that is not remote-writable is BLOCKED', r == {} and e.get(M('AO_1')) == 'status BLOCKED', str(e))

    # A proxy crash: the manager notices, both interfaces set up again, and the served values come back from the
    # platform's memory (the tree values sent with the re-registration) rather than from the starting values.
    class Tree:
        def __init__(self, agent): self.agent = agent
        def get_node(self, topic):
            flat = self.agent.flat()
            return type('Node', (), {'last_value': flat[topic], 'last_updated': True})() if topic in flat else None
    served_agent.pushed.clear()
    served_agent.pushed.append({S('AI_2'): 230.5, S('AI_3'): 12.0, S('BI_0'): False, S('BO_0'): True, S('AO_0'): 250.0})
    served.driver_agent.equipment_model = Tree(served_agent)
    old_peer = served.proxy_peer
    old_peer.process.terminate()
    relaunched = wait_for(lambda: served.proxy_peer is not None and served.proxy_peer is not old_peer
                          and served.proxy_peer.socket_params is not None and master.proxy_peer is served.proxy_peer, 20)
    # Both interfaces register again on their recovery timers; the served outstation is up once the proxy has pushed
    # its table again (the entry after the one appended above), so wait for that before using it.
    registered_again = wait_for(lambda: len(served_agent.pushed) > 1, 20)
    check('proxy relaunched after a crash and both remotes set up again', relaunched and registered_again)

    def master_reads():
        """Both interfaces register again right after the peer is up; retry until the master's read goes through."""
        try:
            results, _ = master.get_multiple_points([M('AI_2')])
            return bool(results)
        except Exception:
            return False
    wait_for(master_reads, 20)
    results, errors = master.get_multiple_points([M('AI_2'), M('AI_3'), M('BO_0'), M('AO_0'), M('AO_1')])
    check('served values survive the proxy restart from the platform memory', abs(results.get(M('AI_2'), 0) - 230.5) < 1e-6
          and results.get(M('AI_3')) == 12.0 and results.get(M('BO_0')) is True and results.get(M('AO_0')) == 250.0
          and results.get(M('AO_1')) == 7.0, f'{results} {errors}')
    served.driver_agent.equipment_model = None

    served_agent.pushed.clear()
    served.revert_all()
    results, _ = master.get_multiple_points([M('AI_2'), M('AO_0'), M('BO_0')])
    check('revert_all restores the starting values', abs(results.get(M('AI_2'), 0) - 240.1) < 1e-6 and results.get(M('AO_0')) == 100.0
          and results.get(M('BO_0')) is False, str(results))
finally:
    for iface in (served, master):
        if iface is not None and iface.ppm is not None:
            for peer in list(getattr(iface.ppm, 'peers', {}).values()):
                proc = getattr(peer, 'process', None)
                if proc: proc.terminate()
failed = [n for n, ok in checks if not ok]
print(f'\n{len(checks) - len(failed)}/{len(checks)} passed' + (f'; FAILED: {failed}' if failed else ''))
sys.exit(1 if failed else 0)
