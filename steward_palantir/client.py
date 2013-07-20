""" Client commands """
from datetime import datetime
from pprint import pprint

from steward.colors import green, red, yellow, magenta


def _fuzzy_timedelta(td):
    """ Format a timedelta into a *loose* 'X time ago' string """
    ago_str = lambda x, y:'%d %s%s ago' % (x, y, 's' if x > 1 else '')
    if td.days > 0:
        return ago_str(td.days, 'day')
    hours = td.seconds / 3600
    if hours > 0:
        return ago_str(hours, 'hour')
    minutes = td.seconds / 60
    if minutes > 0:
        return ago_str(minutes, 'minute')
    return ago_str(td.seconds, 'second')

def _format_check_status(status):
    """ Turn a check status into a nicely-formatted string """
    string = status['check'] + ': '
    if status['retcode'] == 0:
        string += "SUCCESS"
        color = green
    elif status['retcode'] == 1:
        string += "WARNING"
        color = yellow
    else:
        string += "ERROR(%d)" % status['retcode']
        color = red
    string = color(string)
    if not status.get('enabled', True):
        string += ' (disabled)'

    ran_at = datetime.fromtimestamp(status['last_run'])
    string += '\nRan at %s (%s)' % (ran_at.isoformat(),
                                    _fuzzy_timedelta(datetime.now() - ran_at))

    if status.get('stdout'):
        string += "\nSTDOUT:\n%s" % status['stdout']
    if status.get('stderr'):
        string += "\nSTDERR:\n%s" % status['stderr']
    return string

def do_alerts(client):
    """ Print all active alerts """
    response = client.cmd('palantir/alert/list').json()
    # Sort by minion, then by check name
    response.sort(key=lambda x:x['check'])
    response.sort(key=lambda x:x['minion'])
    for alert in response:
        alert['name'] = alert['check']
        color = yellow if alert['retcode'] == 1 else red
        print "{} - {}".format(color(alert['minion']),
                                   _format_check_status(alert))

def do_checks(client, check=None):
    """
    List the Palantir checks or print details of one in particular

    Parameters
    ----------
    check : str, optional
        If specified, print out the details of this check

    """
    response = client.cmd('palantir/check/list').json()
    if check is None:
        for name, check in response.iteritems():
            line = name
            if not check['enabled']:
                line += ' (disabled)'
            print line
    else:
        pprint(response[check])

def do_minions(client):
    """ Print the list of minions """
    response = client.cmd('palantir/minion/list').json()
    for name in sorted(response):
        minion = response[name]
        if minion['enabled']:
            print minion['name']
        else:
            print minion['name'] + ' (disabled)'

def do_status(client, minion, check=None):
    """
    Print the result of the last check on a minion

    Parameters
    ----------
    minion : str
        Name of the minion
    check : str, optional
        Name of the check. If not provided, print all checks.

    """
    if check is None:
        response = client.cmd('palantir/minion/get', minion=minion).json()
        header = response['name']
        if not response['enabled']:
            header += ' (disabled)'
        print magenta('-' * len(header))
        print magenta(header)
        for check in response['checks']:
            print _format_check_status(check)
    else:
        response = client.cmd('palantir/minion/check/get', minion=minion,
                            check=check).json()
        if response is None:
            print "Check %s not found on %s" % (check, minion)
            return
        response['name'] = check
        print _format_check_status(response)

def do_run_check(client, check):
    """
    Run a Palantir check

    Parameters
    ----------
    check : str
        Name of the check to run

    """
    response = client.cmd('palantir/check/run', name=check).json()
    if isinstance(response, basestring):
        print response
    else:
        for minion, result in response.iteritems():
            result['name'] = check
            print '{}: {}'.format(green(minion), _format_check_status(result))

def do_resolve(client, minion, check):
    """
    Mark an alert as resolved

    Parameters
    ----------
    minion : str
        Name of the minion
    check : str
        Name of the check

    """
    client.cmd('palantir/alert/resolve', minion=minion, check=check)

def do_minion_enable(client, *minions):
    """
    Enable one or more minions

    Parameters
    ----------
    *minions : list
        The minions to enable

    """
    client.cmd('palantir/minion/toggle', minions=minions, enabled=True)

def do_minion_disable(client, *minions):
    """
    Disable one or more minions

    Parameters
    ----------
    *minions : list
        The minions to disable

    """
    client.cmd('palantir/minion/toggle', minions=minions, enabled=False)

def do_check_enable(client, *checks):
    """
    Enable one or more checks

    Parameters
    ----------
    *checks : list
        The checks to enable

    """
    client.cmd('palantir/check/toggle', checks=checks, enabled=True)

def do_check_disable(client, *checks):
    """
    Disable one or more checks

    Parameters
    ----------
    *checks : list
        The checks to disable

    """
    client.cmd('palantir/check/toggle', checks=checks, enabled=False)

def do_minion_check_enable(client, minion, *checks):
    """
    Enable one or more checks on a specific minion

    Parameters
    ----------
    minion : str
        The minion to enable checks on
    *checks : list
        The checks to enable on the minion

    """
    client.cmd('palantir/minion/check/toggle', minion=minion, checks=checks,
               enabled=True)

def do_minion_check_disable(client, minion, *checks):
    """
    Disable one or more checks on a specific minion

    Parameters
    ----------
    minion : str
        The minions to disable checks on
    *checks : list
        The checks to disable on the minion

    """
    client.cmd('palantir/minion/check/toggle', minion=minion, checks=checks,
               enabled=False)
