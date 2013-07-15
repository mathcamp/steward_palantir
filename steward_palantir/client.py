""" Client commands """
from pprint import pprint
from steward.colors import green, red

def _format_check_status(status):
    """ Turn a check status into a nicely-formatted string """
    if status['retcode'] == 0:
        string = "SUCCESS"
    elif status['retcode'] == 1:
        string = "WARNING"
    else:
        string = "ERROR(%d)" % status['retcode']

    if status.get('stdout'):
        string += "\nSTDOUT:\n{}".format(status['stdout'])
    if status.get('stderr'):
        string += "\nSTDERR:\n{}".format(status['stderr'])
    return string

def do_alerts(client):
    """ Print all active alerts """
    response = client.cmd('palantir/alert/list').json()
    for alert in response:
        print "{} - {}: {}".format(red(alert['minion']), red(alert['check']),
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
