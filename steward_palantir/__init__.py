""" Steward extension for monitoring servers """
import os

import logging
import yaml
from pyramid.path import DottedNameResolver
from steward.settings import asdict

from .handlers import log_handler, absorb
from .check import Check, CheckRunner


LOG = logging.getLogger(__name__)

def _db(request):
    """ Accessor for storage backend """
    return request.registry.palantir_storage(request)

def include_client(client):
    """ Add methods to the client """
    client.set_cmd('palantir.alerts', 'steward_palantir.client.do_alerts')
    client.set_cmd('palantir.checks', 'steward_palantir.client.do_checks')
    client.set_cmd('palantir.minion', 'steward_palantir.client.do_minion')
    client.set_cmd('palantir.run_check', 'steward_palantir.client.do_run_check')
    client.set_cmd('palantir.resolve', 'steward_palantir.client.do_resolve')
    try:
        response = client.cmd('palantir/check/list').json()
        client.set_autocomplete('palantir.run_check', response)
        client.set_autocomplete('palantir.checks', response)
        response = client.cmd('palantir/minion/list').json()
        client.set_autocomplete('palantir.minion', response)
    except:
        # autocomplete isn't mandatory
        pass

def includeme(config):
    """ Configure the app """
    settings = config.get_settings()
    config.add_acl_from_settings('palantir')
    config.add_request_method(_db, name='palantir_db', reify=True)

    # Add the checks
    checks_dir = settings.get('palantir.checks_dir', '/etc/steward/checks')
    checks_dir = os.path.abspath(checks_dir)
    LOG.debug("Loading palantir checks from '%s'", checks_dir)
    config.registry.palantir_checks = {}
    for filename in os.listdir(checks_dir):
        if not filename.endswith('.yaml'):
            continue
        with open(os.path.join(checks_dir, filename), 'r') as infile:
            try:
                file_data = yaml.load(infile)
                for check_name, data in file_data.iteritems():
                    if check_name in config.registry.palantir_checks:
                        raise ValueError("Duplicate Palantir check '%s' in "
                                         "file '%s'" % (check_name, filename))
                    check = Check(check_name, data)
                    runner = CheckRunner(config, check_name, data['schedule'])
                    config.add_task(runner, runner.schedule_fxn)
                    config.registry.palantir_checks[check_name] = check
            except yaml.scanner.ScannerError:
                raise ValueError("Error loading Palantir check '%s'" % filename)

    # Add the handlers
    name_resolver = DottedNameResolver(__package__)
    config.registry.palantir_handlers = {
        'log': log_handler,
        'absorb': absorb,
    }
    for name, path in asdict(settings.get('palantir.handlers')):
        config.registry.palantir_handlers[name] = name_resolver.resolve(path)

    # Set up the storage backend
    backend = settings.get('palantir.storage')
    if backend is None:
        raise ValueError("steward_palantir requires a storage system")
    elif backend == 'memory':
        backend = 'steward_palantir.storage.MemoryStorage'
    elif backend == 'sqlitedict':
        backend = 'steward_palantir.storage.SqliteDictStorage'
    config.registry.palantir_storage = name_resolver.resolve(backend)

    # Set up the route urls
    config.add_route('palantir_list_checks', '/palantir/check/list')
    config.add_route('palantir_run_check', '/palantir/check/run')
    config.add_route('palantir_get_check', '/palantir/check/get')

    config.add_route('palantir_list_alerts', '/palantir/alert/list')
    config.add_route('palantir_resolve_alert', '/palantir/alert/resolve')

    config.add_route('palantir_list_minions', '/palantir/minion/list')
    config.add_route('palantir_get_minion', '/palantir/minion/get')
    config.add_route('palantir_delete_minion', '/palantir/minion/delete')

    config.add_route('palantir_list_handlers', '/palantir/handler/list')

    config.scan()
