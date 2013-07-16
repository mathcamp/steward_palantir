""" Client commands """
from pprint import pprint
from steward.colors import green, red, yellow, magenta

def _format_check_status(status):
    """ Turn a check status into a nicely-formatted string """
    if status['retcode'] == 0:
        string = green("SUCCESS")
    elif status['retcode'] == 1:
        string = yellow("WARNING")
    else:
        string = red("ERROR(%d)" % status['retcode'])

    if status.get('stdout'):
        string += "\nSTDOUT:\n{}".format(status['stdout'])
    if status.get('stderr'):
        string += "\nSTDERR:\n{}".format(status['stderr'])
    return string

def do_alerts(client):
    """ Print all active alerts """
    response = client.cmd('palantir/alert/list').json()
    # Sort by minion, then by check name
    response.sort(key=lambda x:x['check'])
    response.sort(key=lambda x:x['minion'])
    for alert in response:
        color = yellow if alert['retcode'] == 1 else red
        print "{} - {}: {}".format(color(alert['minion']),
                                   color(alert['check']),
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
        print ', '.join(response)
    else:
        pprint(response[check])

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
        for name, check in response.iteritems():
            header = name
            print magenta('-' * len(name))
            print magenta(header)
            print _format_check_status(check)
    else:
        response = client.cmd('palantir/check/get', minion=minion,
                            check=check).json()
        if response is None:
            print "Check %s not found on %s" % (check, minion)
            return
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
    for minion, result in response.iteritems():
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
