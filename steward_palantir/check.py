""" Model objects for checks and running them """
from datetime import timedelta

import logging


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
        data = {'name':self.name}
        response = self.tasklist.post('palantir/check/run', data=data)
        if not response.ok:
            LOG.error("Error running '%s'\n%s", self, response.text)

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


class Check(object):
    """
    Container object for a check

    Parameters
    ----------
    name : str
        The name of the check
    data : dict
        The raw check data loaded from the file

    Attributes
    ----------
    name : str
    target : str
        The salt target string
    command : dict
        Keyword arguments to the 'cmd.run_all' salt module. 'cmd' must be
        specified.
    schedule : dict
        Keyword arguments to the :class:`datetime.timedelta` constructor
    handlers : list, optional
        List of dicts. Each dict has a single key-value which is the name of
        the handler and a dict representing the keyword arguments that will be
        passed in (may be None).
    raised : list, optional
        Same form as ``handlers``. Only called when a alert is raised.
    resolved : list, optional
        Same form as ``handlers``. Only called when a alert is resolved.
    expr_form : str, optional
        The type of target matching to use for salt (default 'glob')
    timeout : int, optional
        How long for salt to wait for a response (default 10 seconds)

    """
    def __init__(self, name, data):
        self.name = name
        self.target = data['target']
        self.expr_form = data.get('expr_form', 'glob')
        self.timeout = data.get('timeout', 10)
        self.command = data['command']
        self.schedule = data['schedule']
        self.handlers = data.get('handlers', [])
        self.raised = data.get('raised', [])
        self.resolved = data.get('resolved', [])

    def __json__(self, request):
        return {
            'name': self.name,
            'target': self.target,
            'expr_form': self.expr_form,
            'timeout': self.timeout,
            'command': self.command,
            'schedule': self.schedule,
            'handlers': self.handlers,
            'raised': self.raised,
            'resolved': self.resolved,
        }

    def __str__(self):
        return self.name

    def __repr__(self):
        return 'Check(%s)' % self.name
