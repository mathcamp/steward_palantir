Steward Palantir
================
Palantir is a Steward extension for monitoring.

Setup
=====
To use steward_palantir, just add it to your includes either programmatically::

    config.include('steward_palantir')

or in the config.ini file::

    pyramid.includes = steward_palantir

Make sure you include it in the client config file as well.

Quick Start
===========
First thing you need to do is add a storage backend to your paste config.ini file::

    # Do not use 'memory' for production! This is for demonstration purposes only
    palantir.storage = memory

Now add a check to the checks directory

/etc/steward/checks/up.yaml::

    up:
      target: "*"
      command:
        cmd: /bin/true

      handlers:
        - log:
            log_success: true
        - alert:

      schedule:
        minutes: 1

Now start the server. You will see log entries for the results of the checks
(make sure your logging is configured and will log 'INFO' level).

That's it! You now have a working health check for all your minions! See below
for more advanced usage, such as pipelining handlers and customizing checks.

Configuration
=============
::

    # Persistence backend. Dotted path to an implementation of
    # steward_palantir.storage.IStorage. Required. Default values available are
    # 'memory' and 'sqlitedict'.
    palantir.storage = sqlitedict

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
        - log:
        - alert:

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
* **minion** - The name of the minion
* **check** - The Check object that was performed
* **status** - The response dict from running the command (contains stdout, stderr, and retcode)
* **last_retcode** - The retcode of the check the last time this handler was run

In addition, your custom handler may also specify any number of keyword
arguments. Those are the values filled in by the ``handlers`` section of the
check file.

Handlers may mutate the ``status`` object, which will change the value
passed to successive handlers. If a handler returns ``True``, it will stop
running handlers. Any successive handlers will not be run.

Alerts
======
An alert is just an indicator that something is going wrong. Alerts are managed
with the ``steward_palantir.handlers.alert`` handler. It's a useful way to
mark checks as failing or not.

When the ``alert`` handler runs, it will create an alert if the check status
has just changed to a nonzero exit code, and it will resolve alerts if the
check status has just changed back to 0. When alerts are created or resolve,
Palantir fires out a Steward event named either 'palantir/alert/create' or
'palantir/alert/resolve'.

There are a few useful API methods for viewing and manipulating alerts.

Misc
====
When you remove minions, you should call the `delete` endpoint so Palantir can
remove that minion's data from the database.
