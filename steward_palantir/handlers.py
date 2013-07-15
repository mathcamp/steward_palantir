""" Check result handlers """
import re

import logging


LOG = logging.getLogger(__name__)

def log_handler(request, minion, check, status, last_retcode, log_success=False):
    """
    Check handler that logs the result of a check

    Parameters
    ----------
    log_success : bool, optional
        If True, will log even when the check succeeds (default False)

    """
    if status['retcode'] == 0:
        if not log_success:
            return
        method = 'info'
        msg = 'succeeded'
    elif status['retcode'] == 1:
        method = 'warn'
        msg = 'warning'
    else:
        method = 'error'
        msg = 'error'
    fxn = getattr(LOG, method)
    fxn("%s check '%s' %s with code %d\nSTDOUT:\n%s\nSTDERR:\n%s", minion,
        check, msg, status['retcode'], status['stdout'], status['stderr'])

def absorb(request, minion, check, status, last_retcode, success=False,
           warn=False, only_change=False, only_change_status=False, count=1,
           success_count=1, out_match=None, err_match=None, out_err_match=None,
           retcodes=None):
    """
    Check handler that acts as a filter and runs before other handlers

    Parameters
    ----------
    success : bool, optional
        Absorb checks that pass (default False)
    warn : bool, optional
        Absorb checks that are warnings (status code 1) (default False)
    only_change : bool, optional
        Absorb checks with the same retcode as the last check (default False)
    only_change_status : bool, optional
        Absorb checks in the same status category (success, warning, error) as
        the last check (default False)
    count : int, optional
        Absorb non-success checks unless the check has returned that result
        this many times (default 1)
    success_count : int, optional
        Absorb success checks unless the check has succeeded this many times
        (default 1)
    out_match : str, optional
        If provided, absorb any check whose stdout matches this regex
    err_match : str, optional
        If provided, absorb any check whose stderr matches this regex
    out_err_match : str, optional
        If provided, absorb any check whose stdout or stderr matches this regex
    retcodes : str, optional
        Absorb checks whose return codes fall into this set. You may pass in
        numbers or ranges (ex. 1-4) separated by commas. Ranges are inclusive.
        The final range may have a trailing '-' to indicate 'and all retcodes
        greater than or equal to this number'. For example: 0,2,100-104,400-

    Notes
    -----
        Here is an example. This will ignore all warnings from the check and
        only pass through errors if the check fails 3 times in a row.

        ..code-block:: yaml

            handlers:
                - absorb:
                    count: 3
                    warn: true
                - log:
                - alert:

    """
    if status['retcode'] == 0 and success:
        return True
    if status['retcode'] == 1 and warn:
        return True
    if status['retcode'] != 0 and status['count'] < count:
        return True
    if status['retcode'] == 0 and status['count'] < success_count:
        return True
    if only_change and status['retcode'] == last_retcode:
        return True
    if only_change_status:
        if status['retcode'] == last_retcode:
            return True
        if status['retcode'] not in (0, 1) and last_retcode not in (0, 1):
            return True
    if out_match and re.match(out_match, status['stdout']):
        return True
    if err_match and re.match(err_match, status['stderr']):
        return True
    if out_err_match and (re.match(out_err_match, status['stdout']) or
                          re.match(out_err_match, status['stderr'])):
        return True
    if retcodes is not None:
        ranges = str(retcodes).split(',')
        for intrange in ranges:
            try:
                if status['retcode'] == int(intrange):
                    return True
            except ValueError:
                split = intrange.split('-')
                if len(split) == 1:
                    if status['retcode'] >= split[0]:
                        return True
                else:
                    low, high = split
                    if int(low) <= status['retcode'] <= int(high):
                        return True

def alert(request, minion, check, status, last_retcode, manual_resolve=False):
    """
    Create an alert if a check was passing and is now failing

    Resolve the alert if a check was failing and is now passing

    Parameters
    ----------
    manual_resolve : bool, optional
        If True, the alert will persist until you resolve the alert by hand
        (default False)

    """
    if status['retcode'] == 0 and last_retcode != 0 and not manual_resolve:
        status['reason'] = 'Check passing'
        request.subreq('pub', name='palantir/alert/resolve',
                        data=status)
        request.palantir_db.remove_alert(minion, check.name)
    if status['retcode'] != 0 and last_retcode == 0:
        request.subreq('pub', name='palantir/alert/create',
                        data=status)
        request.palantir_db.add_alert(minion, check.name)
