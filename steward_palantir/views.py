""" Endpoints for Palantir """
import itertools
from datetime import datetime

import logging
from pyramid.security import unauthenticated_userid
from pyramid.view import view_config

from .handlers import run_handlers
from .models import CheckDisabled, MinionDisabled, CheckResult, Alert


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

    if request.db.query(CheckDisabled).filter_by(name=check_name).first():
        return 'check disabled'

    check = request.registry.palantir_checks[check_name]

    def do_minion_check(minion, check):
        """ Should this check be run on this minion """
        if request.db.query(MinionDisabled).filter_by(name=minion).first():
            return False
        result = request.db.query(CheckResult).filter_by(minion=minion,
                                                         check=check).first()
        if result is not None and not result.enabled:
            return False
        return True

    if check.target is None:
        response = request.subreq('salt_call', cmd='cmd.run_all',
                                  kwarg=check.command)
        expected_minions = None
        response = {'__global__': response}
    else:
        expected_minions = request.subreq('salt_match', tgt=check.target,
                expr_form=check.expr_form)
        if expected_minions is None:
            target = check.target
            expr_form = check.expr_form
        else:
            i = 0
            while i < len(expected_minions):
                minion = expected_minions[i]
                if not do_minion_check(minion, check_name):
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
    check_results = {}
    for minion in combined_minions:
        if not do_minion_check(minion, check_name):
            continue
        # Get the response. If no response, replace it with a 'salt timeout'
        # message
        result = response.get(minion, {
            'retcode': 1000,
            'stdout': '',
            'stderr': '<< SALT TIMED OUT >>',
        })

        check_result = request.db.query(CheckResult)\
                .filter_by(check=check_name, minion=minion).first()
        if check_result is None:
            check_result = CheckResult(minion, check.name)
            request.db.add(check_result)
        else:
            if check_result.retcode == result['retcode']:
                check_result.count += 1
            else:
                check_result.count = 1
        check_result.stdout = result['stdout']
        check_result.stderr = result['stderr']
        check_result.retcode = result['retcode']
        check_result.last_run = datetime.now()

        # Run all the event handlers
        handler_result = run_handlers(request, check_result, check.handlers)

        if handler_result is not True:
            if check_result.alert and check_result.retcode == 0:
                check_result.alert = False
                request.db.query(Alert).filter_by(minion=minion,
                                                  check=check_name).delete()
                request.subreq('pub', name='palantir/alert/resolved',
                                data=check_result.__json__(request))
                run_handlers(request, check_result, check.resolved)

            elif not check_result.alert and check_result.retcode != 0:
                check_result.alert = True
                request.db.add(Alert.from_result(check_result))
                request.subreq('pub', name='palantir/alert/raised',
                                data=check_result.__json__(request))
                run_handlers(request, check_result, check.raised)

        check_results[minion] = check_result

    return check_results

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
            request.db.add(CheckDisabled(check))
    return request.response

@view_config(route_name='palantir_list_alerts', renderer='json',
             permission='palantir_read')
def list_alerts(request):
    """ List all current alerts """
    return request.db.query(Alert).all()

@view_config(route_name='palantir_resolve_alert', permission='palantir_write')
def resolve_alert(request):
    """ Mark an alert as 'resolved' """
    minion = request.param('minion')
    check_name = request.param('check')
    check = request.registry.palantir_checks[check_name]
    result = request.db.query(CheckResult).filter_by(minion=minion,
                                                     check=check_name).one()
    result.alert = False
    request.db.query(Alert).filter_by(minion=minion, check=check_name).delete()
    render_args = {'marked_resolved': True}
    run_handlers(request, result, check.resolved, render_args=render_args)
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
            'enabled': not bool(request.db.query(MinionDisabled)
                                .filter_by(name=name).first()),
        }
    minions['__global__'] = {
        'name': '__global__',
        'enabled': True,
    }
    return minions

@view_config(route_name='palantir_delete_minion', permission='palantir_write')
def delete_minion(request):
    """ Delete a minion and its data """
    minion = request.param('minion')
    request.db.query(MinionDisabled).filter_by(name=minion).delete()
    request.db.query(CheckResult).filter_by(minion=minion).delete()
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
        if enabled:
            request.db.query(MinionDisabled).filter_by(name=minion).delete()
        else:
            request.db.add(MinionDisabled(minion))
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

@view_config(route_name='palantir_prune', renderer='json',
             permission='palantir_write')
def prune_data(request):
    """
    Remove minions that have been removed from salt

    Remove check results from checks that no longer exist

    """
    check_names = request.registry.palantir_checks
    request.db.query(CheckResult)\
            .filter(CheckResult.check.notin_(check_names))\
            .delete(synchronize_session=False)


    minion_list = request.subreq('palantir_list_minions').keys()
    minions = set(minion_list)
    old_minions = set(itertools.chain.from_iterable(
        request.db.query(CheckResult.minion)
        .group_by(CheckResult.minion).all()))
    removed = old_minions - minions
    added = minions - old_minions
    for minion in removed:
        request.subreq('palantir_delete_minion', minion=minion)
    return {
        'removed': list(removed),
        'added': list(added),
    }
