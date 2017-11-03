import logging
import subprocess
import sys
import tempfile
import time
import psutil
import platform
import netifaces

import pytest


logger = logging.getLogger()


CCM_KILLALL=False
IP_PREFIX='127.0.5.'
NODES='3'


def _loopback_interfaces(prefix='lo'):
    ifaces = []
    for iface in netifaces.interfaces():
        if iface.startswith(prefix):
            ifaces.append(iface)
    return ifaces


def _loopbacks():
    addrs = []
    for iface in _loopback_interfaces():
        netaddrs = netifaces.ifaddresses(iface)
        for b in netaddrs[netifaces.AF_INET]:
            addrs.append((iface, b['addr']))
    return addrs


class CCMPlatform(object):
    """
    Base class for platform specifics
    """
    def __init__(self, lo_prefix='lo0'):
        self.lo_prefix = lo_prefix

    def _mkiface(self, node):
        raise NotImplementedError('Subclass should implement method')

    def _add_ip_cmd(self, iface, ip_addr):
        raise NotImplementedError('Subclass should implement method')

    def _add_ip_addr(self, iface, ip_addr):
        raise NotImplementedError('Subclass should implement method')

    def _rm_ip_addr(self, iface, ip_addr):
        raise NotImplementedError('Subclass should implement method')

    def _rm_ip_addr(self, iface, ip_addr):
        raise NotImplementedError('Subclass should implement method')


class CCMPlatformDarwin(CCMPlatform):

    def __init__(self, lo_prefix='lo0'):
        self.lo_prefix = lo_prefix

    def _mkiface(self, node):
        return self.lo_prefix

    def _add_ip_cmd(self, iface, ip_addr):
        return 'sudo ifconfig {} alias {}'.format(iface, ip_addr)

    def _add_ip_addr(self, iface, ip_addr):
        cmd = self._add_ip_cmd(iface, ip_addr)
        sys.stderr.write('Running: {}\n'.format(cmd))
        sys.stderr.flush()
        exit_code = subprocess.call(cmd, shell=True)
        if exit_code != 0:
            raise Exception('Failed to add IP', exit_code)

    def _rm_ip_addr(self, iface, ip_addr):
        cmd = 'sudo ifconfig lo0 -alias {}'.format(ip_addr)
        sys.stderr.write('Running: {}\n'.format(cmd))
        sys.stderr.flush()
        exit_code = subprocess.call(cmd, shell=True)
        if exit_code != 0:
            raise Exception('Failed to remove IP')


class CCMPlatformLinux(CCMPlatform):

    def __init__(self, lo_prefix='lo:auth_test'):
        self.lo_prefix = lo_prefix

    def _mkiface(self, node):
        return '{}{}'.format(self.lo_prefix, node)

    def _add_ip_cmd(self, iface, ip_addr):
        return 'sudo ifconfig {} {} netmask 255.0.0.0 up'.format(iface, ip_addr)

    def _add_ip_addr(self, iface, ip_addr):
        cmd = self._add_ip_cmd(iface, ip_addr)
        sys.stderr.write('Running: {}\n'.format(cmd))
        sys.stderr.flush()
        exit_code = subprocess.call(cmd, shell=True)
        if exit_code != 0:
            raise Exception('Failed to add IP')

    def _rm_ip_addr(self, iface, ip_addr):
        cmd = 'sudo ifconfig {} down'.format(iface)
        sys.stderr.write('Running: {}\n'.format(cmd))
        sys.stderr.flush()
        exit_code = subprocess.call(cmd, shell=True)
        if exit_code != 0:
            raise Exception('Failed to remove IP')


platforms = {
    'darwin': CCMPlatformDarwin(),
    'linux': CCMPlatformLinux(),
}


