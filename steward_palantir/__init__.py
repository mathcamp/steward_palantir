""" Steward extension for monitoring servers """
import os

import logging
import yaml
from pyramid.path import DottedNameResolver
from steward.settings import asdict

from .handlers import log_handler, absorb, alert, mail, fork, alias_factory
from .check import Check, CheckRunner


LOG = logging.getLogger(__name__)

def _db(request):
    """ Accessor for storage backend """
    return request.registry.palantir_storage(request)

def include_client(client):
    """ Add methods to the client """
    client.set_cmd('palantir.alerts', 'steward_palantir.client.do_alerts')
    client.set_cmd('palantir.checks', 'steward_palantir.client.do_checks')
    client.set_cmd('palantir.status', 'steward_palantir.client.do_status')
    client.set_cmd('palantir.minions', 'steward_palantir.client.do_minions')
    client.set_cmd('palantir.run_check', 'steward_palantir.client.do_run_check')
    client.set_cmd('palantir.resolve', 'steward_palantir.client.do_resolve')
    client.set_cmd('palantir.enable_minion',
                   'steward_palantir.client.do_minion_enable')
    client.set_cmd('palantir.disable_minion',
                   'steward_palantir.client.do_minion_disable')
    client.set_cmd('palantir.enable_check',
                   'steward_palantir.client.do_check_enable')
    client.set_cmd('palantir.disable_check',
                   'steward_palantir.client.do_check_disable')
    client.set_cmd('palantir.enable_minion_check',
                   'steward_palantir.client.do_minion_check_enable')
    client.set_cmd('palantir.disable_minion_check',
                   'steward_palantir.client.do_minion_check_disable')
    try:
        checks = client.cmd('palantir/check/list').json().keys()
        client.set_autocomplete('palantir.run_check', checks)
        client.set_autocomplete('palantir.checks', checks)
        client.set_autocomplete('palantir.enable_check', checks)
        client.set_autocomplete('palantir.disable_check', checks)
        minions = client.cmd('palantir/minion/list').json().keys()
        client.set_autocomplete('palantir.enable_minion', minions)
        client.set_autocomplete('palantir.disable_minion', minions)
        client.set_autocomplete('palantir.enable_minion_check', minions +
                                checks)
        client.set_autocomplete('palantir.disable_minion_check', minions +
                                checks)
        client.set_autocomplete('palantir.status', minions + checks)
        client.set_autocomplete('palantir.resolve', minions + checks)
    except:
        # autocomplete isn't mandatory
        LOG.warn("Failed to load palantir autocomplete")

def includeme(config):
    """ Configure the app """
    settings = config.get_settings()
    config.add_acl_from_settings('palantir')
    config.add_request_method(_db, name='palantir_db', reify=True)

    # Load the checks
    checks_dir = settings.get('palantir.checks_dir', '/etc/steward/checks')
    checks_dir = os.path.abspath(checks_dir)
    LOG.debug("Loading palantir checks from '%s'", checks_dir)
    config.registry.palantir_checks = {}
    check_to_file = {}
    for filename in os.listdir(checks_dir):
        if not filename.endswith('.yaml'):
            continue
        absfile = os.path.join(checks_dir, filename)
        with open(absfile, 'r') as infile:
            try:
                file_data = yaml.load(infile)
                for check_name, data in file_data.iteritems():
                    if check_name in config.registry.palantir_checks:
                        raise ValueError("Duplicate Palantir check '%s' in "
                                         "file '%s'. First occurrence "
                                         "in file '%s'" %
                                         (check_name, absfile,
                                          check_to_file[check_name]))
                    check = Check(check_name, data)
                    runner = CheckRunner(config, check_name, data['schedule'])
                    config.add_task(runner, runner.schedule_fxn)
                    config.registry.palantir_checks[check_name] = check
                    check_to_file[check_name] = absfile
            except yaml.scanner.ScannerError:
                raise ValueError("Error loading Palantir check '%s'" % absfile)

    # Add the handlers
    name_resolver = DottedNameResolver(__package__)
    config.registry.palantir_handlers = {
        'log': log_handler,
        'absorb': absorb,
        'alert': alert,
        'mail': mail,
        'fork': fork,
    }
    for name, path in asdict(settings.get('palantir.handlers')):
        config.registry.palantir_handlers[name] = name_resolver.resolve(path)

    # Load any handler aliases
    alias_dir = settings.get('palantir.alias_dir')
    config.registry.palantir_aliases = {}
    alias_to_file = {}
    if alias_dir is not None and os.path.exists(alias_dir):
        alias_dir = os.path.abspath(alias_dir)
        LOG.debug("Loading palantir aliases from '%s'", alias_dir)
        for filename in os.listdir(alias_dir):
            if not filename.endswith('.yaml'):
                continue
            absfile = os.path.join(alias_dir, filename)
            with open(absfile, 'r') as infile:
                try:
                    file_data = yaml.load(infile)
                    for alias_name, data in file_data.iteritems():
                        if alias_name in config.registry.palantir_checks:
                            raise ValueError("Cannot create Palantir alias "
                                             "'%s'. Check '%s' in "
                                            "file '%s' already exists" %
                                             (alias_name, alias_name,
                                              check_to_file[alias_name]))
                        if alias_name in config.registry.palantir_aliases:
                            raise ValueError("Duplicate Palantir alias '%s' in "
                                            "file '%s'. First occurrence "
                                            "in file '%s'" %
                                            (alias_name, absfile,
                                            alias_to_file[alias_name]))
                        config.registry.palantir_aliases[alias_name] = data
                        config.registry.palantir_handlers[alias_name] = alias_factory(alias_name)
                        alias_to_file[alias_name] = absfile
                except yaml.scanner.ScannerError:
                    raise ValueError("Error loading Palantir alias '%s'" %
                                     absfile)

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
    config.add_route('palantir_toggle_check', '/palantir/check/toggle')

    config.add_route('palantir_list_alerts', '/palantir/alert/list')
    config.add_route('palantir_resolve_alert', '/palantir/alert/resolve')

    config.add_route('palantir_list_minions', '/palantir/minion/list')
    config.add_route('palantir_get_minion', '/palantir/minion/get')
    config.add_route('palantir_toggle_minion', '/palantir/minion/toggle')
    config.add_route('palantir_delete_minion', '/palantir/minion/delete')

    config.add_route('palantir_toggle_minion_check', '/palantir/minion/check/toggle')
    config.add_route('palantir_get_minion_check', '/palantir/minion/check/get')

    config.add_route('palantir_list_handlers', '/palantir/handler/list')

    config.scan()
