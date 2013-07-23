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

    # Dictionary mapping handler names to dotted paths of a handler function.
    # Optional. See steward_palantir.handlers for built-in handlers.
    palantir.handlers =
        absorb = steward_palantir.handlers.absorb

    # Directory containing handler aliases. Optional
    palantir.alias_dir = /etc/steward/aliases

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
* ``check`` - instance of ``steward_palantir.check.Check``

You can use this for contextual emails::

    raised:
      - mail:
          subject: "{{ result.check }} failed on {{ result.minion }}"
          body: |
            {{ result.check }} check failed on {{ result.minion }} with exit code {{ result.retcode }}
            STDOUT:
            {{ result.stdout }}
            STDERR:
            {{ result.stderr }}

If you specify additional data in the check's 'meta' field, you can use that in
the formatting. It is highly recommended that you establish a good system of
metadata and enforce it with the 'required_meta' option mentioned above. For
example, doesn't this email look SO much better than the last one?

::

    raised:
      - mail:
          mail_to: "{{ check.meta.owners }}"
          subject: "{{ result.check }} failed on {{ result.minion }}"
          body: |
            {{ result.check }} check failed on {{ result.minion }} with exit code {{ result.retcode }}

            What this check does: {{ check.meta.description }}
            Possible causes for this error: {{ check.meta.causes }}

            STDOUT:
            {{ result.stdout }}
            STDERR:
            {{ result.stderr }}

Which one would you rather receive at 3am on a Saturday?

Aliases
-------
You may find yourself creating complex handler pipelines that you want to use
for more than one check. To keep yourself DRY, create an alias. The first thing
you have to do is set the alias_dir configuration value::

    palantir.alias_dir = /etc/steward/aliases

Now you need to put an alias into that directory::

    mailalert:
      kwargs:
        title: ALERT
      handlers:
        - log:
        - mail:
          subject: "[{{ title }}] {{ minion }} {{ check.name }} check"
          body: "{{ minion }} {{ check.name }} has status {{ status['retcode'] }}"

Now you can refer to your new alias inside of a check::

    healthcheck:
      target: "*"
      timeout: 10
      command:
        cmd: /bin/true
        timeout: 1

      raised:
        - mailalert:
          title: ALERT

      resolved:
        - mailalert:
          title: RESOLVED

      schedule:
        seconds: 30

Note that the alias system is useful, but not super flexible. For example, it
can't conditionally re-arrange the order of its handlers based on parameters.
It also can't template non-string arguments. If you need these, or other
complex behaviors, you should just write a custom handler.

Misc
====
**Disabling checks/minions**

You can disable checks, minions, or individual checks for a specific minion.
Disabling a check is straightforward: the check will not run. Disabling a
minion or a check on a minion has two possible outcomes.

1. If a check targets a minion using the 'glob', 'list', or 'pcre' expr_forms, it will never be run on the minion.
2. If a check targets a minion with a different expr_form, the check will still run, but the handlers will not. Meaning no alerts will be raised.

This is due to a limitation with salt (it does not expose the matching algorithms).
