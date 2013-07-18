""" Endpoints for Palantir """
from .handlers import fork
import logging
from pyramid.security import unauthenticated_userid
from pyramid.view import view_config


LOG = logging.getLogger(__name__)

@view_config(route_name='palantir_run_check', renderer='json',
             permission='palantir_write')
def run_check(request):
    """
    Run a check

    Parameters
    ----------
    name : str
        The name of the check to run

    """
    check_name = request.param('name')

    if not request.palantir_db.is_check_enabled(check_name):
        return 'check disabled'

    check = request.registry.palantir_checks[check_name]

    expected_minions = request.subreq('salt_match', tgt=check.target,
            expr_form=check.expr_form)
    if expected_minions is None:
        target = check.target
        expr_form = check.expr_form
    else:
        i = 0
        while i < len(expected_minions):
            minion = expected_minions[i]
            if not request.palantir_db.is_minion_enabled(minion) or \
            not request.palantir_db.is_minion_check_enabled(minion, check_name):
                del expected_minions[i]
                continue
            i += 1
        target = ','.join(expected_minions)
        expr_form = 'list'
        if len(expected_minions) == 0:
            return 'No minions matched'

    response = request.subreq('salt', tgt=target, cmd='cmd.run_all',
                              kwarg=check.command, expr_form=expr_form,
                              timeout=check.timeout)

    if expected_minions is None:
        expected_minions = response.keys()

    combined_minions = set(expected_minions).union(set(response.keys()))

    # Process results for each minion
    check_result = {}
    for minion in combined_minions:
        if not request.palantir_db.is_minion_enabled(minion) or \
        not request.palantir_db.is_minion_check_enabled(minion, check_name):
            continue
        # Get the response. If no response, replace it with a 'salt timeout'
        # message
        result = response.get(minion, {
            'retcode': 1000,
            'stdout': '',
            'stderr': '<< SALT TIMED OUT >>',
        })
        status = request.palantir_db.add_check_result(minion, check_name,
                                                      result['retcode'],
                                                      result['stdout'],
                                                      result['stderr'])
        check_result[minion] = status

        # Run all the event handlers
        fork(request, minion, check, status, '0', handlers=check.handlers)

    return check_result

@view_config(route_name='palantir_list_checks', renderer='json',
             permission='palantir_read')
def list_checks(request):
    """ List all available checks """
    checks = request.registry.palantir_checks
    json_checks = {}
    for name, check in checks.iteritems():
        data = check.__json__(request)
        data['enabled'] = request.palantir_db.is_check_enabled(name)
        data['minions'] = request.subreq('salt_match', tgt=check.target,
                                          expr_form=check.expr_form)
        json_checks[name] = data
    return json_checks

@view_config(route_name='palantir_get_minion_check', renderer='json',
             permission='palantir_read')
def get_check(request):
    """
    Get the current status of a check

    Parameters
    ----------
    minion : str
    check : str

    """
    minion = request.param('minion')
    check = request.param('check')
    data = request.palantir_db.check_status(minion, check)
    data['enabled'] = request.palantir_db.is_check_enabled(check)
    return data

@view_config(route_name='palantir_toggle_check', permission='palantir_write')
def toggle_check(request):
    """
    Enable/disable a check

    Parameters
    ----------
    checks : list
    enabled : bool

    """
    checks = request.param('checks', type=list)
    enabled = request.param('enabled', type=bool)
    for check in checks:
        request.palantir_db.set_check_enabled(check, enabled)
    return request.response

@view_config(route_name='palantir_list_alerts', renderer='json',
             permission='palantir_read')
def list_alerts(request):
    """ List all current alerts """
    checks = []
    for minion, check in request.palantir_db.get_alerts():
        status = request.palantir_db.check_status(minion, check)
        status['minion'] = minion
        status['check'] = check
        checks.append(status)
    return checks

@view_config(route_name='palantir_resolve_alert', permission='palantir_write')
def resolve_alert(request):
    """ Mark an alert as 'resolved' """
    minion = request.param('minion')
    check = request.param('check')
    request.palantir_db.clear_last_retcode(minion, check)
    request.palantir_db.remove_alert(minion, check)
    request.palantir_db.reset_check(minion, check)
    data = {'reason': 'Marked resolved by %s' % unauthenticated_userid(request)}
    request.subreq('pub', name='palantir/alert/resolved', data=data)
    return request.response

@view_config(route_name='palantir_list_handlers', renderer='json',
             permission='palantir_read')
def list_handlers(request):
    """ List all current handlers """
    return {name: handler.__doc__ for name, handler in
            request.registry.palantir_handlers.iteritems()}

@view_config(route_name='palantir_list_minions', renderer='json',
             permission='palantir_read')
def list_minions(request):
    """ List all salt minions """
    keys = request.subreq('salt_key', cmd='list_keys')
    minions = {}
    for name in keys['minions']:
        minions[name] = {
            'name': name,
            'enabled': request.palantir_db.is_minion_enabled(name),
        }
    return minions

@view_config(route_name='palantir_delete_minion', permission='palantir_write')
def delete_minion(request):
    """ Delete a minion and its data """
    minion = request.param('minion')
    request.palantir_db.delete_minion(minion)
    return request.response

@view_config(route_name='palantir_prune_minions', renderer='json',
             permission='palantir_write')
def prune_minions(request):
    """ Remove minions that have been removed from salt """
    minion_list = request.subreq('palantir_list_minions').keys()
    minions = set(minion_list)
    old_minions = set(request.palantir_db.get_minions())
    removed = old_minions - minions
    added = minions - old_minions
    for minion in removed:
        LOG.info("Removing minion '%s'", minion)
        request.palantir_db.delete_minion(minion)
    request.palantir_db.set_minions(minion_list)
    return {
        'removed': list(removed),
        'added': list(added),
    }

@view_config(route_name='palantir_get_minion', renderer='json',
             permission='palantir_read')
def get_minion(request):
    """ Get the checks that will run on a minion """
    minion = request.param('minion')
    data = {'name': minion}
    check_names = request.palantir_db.minion_checks(minion)
    checks = []
    for name in check_names:
        check = request.palantir_db.check_status(minion, name)
        check['name'] = name
        check['minion_check_enabled'] = request.palantir_db.is_minion_check_enabled(minion, name)
        check['enabled'] = request.palantir_db.is_check_enabled(name)
        checks.append(check)
    data['checks'] = checks
    data['enabled'] = request.palantir_db.is_minion_enabled(minion)
    return data

@view_config(route_name='palantir_toggle_minion', permission='palantir_write')
def toggle_minion(request):
    """
    Enable/disable a minion

    Parameters
    ----------
    minions : list
    enabled : bool

    """
    minions = request.param('minions', type=list)
    enabled = request.param('enabled', type=bool)
    for minion in minions:
        request.palantir_db.set_minion_enabled(minion, enabled)
    return request.response

@view_config(route_name='palantir_toggle_minion_check',
             permission='palantir_write')
def toggle_minion_check(request):
    """
    Enable/disable a check on a specific minion

    Parameters
    ----------
    minion : str
    checks : list
    enabled : bool

    """
    minion = request.param('minion')
    checks = request.param('checks', type=list)
    enabled = request.param('enabled', type=bool)
    for check in checks:
        request.palantir_db.set_minion_check_enabled(minion, check, enabled)
    return request.response
