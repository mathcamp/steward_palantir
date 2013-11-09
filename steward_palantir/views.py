""" Endpoints for Palantir """
import logging
from collections import defaultdict
from pyramid.security import unauthenticated_userid
from pyramid.view import view_config

from .models import CheckDisabled, MinionDisabled, CheckResult, Alert
from .tasks import toggle_minion, resolve_alerts, run_check, prune


LOG = logging.getLogger(__name__)


@view_config(route_name='palantir_run_check', renderer='json',
             permission='palantir_write')
def do_run_check(request):
    """
    Run a check

    Parameters
    ----------
    name : str
        The name of the check to run

    """
    check_name = request.param('name')
    return run_check(check_name)


@view_config(route_name='palantir_list_checks', renderer='json',
             permission='palantir_read')
def list_checks(request):
    """ List all available checks """
    checks = request.registry.palantir_checks
    json_checks = {}
    for name, check in checks.iteritems():
        data = check.__json__(request)
        data['enabled'] = not bool(request.db.query(CheckDisabled)
                                   .filter_by(name=name).first())
        json_checks[name] = data
    return json_checks


@view_config(route_name='palantir_get_check', renderer='json',
             permission='palantir_read')
def get_check(request):
    """ Get detailed data about a check """
    name = request.param('check')
    checks = request.registry.palantir_checks
    data = checks[name].__json__(request)
    data['enabled'] = not bool(request.db.query(CheckDisabled)
                               .filter_by(name=name).first())
    data['results'] = request.db.query(CheckResult).filter_by(check=name).all()

    return data


@view_config(route_name='palantir_get_minion_check', renderer='json',
             permission='palantir_read')
def get_minion_check(request):
    """
    Get the current status of a check

    Parameters
    ----------
    minion : str
    check : str

    """
    minion = request.param('minion')
    check = request.param('check')
    return request.db.query(CheckResult).filter_by(minion=minion,
                                                   check=check).one()


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
        if enabled:
            request.db.query(CheckDisabled).filter_by(name=check).delete()
        else:
            request.db.merge(CheckDisabled(check))
    return request.response


@view_config(route_name='palantir_list_alerts', renderer='json',
             permission='palantir_read')
def list_alerts(request):
    """ List all current alerts """
    return request.db.query(Alert).all()


@view_config(route_name='palantir_get_alert', renderer='json',
             permission='palantir_read')
def get_alert(request):
    """ List all current alerts """
    minion = request.param('minion')
    check = request.param('check')
    return request.db.query(Alert)\
        .filter_by(check=check, minion=minion).first()


@view_config(route_name='palantir_resolve_alert', permission='palantir_write')
def do_resolve_alerts(request):
    """ Mark an alert as 'resolved' """
    alerts = request.param('alerts', type=list)
    resolve_alerts(alerts, unauthenticated_userid(request))
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
            'enabled': not bool(request.db.query(MinionDisabled)
                                .filter_by(name=name).first()),
        }
    return minions


@view_config(route_name='palantir_delete_minion', permission='palantir_write')
def delete_minion(request):
    """ Delete a minion and its data """
    minion = request.param('minion')
    request.db.query(MinionDisabled).filter_by(name=minion).delete()
    request.db.query(CheckResult).filter_by(minion=minion).delete()
    request.db.query(Alert).filter_by(minion=minion).delete()
    return request.response


@view_config(route_name='palantir_get_minion', renderer='json',
             permission='palantir_read')
def get_minion(request):
    """ Get some data about a minion """
    minion = request.param('minion')
    data = {'name': minion}
    results = request.db.query(CheckResult).filter_by(minion=minion).all()
    data['checks'] = results
    data['enabled'] = not bool(request.db.query(MinionDisabled)
                               .filter_by(name=minion).first())
    return data


@view_config(route_name='palantir_toggle_minion', permission='palantir_write')
def do_toggle_minion(request):
    """
    Enable/disable a minion

    Parameters
    ----------
    minions : list
    enabled : bool

    """
    minions = request.param('minions', type=list)
    enabled = request.param('enabled', type=bool)
    toggle_minion(minions, enabled)
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
        result = request.db.query(CheckResult).filter_by(check=check,
                                                         minion=minion).first()
        if result is None:
            result = CheckResult(minion, check)
            request.db.add(result)
        result.enabled = enabled
    return request.response


@view_config(route_name='palantir_list_minion_checks', renderer='json',
             permission='palantir_read')
def list_minion_checks(request):
    """ List all salt minions and their associated checks """
    minions = defaultdict(list)
    results = request.db.query(CheckResult).all()
    for result in results:
        minions[result.minion].append(result)
    return dict(minions)


@view_config(route_name='palantir_prune', renderer='json',
             permission='palantir_write')
def prune_data(request):
    """
    Remove minions that have been removed from salt

    Remove check results from checks that no longer exist

    """
    return prune()
