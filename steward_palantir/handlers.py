""" Check result handlers """
import logging
import re


LOG = logging.getLogger(__name__)


class RangeSpec(object):

    """
    Specification of an integer range

    Parameters
    ----------
    spec : int or str
        numbers or ranges (ex. 1-4) separated by commas. Ranges are inclusive.
        The final range may have a trailing '-' to indicate 'all values
        greater than or equal to this number'. (ex. '0,2,100-104,400-')

    """
    def __init__(self, spec):
        self.spec = str(spec)
        self._ranges = self.spec.split(',')

    def __contains__(self, value):
        if len(self.spec) == 0:
            return False
        for intrange in self._ranges:
            try:
                if value == int(intrange):
                    return True
            except ValueError:
                split = intrange.split('-')
                if len(split) == 2 and split[1]:
                    low, high = split
                    if int(low) <= value <= int(high):
                        return True
                else:
                    if value >= int(split[0]):
                        return True

    def __repr__(self):
        return "Range(%s)" % self.spec

    def __str__(self):
        return self.spec


class BaseHandler(object):

    """ Base class for check handlers """
    name = None

    def handle(self, request, check, result, **kwargs):
        """
        The is called to handle the result of a check every time the check is
        run

        If this is implemented, the handler may be used in the 'handlers' list
        of a check.

        Parameters
        ----------
        request : :class:`pyramid.request.Request`
        check : :class:`steward_palantir.check.Check`
        result : :class:`steward_palantir.models.CheckResult`
        **kwargs : dict
            Other parameters for the handler

        Returns
        -------
        halt : bool
            If True, stop running the handlers and raise no alerts for this
            check on this minion.

        """
        raise NotImplementedError

    def handle_alert(self, request, check, normalized_retcode, results,
                     **kwargs):
        """
        This is called while raising or resolving an alert

        If this is implemented, the handler may be used in the 'raised' and
        'resolved' lists of a check. This method differs from ``handle`` in
        that it processes batches of results, which allows for rolling-up
        notifications.

        Parameters
        ----------
        request : :class:`pyramid.request.Request`
        check : :class:`steward_palantir.check.Check`
        normalized_retcode : int
            0, 1, or 2 to denote success, warning, or error
        results : list
            The list of :class:`steward_palantir.models.CheckResult`s to process
        **kwargs : dict
            Other parameters for the handler

        Returns
        -------
        result : None or list
            A list of the CheckResults that passed through this handler.
            Successive handlers will only be run on those CheckResults. If None
            is returned, all CheckResults will be passed on.

        """
        raise NotImplementedError

    def __json__(self, request):
        return "Handler(%s)" % self.name


class LogHandler(BaseHandler):

    """
    Check handler that logs the result of a check

    Parameters
    ----------
    message : str, optional
        Specific message to send to the logs

    """
    name = 'log'

    def __init__(self, message=None):
        self.message = message

    def handle(self, request, check, result, **kwargs):
        self.handle_alert(request, check, result.normalized_retcode, [result],
                **kwargs)

    def handle_alert(self, request, check, normalized_retcode, results,
                     **kwargs):
        if normalized_retcode == 0:
            fxn = LOG.info
            msg = 'succeeded'
        elif normalized_retcode == 1:
            fxn = LOG.warn
            msg = 'warning'
        else:
            fxn = LOG.warn
            msg = 'error'

        if self.message is None:
            fxn("check '%s' %s on %s",
                check.name, msg, ', '.join([result.minion for result in
                                            results]))
        else:
            fxn(self.message)


class AbsorbHandler(BaseHandler):

    """
    Check handler that acts as a filter and runs before other handlers

    Parameters
    ----------
    success : bool, optional
        If True, absorb successes. If False, *never* absorb successes. (default
        None)
    warn : bool, optional
        If True, absorb warnings. If False, *never* absorb warnings. (default None)
    error : bool, optional
        If True, absorb errors. If False, *never* absorb errors. (default None)
    count : int, optional
        Absorb checks unless the check has returned that result this many times
        (default 1)
    out_match : str, optional
        If provided, absorb any check whose stdout matches this regex
    err_match : str, optional
        If provided, absorb any check whose stderr matches this regex
    out_err_match : str, optional
        If provided, absorb any check whose stdout or stderr matches this regex
    retcodes : str, optional
        Absorb checks whose return codes fall into this set. This should match
        the format for :class:`.RangeSpec`

    Notes
    -----
    Here is an example. This will ignore all warnings from the check and only
    pass through errors/successes if the check fails/succeeds 3 times in a row.

        ..code-block:: yaml

            handlers:
              - absorb:
                  count: 3
                  warn: true
              - log:

    """
    name = 'absorb'

    def __init__(self, success=None, warn=None, error=None,
                 count=1, out_match=None,
                 err_match=None, out_err_match=None, retcodes=''):
        self.success = success
        self.warn = warn
        self.error = error
        self.count = count
        self.out_match = out_match
        self.err_match = err_match
        self.out_err_match = out_err_match
        self.retcodes = RangeSpec(retcodes)

    def handle(self, request, check, result, **kwargs):
        if self.success is not None and result.normalized_retcode == 0:
            return self.success
        if self.warn is not None and result.normalized_retcode == 1:
            return self.warn
        if self.error is not None and result.normalized_retcode == 2:
            return self.error

        if self.count > 1 and result.count < self.count:
            return True

        if self.out_match and re.match(self.out_match, result.stdout):
            return True
        if self.err_match and re.match(self.err_match, result.stderr):
            return True
        if self.out_err_match and (re.match(self.out_err_match, result.stdout)
                                   or re.match(self.out_err_match,
                                               result.stderr)):
            return True

        if self.retcodes is not None and result.retcode in self.retcodes:
            return True

    def handle_alert(self, request, check, normalized_retcode, results,
                     **kwargs):
        return [result for result in results
                if self.handle(request, check, result, **kwargs) is not True]


class MutateHandler(BaseHandler): # pylint: disable=W0223

    """
    Check handler that can mutate check results conditionally

    May not be run on alerts.

    .. warning::
        The ordering of handlers that mutate the result is important! A trivial
        example would be if you have a handler that converts warnings to errors
        and another handler that absorbs warnings.

    Parameters
    ----------
    promote_after : int, optional
        If the check has returned a warning (status 1) this many times, promote
        it to an error.

    """
    name = 'mutate'

    def __init__(self, promote_after=None):
        self.promote_after = promote_after

    def handle(self, request, check, result, **kwargs):

        if self.promote_after is not None and result.normalized_retcode == 1:
            if result.count >= self.promote_after:
                result.retcode = 2
            elif (result.old_result.normalized_retcode == 2 and
                  result.old_result.count >= self.promote_after):
                result.retcode = 2
                result.count = result.old_result.count + 1


class MailHandler(BaseHandler): # pylint: disable=W0223

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
    name = 'mail'

    def __init__(self, **kwargs):
        self.kwargs = kwargs

    def handle_alert(self, request, check, normalized_retcode, results,
                     **kwargs):
        request.subreq('mail', **self.kwargs)
