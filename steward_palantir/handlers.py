""" Check result handlers """
import re

import logging
from jinja2 import Template


LOG = logging.getLogger(__name__)

def run_handlers(request, result, handlers, render_args=None):
    """
    Run a list of handlers on a check result

    Parameters
    ----------
    result : :class:`~steward_palantir.models.CheckResult`
    handlers : list
        A list of handlers in the same format as the base ``handlers``
        attribute of a check.
    render_args : dict
        Values to add to the environment when rendering jinja strings

    """
    if render_args is None:
        render_args = {}
    for handler_dict in handlers:
        handler_name, params = handler_dict.items()[0]
        if params is None:
            params = {}
        handler = request.registry.palantir_handlers[handler_name]
        try:
            LOG.debug("Running handler '%s'", handler_name)
            # Render any templated handler parameters
            for key, value in params.items():
                if isinstance(value, basestring):
                    render_args.update(result=result)
                    params[key] = Template(value).render(**render_args)
            handler_result = handler(request, result, **params)
            # If the handler returns True, don't pass to further handlers
            if handler_result is True:
                LOG.debug("Handler '%s' stopped propagation", handler_name)
                return True
        except:
            LOG.exception("Error running handler '%s'", handler_name)
            return True

def alias(data, request, result, **kwargs):
    """
    Check handler for calling other check handlers

    Do not use this handler directly. Instead, use the alias system mentioned
    in the README

    """
    render_args = data.get('kwargs', {})
    render_args.update(kwargs)
    handlers = data['handlers']
    return run_handlers(request, result, handlers, render_args)

def log_handler(request, result):
    """
    Check handler that logs the result of a check

    """
    if result.retcode == 0:
        method = 'info'
        msg = 'succeeded'
    elif result.retcode == 1:
        method = 'warn'
        msg = 'warning'
    else:
        method = 'error'
        msg = 'error'
    fxn = getattr(LOG, method)

    count_str = '%d time%s' % (result.count, 's' if result.count > 1 else '')
    fxn("%s check '%s' %s %s with code %d\nSTDOUT:\n%s\nSTDERR:\n%s",
        result.minion, result.check, msg, count_str, result.retcode,
        result.stdout, result.stderr)

def absorb(request, result, success=None, warn=None, error=None,
           alert=None, count=1, success_count=1, out_match=None,
           err_match=None, out_err_match=None, retcodes=None):
    """
    Check handler that acts as a filter and runs before other handlers

    Parameters
    ----------
    success : bool, optional
        If True, absorb success checks. If False, *never* absorb success checks. (default None)
    warn : bool, optional
        If True, absorb warnings. If False, *never* absorb warnings. (default None)
    error : bool, optional
        If True, absorb errors. If False, *never* absorb errors. (default None)
    alert : bool, optional
        If True, absorb alerts. If False, absorb non-alerts. (default None)
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
    if success is not None and result.retcode == 0:
        return success
    if warn is not None and result.retcode == 1:
        return warn
    if error is not None and result.retcode not in (0, 1):
        return error
    if result.retcode != 0 and result.count < count:
        return True
    if result.retcode == 0 and result.count < success_count:
        return True

    if alert is not None:
        if alert and result.alert:
            return True
        elif not alert and not result.alert:
            return True

    if out_match and re.match(out_match, result.stdout):
        return True
    if err_match and re.match(err_match, result.stderr):
        return True
    if out_err_match and (re.match(out_err_match, result.stdout) or
                          re.match(out_err_match, result.stderr)):
        return True
    if retcodes is not None:
        ranges = str(retcodes).split(',')
        for intrange in ranges:
            try:
                if result.retcode == int(intrange):
                    return True
            except ValueError:
                split = intrange.split('-')
                if split[1]:
                    low, high = split
                    if int(low) <= result.retcode <= int(high):
                        return True
                else:
                    if result.retcode >= int(split[0]):
                        return True

def mail(request, result, **kwargs):
    """
    Check handler that sends emails

    This handler takes the same parameters as the mail endpoint

    Parameters
    ----------
    subject : str
        The subject of the email
    body : str
        The body for the email
    mail_to : str, optional
        The 'to' address(es) (comma-delimited) (default specified in ini file)
    mail_from : str, optional
        The 'from' address (default specified in ini file)
    smtp_server : str, optional
        The hostname of the SMTP server (default specified in ini file)
    smtp_port : int, optional
        The port the SMTP server is running on (default specified in ini file)

    Notes
    -----
    This requires :mod:`steward_smtp` to be included in the app

    """
    request.subreq('mail', **kwargs)
