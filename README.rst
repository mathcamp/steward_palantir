Steward Palantir
================
Palantir is a Steward extension for monitoring.

Setup
=====
To use steward_palantir, just add it to your includes either programmatically::

    config.include('pyramid_tm')
    config.include('steward_sqlalchemy')
    config.include('steward_tasks')
    config.include('steward_palantir')

or in the config.ini file::

    pyramid.includes =
        pyramid_tm
        steward_sqlalchemy
        steward_tasks
        steward_palantir

Make sure you include it in the client config file as well.

Web Interface
=============

There is also a web interface for Palantir, which relies on ``steward_web``. To
use the web interface, add more includes::

    config.include('steward_web')
    config.include('steward_palantir.web')

or::

    pyramid.includes =
        steward_web
        steward_palantir.web

And make sure you include the jinja templates in your config file::

    jinja2.directories =
        steward_web:templates
        steward_palantir.web:templates

Quick Start
===========
First thing you need to do is add a check to the checks directory

/etc/steward/checks/up.yaml::

    up:
      target: "*"
      command:
        cmd: /bin/true

      handlers:
        - log:

      schedule:
        minutes: 1

Now start the server. You won't see anything yet, because the checks are not
being run. To run the checks, you will need to run ``steward-tasks
config.ini``, which will start all steward tasks. See steward_tasks for more
information.

You should now see log entries for the results of the checks (make sure your
logging is configured and will log 'INFO' level).

That's it! You now have a working health check for all your minions!

Configuration
=============
::

    # Directory containing the checks. Optional. Default /etc/steward/checks
    palantir.checks_dir = /etc/steward/checks

    # List of additional handlers. May specify the dotted path to a handler,
    # the dotted path to a module with handlers in it, the file name of a
    # module with handlers in it, or a directory that contains python files
    # with handlers. Optional. Default /etc/steward/handlers. See
    # steward_palantir.handlers for built-in handlers.
    palantir.handlers =
        /etc/steward/handlers
        my_package.handlers

    # List of fields that are required in your check metadata. Used to enforce
    # good conventions within your organization. Optional.
    palantir.required_meta =
        owner
        description
        resolve_steps

Permissions
===========
::

    # Allows users to see server & check data
    palantir.perm.palantir_read = group1 group2

    # Allows users to remove minions, run checks, etc.
    palantir.perm.palantir_write = group1

Checks
======
A check is a collection of data that defines a single assertion that you want
to make about your system. Here is an annotated example of a complete check::

    # The name of a check
    mycheck:

      # The salt target to run the check on.
      target: "*"

      # The type of matching to do for salt (default 'glob')
      expr_form: glob

      # How long for salt to wait for responses (default 10)
      timeout: 10

      # Command to run using the ``cmd.run_all`` salt module. Fields are passed
      # in as keyword arguments. Some basic options are listed below.
      command:
        cmd: echo "hello {{ grains['id'] }}!"
        template: jinja
        timeout: 1

      # Optional dict of any metadata about the check
      meta:
        owner: Cave Johnson
        owner_email: cave@aperture.com
        description: Basic health test for salt
        causes: Salt minion is probably down. Try restarting it (service salt-minion restart)
        severity: low

      # A list of handlers for the check. This is a list of dicts that maps the
      # name of the handler to an optional list of keyword arguments to pass in
      # to the handler
      handlers:
        - absorb:
            count: 2

      # A list of handlers to run when an alert is raised
      raised:
        - log:

      # A list of handlers to run when an alert is resolved
      resolved:
        - log:

      # How frequently to run the check. Fields are passed in as keyword
      # arguments to datetime.timedelta
      schedule:
        days: 1
        hours: 3
        minutes: 15
        seconds: 30

You can put as many checks as you want into a single file, and you can put as
many check files as you want into the check_dir. The files must end with
'.yaml'.

The command that you run in the `command` section will most likely be a custom
script. There are a few useful scripts provided in this repository, but any
nagios script will work. It should print out useful information to stdout or
stderr, and the exit status of the script will determine the status.

* 0 - Check succeeded. All is well.
* 1 - Warning
* 2+ - Error

Typically for an error your script should just use the exit code '2', but you
may use any other non-0, non-1 exit code if you want to write a custom handler
to perform special logic.

Advanced Checks
===============
You may also write checks in pure python instead of YAML. This is slightly less
pretty, but allows you to heavily customize the handler behavior. Here is the
same simple health check from before re-written in python.

/etc/steward/checks/up.py::

    from steward_palantir.check import Check

    class HealthCheck(Check):
        def __init__(self):
            super(HealthCheck, self).__init__(
                'health',
                {'cmd': '/bin/true'},
                {'minutes': 1},
                target='*',
                handlers=(
                    {'log': None},
                ),
            )

Pretty much the same as before. Except you can override methods to do some
nifty tricks. For example, here's the same check, but it has a special set of
handlers that only run when a user manually marks an alert as resolved.

/etc/steward/checks/up.py::

    from steward_palantir.check import Check

    class HealthCheck(Check):
        def __init__(self):
            super(HealthCheck, self).__init__(
                'health',
                {'cmd': '/bin/true'},
                {'minutes': 1},
                target='*',
            )
            self.mark_resolved_handlers = (
                {'log': None},
            )

    def _get_handlers(self, request, action, normalized_retcode, results,
                     **kwargs):
        """ Get the list of handlers to run. Useful to override """
        if action == 'resolve' and kwargs.get('marked_resolved'):
            return self.marked_resolved_handlers
        else:
            return super(HealthCheck, self)._get_handlers(request, action,
                normalized_retcode, results, **kwargs)

Handlers
========
Handlers are functions that are run on the result of a check to do alerting,
logging, filtering, or any other processing. A good place to start for
reference is the built-in handlers in ``steward_palantir.handlers``.

Any handlers you write must subclass ``steward_palantir.handlers.BaseHandler``.

Handlers may mutate check results and/or prevent successive handlers from being
run. This technique can be used, for example, to require multiple failed checks
before raising an alert. See the documentation on
``steward_palantir.handlers.BaseHandler`` for details.
