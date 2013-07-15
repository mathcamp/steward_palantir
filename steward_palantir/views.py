""" Endpoints for Palantir """
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

    check = request.registry.palantir_checks[check_name]

    expected_minions = request.subreq('salt_match', tgt=check.target,
            expr_form=check.expr_form)
    response = request.subreq('salt', tgt=check.target, cmd='cmd.run_all',
                              kwarg=check.command, expr_form=check.expr_form,
                              timeout=check.timeout)

    if expected_minions is None:
        expected_minions = response.keys()

    combined_minions = set(expected_minions).union(set(response.keys()))

    # Process results for each minion
    check_result = {}
    for minion in combined_minions:
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
        for handler_idx, handler_dict in enumerate(check.handlers):
            handler_name, params = handler_dict.items()[0]
            if params is None:
                params = {}
            handler = request.registry.palantir_handlers[handler_name]
            try:
                last_retcode = request.palantir_db.last_retcode(minion,
                                                                check_name,
                                                                handler_idx)
                handler_result = handler(request, minion, check, status,
                                         last_retcode, **params)
                request.palantir_db.set_last_retcode(minion, check_name,
                                                     handler_idx,
                                                     status['retcode'])
                # If the handler returns True, don't pass to further handlers
                if handler_result is True:
                    break
            except:
                LOG.exception("Error running handler '%s'", handler_name)

    return check_result

@view_config(route_name='palantir_list_checks', renderer='json',
             permission='palantir_read')
def list_checks(request):
    """ List all available checks """
    checks = request.registry.palantir_checks
    json_checks = {}
    for name, check in checks.iteritems():
        data = check.__json__(request)
        data['minions'] = request.subreq('salt_match', tgt=check.target,
                                          expr_form=check.expr_form)
        json_checks[name] = data
    return json_checks

@view_config(route_name='palantir_get_check', renderer='json',
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
    return request.palantir_db.check_status(minion, check)

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
    request.palantir_db.remove_alert(minion, check)
    request.palantir_db.reset_check(minion, check)
    for i in xrange(len(request.registry.palantir_checks[check].handlers)):
        request.palantir_db.set_last_retcode(minion, check, i, 0)
    data = {'reason': 'Marked resolved by %s' % unauthenticated_userid(request)}
    request.subreq('pub', name='palantir/alert/resolve', data=data)
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
    minions = keys['minions']
    return minions

@view_config(route_name='palantir_delete_minion', permission='palantir_write')
def delete_minion(request):
    """ Delete a minion and its data """
    minion = request.param('minion')
    request.palantir_db.delete_minion(minion)
    return request.response

@view_config(route_name='palantir_get_minion', renderer='json',
             permission='palantir_read')
def get_minion(request):
    """ Get the checks that will run on a minion """
    minion = request.param('minion')
    checks = []
    for check in request.registry.palantir_checks.itervalues():
        minions = request.subreq('salt_match', tgt=check.target,
                                            expr_form=check.expr_form)
        if minions is not None and minion in minions:
            checks.append(check)
    return checks
