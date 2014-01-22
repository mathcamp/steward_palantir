""" Steward extension for monitoring servers """
from __future__ import unicode_literals

import imp
import os
import sys
from datetime import timedelta

import inspect
import logging
import yaml
from pyramid.path import DottedNameResolver
from pyramid.settings import aslist

from .check import Check
from .handlers import BaseHandler


LOG = logging.getLogger(__name__)

CHECK_MODULE = 'steward_palantir.plugin_checks'
HANDLER_MODULE = 'steward_palantir.plugin_handlers'

sys.modules[CHECK_MODULE] = imp.new_module(CHECK_MODULE)
sys.modules[HANDLER_MODULE] = imp.new_module(HANDLER_MODULE)


def iterate_files(filedir, loaders):
    """ Generator for file data """
    LOG.debug("Loading palantir files from '%s'", filedir)
    for filename in os.listdir(filedir):
        _, ext = os.path.splitext(filename)
        if ext not in loaders:
            continue
        absfile = os.path.abspath(os.path.join(filedir, filename))
        for result in loaders[ext](absfile):
            yield result


def load_yaml_checks(filepath):
    """ Load checks from yaml files """
    try:
        with open(filepath, 'r') as infile:
            file_data = yaml.safe_load(infile)
            for name, data in file_data.iteritems():
                yield Check(name, **data)
    except (yaml.scanner.ScannerError, yaml.parser.ParserError):
        LOG.exception("Could not load '%s'", filepath)


def load_python_checks(filepath):
    """ Load checks from a file path """
    module_name, _ = os.path.splitext(os.path.basename(filepath))
    module_path = os.path.dirname(filepath)
    module_desc = imp.find_module(module_name, [module_path])
    fullname = CHECK_MODULE + '.' + module_name
    module = imp.load_module(fullname, *module_desc)
    for _, member in inspect.getmembers(module, inspect.isclass):
        if issubclass(member, Check) and member != Check:
            yield member()


def load_handlers_from_path(filepath):
    """ Load check handlers from a file path """
    module_name, _ = os.path.splitext(os.path.basename(filepath))
    module_path = os.path.dirname(filepath)
    module_desc = imp.find_module(module_name, [module_path])
    fullname = HANDLER_MODULE + '.' + module_name
    module = imp.load_module(fullname, *module_desc)
    for _, member in inspect.getmembers(module, inspect.isclass):
        if issubclass(member, BaseHandler) and member != BaseHandler:
            yield member


DEFAULT_LOADERS = {
    '.yaml': load_yaml_checks,
    '.py': load_python_checks,
}


def include_client(client):
    """ Add methods to the client """
    client.set_cmd('palantir.alerts', 'steward_palantir.client.do_alerts')
    client.set_cmd('palantir.checks', 'steward_palantir.client.do_checks')
    client.set_cmd('palantir.status', 'steward_palantir.client.do_status')
    client.set_cmd('palantir.minions', 'steward_palantir.client.do_minions')
    client.set_cmd('palantir.run_check',
                   'steward_palantir.client.do_run_check')
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
    except Exception:
        # autocomplete isn't mandatory
        LOG.warn("Failed to load palantir autocomplete")


def prune(tasklist):
    """ Prune the minions and checks regularly """
    response = tasklist.post('palantir/prune')
    if not response.status_code == 200:
        LOG.warning("Failed to prune palantir minions and checks\n%s",
                    response.text)


def load_checks(settings):
    """ Load all palantir checks """
    checks = {}
    checks_dir = settings.get('palantir.checks_dir', '/etc/steward/checks')
    required_meta = set(aslist(settings.get('palantir.required_meta', [])))
    for check in iterate_files(checks_dir, DEFAULT_LOADERS):
        if check.name in checks:
            LOG.error("Duplicate Palantir check '%s'", check.name)
            continue
        missing_meta = required_meta - set(check.meta.keys())
        if missing_meta:
            LOG.error("Check '%s' is missing meta field(s) '%s'", check.name,
                      ', '.join(missing_meta))
            continue
        checks[check.name] = check
    return checks


def load_handlers(settings):
    """ Load all additional handlers """
    handlers = {}
    name_resolver = DottedNameResolver(__package__)
    handler_files = aslist(settings.get('palantir.handlers',
                                        ['/etc/steward/handlers']))
    handler_files.append('steward_palantir.handlers')
    for mod_name in handler_files:
        # If a file or directory, import and load the handlers
        if os.path.exists(mod_name):
            loaders = {
                '.py': load_handlers_from_path,
            }
            if os.path.isdir(mod_name):
                for handler in iterate_files(mod_name, loaders):
                    handlers[handler.name] = handler
            else:
                for handler in load_handlers_from_path(mod_name):
                    handlers[handler.name] = handler
            continue

        module = name_resolver.resolve(mod_name.strip())
        # If a reference to a handler directly, add it
        if inspect.isclass(module) and issubclass(module, BaseHandler):
            handlers[module.name] = module
            continue

        # Otherwise, import the module and search for handlers
        for _, member in inspect.getmembers(module, inspect.isclass):
            if issubclass(member, BaseHandler) and member != BaseHandler:
                handlers[member.name] = member

    return handlers


def include_tasks(config):
    """ Add tasks """
    checks_dir = config.settings.get('palantir.checks_dir',
                                     '/etc/steward/checks')
    for check in iterate_files(checks_dir, DEFAULT_LOADERS):
        config.add_scheduled_task(check.name, {
            'schedule': timedelta(**check.schedule),
            'task': 'steward_palantir.tasks.run_check',
            'args': [check.name],
        })

    config.add_scheduled_task('palantir_prune', {
        'schedule': timedelta(minutes=10),
        'task': 'steward_palantir.tasks.prune',
    })
    config.registry.palantir_checks = load_checks(config.settings)

    def post_setup_load_handlers():
        """ Load handlers as a callback """
        config.registry.palantir_handlers = load_handlers(config.settings)
    config.after_setup.append(post_setup_load_handlers)


def includeme(config):
    """ Configure the app """
    settings = config.get_settings()

    # Add the handlers
    config.registry.palantir_handlers = load_handlers(settings)

    # Load the checks
    config.registry.palantir_checks = load_checks(settings)

    # Set up the route urls
    config.add_route('palantir_list_checks', '/palantir/check/list')
    config.add_route('palantir_get_check', '/palantir/check/get')
    config.add_route('palantir_run_check', '/palantir/check/run')
    config.add_route('palantir_toggle_check', '/palantir/check/toggle')

    config.add_route('palantir_list_alerts', '/palantir/alert/list')
    config.add_route('palantir_get_alert', '/palantir/alert/get')
    config.add_route('palantir_resolve_alert', '/palantir/alert/resolve')

    config.add_route('palantir_list_minions', '/palantir/minion/list')
    config.add_route('palantir_get_minion', '/palantir/minion/get')
    config.add_route('palantir_toggle_minion', '/palantir/minion/toggle')
    config.add_route('palantir_delete_minion', '/palantir/minion/delete')

    config.add_route('palantir_toggle_minion_check',
                     '/palantir/minion/check/toggle')
    config.add_route('palantir_list_minion_checks',
                     '/palantir/minion/check/list')
    config.add_route('palantir_get_minion_check', '/palantir/minion/check/get')

    config.add_route('palantir_list_handlers', '/palantir/handler/list')
    config.add_route('palantir_prune', '/palantir/prune')

    config.scan(__package__ + '.views')
