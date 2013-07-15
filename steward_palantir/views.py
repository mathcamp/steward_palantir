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

    response = request.subreq('salt', tgt=check.target, cmd='cmd.run_all',
                              kwarg=check.command, expr_form=check.expr_form,
                              timeout=check.timeout)

    # Process results for each minion
    check_result = {}
    for minion, result in response.iteritems():
        status = request.palantir_db.add_check_result(minion, check_name,
                                                      result['retcode'],
                                                      result['stdout'],
                                                      result['stderr'])
        check_result[minion] = status

        # Run all the event handlers
        absorbed = False
        for handler_dict in check.handlers:
            handler_name, params = handler_dict.items()[0]
            if params is None:
                params = {}
            handler = request.registry.palantir_handlers[handler_name]
            try:
                handler_result = handler(request, minion, check, status,
                                         **params)
                # If the handler returns True, don't pass to further handlers
                if handler_result is True:
                    absorbed = True
                    break
            except:
                LOG.exception("Error running handler '%s'", handler_name)

        # Create/resolve alerts
        if not absorbed:
            is_alert = request.palantir_db.is_alert(minion, check_name)
            if status['retcode'] == 0 and is_alert:
                status['reason'] = 'Check passing'
                request.subreq('pub', name='palantir/alert/resolve',
                                data=status)
                request.palantir_db.remove_alert(minion, check_name)
            elif status['retcode'] != 0 and not is_alert:
                request.subreq('pub', name='palantir/alert/create',
                               data=status)
                request.palantir_db.add_alert(minion, check_name)

    return check_result

@view_config(route_name='palantir_list_checks', renderer='json',
             permission='palantir_read')
def list_checks(request):
    """ List all available checks """
    return request.registry.palantir_checks

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
