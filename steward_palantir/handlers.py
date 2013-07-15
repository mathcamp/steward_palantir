""" Check result handlers """
import re

import logging


LOG = logging.getLogger(__name__)

def log_handler(request, minion, check, status, log_success=False):
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

def absorb(request, minion, check, status, success=False, warn=False, count=1,
        success_count=1, out_match=None, err_match=None,
        out_err_match=None):
    """
    Check handler that acts as a filter and runs before other handlers

    Parameters
    ----------
    success : bool, optional
        Absorb checks that pass (default False)
    warn : bool, optional
        Absorb checks that are warnings (status code 1) (default False)
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

    """
    if status['retcode'] == 0 and success:
        return True
    if status['retcode'] == 1 and warn:
        return True
    if status['retcode'] != 0 and status['count'] < count:
        return True
    if status['retcode'] == 0 and status['count'] < success_count:
        return True
    if out_match and re.match(out_match, status['stdout']):
        return True
    if err_match and re.match(err_match, status['stderr']):
        return True
    if out_err_match and (re.match(out_err_match, status['stdout']) or
                          re.match(out_err_match, status['stderr'])):
        return True
