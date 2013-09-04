""" Check result handlers """
import logging
import re


LOG = logging.getLogger(__name__)


class BaseHandler(object):

    """ Base class for check handlers """
    name = None

    def __call__(self, request, check, results, **kwargs):
        """
        Handle the results of a check

        Parameters
        ----------
        request : :class:`pyramid.request.Request`
        check : :class:`steward_palantir.check.Check`
        results : list
            The list of :class:`steward_palantir.models.CheckResult`s to process
        **kwargs : dict
            Other parameters for the handler

        Returns
        -------
        result : bool or list
            If result is True, prevent any successive handlers from running on
            these results. If result is a list of
            :class:`steward_palantir.models.CheckResult`s, only run successive
            handlers on that list of results. If False or None, run successive
            handlers on all results.

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

    def __call__(self, request, check, normalized_retcode, results, **kwargs):
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
        If True, absorb success checks. If False, *never* absorb success checks. (default None)
    warn : bool, optional
        If True, absorb warnings. If False, *never* absorb warnings. (default None)
    error : bool, optional
        If True, absorb errors. If False, *never* absorb errors. (default None)
    alert : bool, optional
        If True, absorb alerts. If False, absorb non-alerts. (default None)
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
    name = 'absorb'

    def __init__(self, success=None, warn=None, error=None,
                 alert=None, count=1, out_match=None,
                 err_match=None, out_err_match=None, retcodes=None):
        self.success = success
        self.warn = warn
        self.error = error
        self.alert = alert
        self.count = count
        self.out_match = out_match
        self.err_match = err_match
        self.out_err_match = out_err_match
        self.retcodes = retcodes

    def __call__(self, request, check, normalized_retcode, results, **kwargs):
        if self.success is not None and normalized_retcode == 0:
            return self.success
        if self.warn is not None and normalized_retcode == 1:
            return self.warn
        if self.error is not None and normalized_retcode not in (0, 1):
            return self.error

        if self.alert is not None:
            if self.alert and normalized_retcode != 0:
                return True
            elif not self.alert and normalized_retcode == 0:
                return True

        if self.count > 1:
            return filter(lambda r: r.count >= self.count, results)

        if self.out_match:
            return filter(lambda r: re.match(self.out_match, r.stdout), results)
        if self.err_match:
            return filter(lambda r: re.match(self.err_match, r.stdout), results)
        if self.out_err_match:
            return filter(lambda r: re.match(self.out_err_match, r.stdout) or
                          re.match(self.out_err_match, r.stderr), results)

        if self.retcodes is not None:
            ranges = str(self.retcodes).split(',')

            def match_retcode(result):
                """ Filter function for checking if retcode is in a range """
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
            return filter(match_retcode, results)


class MailHandler(BaseHandler):

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

    def __call__(self, request, check, normalized_retcode, results, **kwargs):
        request.subreq('mail', **self.kwargs)
