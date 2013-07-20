Steward Palantir
================
Palantir is a Steward extension for monitoring.

Setup
=====
Steward_palantir depends on steward_sqlalchemy. To use steward_palantir, just
add it to your includes either programmatically::

    config.include('pyramid_tm')
    config.include('steward_sqlalchemy')
    config.include('steward_palantir')

or in the config.ini file::

    pyramid.includes = 
        pyramid_tm
        steward_sqlalchemy
        steward_palantir

Make sure you include it in the client config file as well.

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

Now start the server. You will see log entries for the results of the checks
(make sure your logging is configured and will log 'INFO' level).

That's it! You now have a working health check for all your minions!

Configuration
=============
::

    # Directory containing the checks. Optional. Default /etc/steward/checks
    palantir.checks_dir = /etc/steward/checks

    # Dictionary mapping handler names to dotted paths of a handler function.
    # Optional. See steward_palantir.handlers for built-in handlers.
    palantir.handlers =
        absorb = steward_palantir.handlers.absorb

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

      # The salt target to run the check on
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
        microseconds: 88

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

Handlers
========
Handlers are functions that are run on the result of a check to do alerting,
logging, filtering, or any other processing. A good place to start for
reference is the built-in handlers in ``steward_palantir.handlers``. All
handlers must take the following arguments:

* **request** - The pyramid Request object
* **result** - The ``steward_palantir.models.CheckResult`` object for the check

In addition, your custom handler may also specify any number of keyword
arguments. Those are the values filled in by the ``handlers`` section of the
check file.

If a handler returns ``True``, it will stop running handlers. Any successive
handlers will not be run. This technique can be used, for example, to require
multiple failed checks before raising an alert.

Handler Templating
------------------
If you pass in an argument to a handler as a string, you may render it using
the jinja templating syntax. The available variables are:

* ``result`` - instance of ``steward_palantir.models.CheckResult``

You can use this for contextual emails::

    handlers:
      - absorb:
          success: true
      - mail:
          subject: {{ result.check }} failed on {{ result.minion }}
          body: |
            {{ result.check }} check failed on {{ result.minion }} with exit code {{ result.retcode }}
            STDOUT:
            {{ result.stdout }}
            STDERR:
            {{ result.stderr }}

Misc
====
**Disabling checks/minions**

You can disable checks, minions, or individual checks for a specific minion.
Disabling a check is straightforward: the check will not run. Disabling a
minion or a check on a minion has two possible outcomes.

1. If a check targets a minion using the 'glob', 'list', or 'pcre' expr_forms, it will never be run on the minion.
2. If a check targets a minion with a different expr_form, the check will still run, but the handlers will not. Meaning no alerts will be raised.

This is due to a limitation with salt (it does not expose the matching algorithms).