class CCMCluster(object):
    '''
    CCMCluster test fixture. Takes care of starting and stopping a cassandra
    cluster for running automated tests.

    Args:

        name                The name of this tests cluster, if no name is given
                            one is generated.

        nodes               The number of nodes in the cluster

        manage_cluster      When true, the cluster has already been intialized
                            so skip the initalization phase.

        manage_interfaces   Add interfaces and configure the ip addresses
                            needed to launch the test cluster, this option may
                            require a password to be entered at runtime.

        debug               Print extra debug info to stderr

        killall             Kill *all* cassandra processes when shutting down
                            the cluster. This could potentially stop multiple
                            clusters (use with care)

        ip_prefix           Use this ip prefix when launching the cluster

        platforms           Platform abatraction classes

    '''

    def __init__(
            self, name='', nodes=NODES, initialized=False,
            manage_cluster=False, debug=True, manage_interfaces=False,
            killall=CCM_KILLALL, ip_prefix=IP_PREFIX, platforms=platforms,
            pluginmanager=None):
        self.name = name
        self.nodes = nodes
        self.debug = debug
        self.initialized = initialized
        self.manage_cluster = manage_cluster
        self.manage_interfaces = manage_interfaces
        self.killall = killall
        self.ip_prefix = ip_prefix
        self.platforms = platforms
        self.pluginmanager = pluginmanager

    @property
    def num_nodes(self):
        nodes = 0
        for dc in self.nodes.split(':'):
            nodes += int(dc)
        return nodes

    @property
    def hosts_cfg(self):
        return ', '.join(self.hosts)

    @property
    def hosts(self):
        hosts = []
        for x in range(self.num_nodes):
            hosts.append(self._mkaddr(x))
        return hosts

    @property
    def _platform(self):
        for name in self.platforms:
            if sys.platform.startswith(name):
                return self.platforms[name]

    def _add_ip_cmd(self, iface, ip_addr):
        return self._platform._add_ip_cmd(iface, ip_addr)

    def _add_ip_addr(self, iface, ip_addr):
        self._platform._add_ip_addr(iface, ip_addr)

    def _rm_ip_addr(self, iface, ip_addr):
        self._platform._rm_ip_addr(iface, ip_addr)

    def _mkiface(self, node_num):
        return self._platform._mkiface(node_num)

    def _mkaddr(self, node_num):
        return '{}{}'.format(self.ip_prefix, node_num + 1)

    def _check_loopbacks(self):
        loopbacks = _loopbacks()
        missing = []
        for x in range(self.num_nodes):
            iface = self._mkiface(x)
            ip_addr = self._mkaddr(x)
            if (iface, ip_addr) not in loopbacks:
                sys.stderr.write('Ip check failed {}.\n'.format(x))
                missing.append(
                   self._add_ip_cmd(iface, ip_addr)
                )
        if missing:
            sys.stderr.write(
                "Missing network addresses.\n"
                "You can run the following commands to resolve this:\n\n"
            )
            for cmd in missing:
                sys.stderr.write("\t{}\n".format(cmd))
            sys.stderr.flush()
            pytest.exit(1)

    def _setup_loopbacks(self):
        loopbacks = _loopbacks()
        for x in range(self.num_nodes):
            iface = self._mkiface(x)
            ip_addr = self._mkaddr(x)
            if (iface, ip_addr) not in loopbacks:
                sys.stderr.write('Ip check failed {}.\n'.format(x))
                sys.stderr.write('Add ip address to loopback: {}\n'.format(x))
                sys.stderr.flush()
                self._add_ip_addr(iface, ip_addr)
        loopbacks = _loopbacks()
        missing = []
        for x in range(self.num_nodes):
            iface = self._mkiface(x)
            ip_addr = self._mkaddr(x)
            if (iface, ip_addr) not in loopbacks:
                sys.stderr.write('Ip check failed {}.\n'.format(x))
                missing.append(a)
        if missing:
            sys.stderr.write("Missing network addresses: {}\n".format(', '.join(missing)))
            raise Exception("CCM setup exception: missing address")

    def _teardown_loopbacks(self):
        for x in range(self.num_nodes):
            iface = self._mkiface(x)
            ip_addr = self._mkaddr(x)
            self._rm_ip_addr(iface, ip_addr)

    def setup(self, *args):
        """
        Accepts a single optional 'name' argument.
        """
        if self.initialized:
            return True
        if args:
            self.name = args[0]
        self._check_state()
        try:
            self._create_cluster()
        finally:
            self.initialized = True

    def teardown(self):
        if not self.initialized:
            return True
        try:
            self._remove_cluster()
            if self.manage_interfaces:
                self._teardown_loopbacks()
        finally:
            self.initialized = False
            self._check_state()

    def _check_state(self):
        if self.manage_interfaces:
            self._setup_loopbacks()
        else:
            self._check_loopbacks()
        if self.killall and len(list(self._cassandra_processes())) != 0:
            logger.warn(
                'Killing all cassandra processess, disable this by '
                'setting CCMCluster.killall to False'
            )
            self._kill_all()

    @property
    def stdout(self):
        if not self.debug:
            return subprocess.PIPE

    @property
    def stderr(self):
        if not self.debug:
            return subprocess.PIPE

    def _cassandra_processes(self, name=None):
        for p in psutil.process_iter():
            cmdline = []
            if p.name() == 'java':
                try:
                    cmdline = p.cmdline()
                except psutil.AccessDenied as e:
                    logger.debug('Unable to access commandline of java process')
            if self._cmdline_matches(cmdline):
                print("process {}".format(cmdline))
                yield p

    def _cmdline_matches(self, cmdline):
        '''
        Check to see if the commandline matches one for the test cluster
        '''
        matches = False
        if 'org.apache.cassandra.service.CassandraDaemon' in cmdline:
            for arg in cmdline:
                if arg.find(self.name) != -1:
                     matches = True
                     break
        return matches

    def _kill_all(self):
        for p in self._cassandra_processes():
            logger.warn("Kill process %d", p.pid)
            p.kill()

    def _create_cluster(self):
        if not self.name:
            raise Exception("Set name before calling create cluster")
        popenargs = [
            'ccm create {} --nodes {} -v 3.7 -i \'{}\' --start --no-switch'.format(
                self.name, self.nodes, self.ip_prefix
            )
        ]
        popenkwargs = dict(stderr=subprocess.PIPE, stdout=subprocess.PIPE, shell=True)
        stdout, stderr, e = None, None, None
        ret = 0
        p = subprocess.Popen(*popenargs, **popenkwargs)
        try:
            stdout, stderr = p.communicate()
            ret = p.wait()
        except Exception as e:
            p.kill()
            p.wait()
            logger.exception("Exception waiting for sub-process")
        if e or ret != 0:
            sys.stdout.write(stdout.decode())
            sys.stdout.flush()
            sys.stderr.write(stderr.decode())
            sys.stderr.flush()
            pytest.exit(ret)

    def _remove_cluster(self):
        ret = subprocess.call(
           'ccm remove {}'.format(self.name),
            stdout=self.stdout,
            stderr=self.stderr,
            shell=True,
        )
        if ret != 0:
            raise Exception("Problem removing test cluster")
        while len(list(self._cassandra_processes())) > 0:
            time.sleep(.5)

    def __enter__(self):
        name = tempfile.mkdtemp(suffix='-cassandra').split('/')[-1]
        if self.pluginmanager:
            capmanager = self.pluginmanager.getplugin('capturemanager')
            capmanager.suspendcapture()
        else:
            capmanager = None
        try:
            logger.info("Setting up cassandra cluster: %s", name)
            self.setup(name)
            logger.info("Cassandra cluster setup complete")
        finally:
            if capmanager:
                capmanager.resumecapture()
        return self

    def __exit__(self, *args, **kwargs):
        self.teardown()

cluster = CCMCluster()


def pytest_addoption(parser):
    parser.addoption(
        "--with-cassandra",
        action='store_true',
        default=False,
        help='Run cassandra tests',
    )


def pytest_configure(config):
    cluster.name = config.inicfg.get('cassandra-name', cluster.name)
    cluster.killall = config.inicfg.get('cassandra-killall', cluster.killall)
    cluster.ip_prefix = config.inicfg.get('cassandra-ip-prefix', cluster.ip_prefix)
    cluster.nodes = config.inicfg.get('cassandra-nodes', cluster.nodes)
    cluster.pluginmanager = config.pluginmanager


@pytest.yield_fixture()
def cluster_fixture():
    with cluster as c:
        yield c


@pytest.yield_fixture(scope='session')
def session_cluster_fixture():
    with cluster as c:
        yield c


@pytest.yield_fixture(scope='module')
def module_cluster_fixture():
    with cluster as c:
        yield c
