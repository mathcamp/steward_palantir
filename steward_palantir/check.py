""" Model objects for checks and running them """
from __future__ import unicode_literals

import logging
from datetime import timedelta


LOG = logging.getLogger(__name__)


class CheckRunner(object):

    """
    Creates the task interval function and runs a check

    Parameters
    ----------
    config : :class:`pyramid.config.Configurator`
        The app config object
    name : str
        The name of the check
    schedule : dict
        The schedule for when to run the check

    """
    def __init__(self, tasklist, name, schedule):
        self.__name__ = 'Check(%s)' % name
        self.tasklist = tasklist
        self.name = name
        self.interval = timedelta(**schedule)
        self.first_run = True

    def __call__(self):
        data = {'name': self.name}
        response = self.tasklist.post('palantir/check/run', data=data)
        if not response.ok:
            LOG.error("Error running '%s'\n%s", self, response.text)

    @classmethod
    def from_check(cls, tasklist, check):
        """ Construct from a Check """
        return cls(tasklist, check.name, check.schedule)

    @property
    def schedule_fxn(self):
        """ Function used by steward tasks to schedule the check """
        def next_run(dt):
            """ Run the check immediately, and then on an interval """
            if self.first_run:
                self.first_run = False
                return dt
            return dt + self.interval
        return next_run

    def __str__(self):
        return self.__name__


class Check(object):

    """
    Container object for a check

    Parameters
    ----------
    name : str
        The name of the check
    command : dict
        Keyword arguments to the 'cmd.run_all' salt module. 'cmd' must be
        specified.
    schedule : dict
        Keyword arguments to the :class:`datetime.timedelta` constructor
    target : str, optional
        The salt target string. If not present, will only be run on the
        palantir server.
    expr_form : str, optional
        The type of target matching to use for salt (default 'glob')
    timeout : int, optional
        How long in seconds for salt to wait for a response (default 10)
    handlers : list, optional
        List of dicts. Each dict has a single key-value which is the name of
        the handler and a dict representing the keyword arguments that will be
        passed in (may be None).
    raised : list, optional
        Same form as ``handlers``. Only called when a alert is raised.
    resolved : list, optional
        Same form as ``handlers``. Only called when a alert is resolved.
    meta : dict, optional
        Dictionary of arbitrary metadata for the check

    """
    def __init__(self, name, command, schedule, target=None, expr_form=None,
                 timeout=None, handlers=(), raised=(), resolved=(), meta=None):
        self.name = unicode(name)
        self.target = target
        self.expr_form = expr_form
        self.timeout = timeout
        if self.target is None:
            if self.expr_form is not None:
                raise ValueError("Cannot use expr_form when target is blank!")
            if self.timeout is not None:
                raise ValueError("Cannot use timeout when target is blank!")
        else:
            if self.expr_form is None:
                self.expr_form = 'glob'
            if self.timeout is None:
                self.timeout = 10
        self.command = command
        self.schedule = schedule
        self.handlers = handlers
        self.raised = raised
        self.resolved = resolved
        self.meta = meta or {}

    def _get_handlers(self, request, action, normalized_retcode, results,
                     **kwargs):
        """ Get the list of handlers to run. Useful to override """
        if action == 'resolve':
            return self.resolved
        elif action == 'raise':
            return self.raised
        else:
            raise ValueError("Unrecognized action '%s'" % action)

    def _build_handlers(self, request, handlers):
        """ Instantiate any handlers that are just the data representation """
        handler_instances = []
        for handler in handlers:
            # If the handler is a data representation, construct it
            if isinstance(handler, dict):
                name, args = handler.items()[0]
                args = args or {}
                handler_instances.append(request.registry.palantir_handlers[name](**args))
            else:
                handler_instances.append(handler)
        return handler_instances

    def _run_alert_handler_list(self, request, normalized_retcode, results,
                                handlers, **kwargs):
        """
        Run the alert handlers iteratively

        Returns
        -------
        check_results : list
            List of all the check results that made it through all the handlers

        """
        for handler in handlers:
            try:
                LOG.debug("Running handler '%s'", handler)
                handler_result = handler.handle_alert(request, self,
                                                      normalized_retcode,
                                                      results, **kwargs)
                if handler_result is not None:
                    # If the handler returns a list of results, only apply
                    # successive handlers to that list
                    if len(handler_result) == 0:
                        return []
                    results = handler_result
            except:
                LOG.exception("Error running handler '%s'", handler.name)
                return []


    def run_alert_handlers(self, request, action, normalized_retcode, results,
                           **kwargs):
        """
        Run a list of handlers on a check result when raising or resolving an
        alert

        Parameters
        ----------
        request : :class:`pyramid.request.Request`
        action : str {'raise', 'resolve'}
            What action triggered these handlers
        normalized_retcode : int
            0, 1, or 2 denoting success, warning, or error
        results : list
            List of :class:`~steward_palantir.models.CheckResult`s
        **kwargs : dict
            Other arguments to pass to handlers

        Returns
        -------
        check_results : list
            List of all the check results that made it through all the handlers

        """
        handlers = self._get_handlers(request, action, normalized_retcode,
                                     results, **kwargs)

        handlers = self._build_handlers(request, handlers)

        return self._run_alert_handler_list(request, normalized_retcode,
                                            results, handlers, **kwargs)


    def _run_handler_list(self, request, result, handlers, **kwargs):
        """ Run the handlers iteratively """
        for handler in handlers:
            try:
                LOG.debug("Running handler '%s'", handler)
                handler_result = handler.handle(request, self, result,
                                                **kwargs)
                if handler_result is True:
                    return True
            except:
                LOG.exception("Error running handler '%s'", handler.name)
                return True


    def run_handler(self, request, result, **kwargs):
        """
        Run a list of handlers on a check result

        Parameters
        ----------
        request : :class:`pyramid.request.Request`
        result : :class:`~steward_palantir.models.CheckResult`
        **kwargs : dict
            Other arguments to pass to handlers

        Returns
        -------
        halted : bool
            If True, the result did not make it through all the handlers

        """
        handlers = self._build_handlers(request, self.handlers)

        return self._run_handler_list(request, result, handlers, **kwargs)


    def __json__(self, request):
        return {
            'name': self.name,
            'target': self.target,
            'expr_form': self.expr_form,
            'timeout': self.timeout,
            'command': self.command,
            'schedule': self.schedule,
            'meta': self.meta,
        }

    def __unicode__(self):
        return unicode(self.name)

    def __str__(self):
        return unicode(self).encode('utf-8')

    def __repr__(self):
        return 'Check(%s)' % self.name
