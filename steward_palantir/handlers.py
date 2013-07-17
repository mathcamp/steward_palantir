""" Check result handlers """
import functools
import re

import logging
from jinja2 import Template


LOG = logging.getLogger(__name__)

def log_handler(request, minion, check, status, handler_id):
    """
    Check handler that logs the result of a check

    """
    if status['retcode'] == 0:
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

def fork(request, minion, check, status, handler_id, handlers=None,
         render_args=None):
    """
    Check handler for forking the handler list into a tree

    Parameters
    ----------
    handlers : list
        A list of handlers in the same format as the base ``handlers``
        attribute of a check.
    render_args : dict
        Values to add to the environment when rendering jinja strings

    """
    if render_args is None:
        render_args = {}
    LOG.debug("Forking check handlers")
    for i, handler_dict in enumerate(handlers):
        next_id = handler_id + 'f' + str(i)
        handler_name, params = handler_dict.items()[0]
        if params is None:
            params = {}
        handler = request.registry.palantir_handlers[handler_name]
        try:
            LOG.debug("Running handler '%s'", handler_name)
            # Render any templated handler parameters
            for key, value in params.items():
                if isinstance(value, basestring):
                    render_args.update(minion=minion, check=check,
                                       status=status)
                    params[key] = Template(value).render(**render_args)
            handler_result = handler(request, minion, check, status, next_id,
                                     **params)
            request.palantir_db.set_last_retcode(minion, check.name,
                                                    next_id,
                                                    status['retcode'])
            # If the handler returns True, don't pass to further handlers
            if handler_result is True:
                LOG.debug("Handler '%s' stopped propagation", handler_name)
                break
        except:
            LOG.exception("Error running handler '%s'", handler_name)
            break
    LOG.debug("Leaving fork")

def absorb(request, minion, check, status, handler_id, success=None,
           warn=None, error=None, only_change=False, only_change_status=False,
           count=1, success_count=1, out_match=None, err_match=None,
           out_err_match=None, retcodes=None):
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
    if count > 1 and (only_change or only_change_status):
        raise ValueError("You should not use count > 1 and only_change in the "
                         "same 'absorb' handler. It will drop everything.")

    if success is not None and status['retcode'] == 0:
        return success
    if warn is not None and status['retcode'] == 1:
        return warn
    if error is not None and status['retcode'] not in (0, 1):
        return error
    if status['retcode'] != 0 and status['count'] < count:
        return True
    if status['retcode'] == 0 and status['count'] < success_count:
        return True
    last_retcode = request.palantir_db.last_retcode(minion,
                                                    check.name,
                                                    handler_id)
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
                if split[1]:
                    low, high = split
                    if int(low) <= status['retcode'] <= int(high):
                        return True
                else:
                    if status['retcode'] >= int(split[0]):
                        return True

def alert(request, minion, check, status, handler_id, raised=None,
          resolved=None):
    """
    Raise an alert if a check was passing and is now failing

    Resolve the alert if a check was failing and is now passing

    Parameters
    ----------
    raised : list
        A list of handlers to run if an alert was raised
    resolved : list
        A list of handlers to run if an alert was resolved

    """
    last_retcode = request.palantir_db.last_retcode(minion,
                                                    check.name,
                                                    handler_id)
    if status['retcode'] == 0 and last_retcode != 0:
        status['reason'] = 'Check passing'
        request.subreq('pub', name='palantir/alert/resolved',
                        data=status)
        request.palantir_db.remove_alert(minion, check.name)
        if resolved is not None:
            fork(request, minion, check, status, handler_id, resolved)
    if status['retcode'] != 0 and last_retcode == 0:
        request.subreq('pub', name='palantir/alert/raised',
                        data=status)
        request.palantir_db.add_alert(minion, check.name)
        if raised is not None:
            fork(request, minion, check, status, handler_id, raised)

def mail(request, minion, check, status, handler_id, **kwargs):
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

def alias_factory(name):
    """ Generate an alias handler with a particular name """
    return functools.partial(alias, __name=name)

def alias(request, minion, check, status, handler_id, __name=None, **kwargs):
    """
    Handler for shortcut references to other sets of handlers

    Parameters
    ----------
    __name : str
        The name of the aliased handlers
    **kwargs : dict
        Any keyword arguments passed in will be used for string rendering of
        parameters passed to the handlers.

    """
    data = request.registry.palantir_aliases[__name]
    handlers = data['handlers']
    render_args = data.get('kwargs', {})
    render_args.update(kwargs)
    fork(request, minion, check, status, handler_id, handlers=handlers,
         render_args=render_args)
