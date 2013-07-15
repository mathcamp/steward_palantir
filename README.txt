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

Usage
=====
* TODO: writing checks
* TODO: writing handlers
* TODO: setting up checks & handlers
* TODO: operation (what happens when an alert is triggered, etc)


Configuration
=============
* **palantir.checks_dir** - Directory containing the checks (default /etc/steward/checks)
* **palantir.handlers** - Dictionary of handler names to dotted paths
* **palantir.storage** - Persistence backend. May be 'memory', 'sqlitedict', or a dotted path.

Permissions
===========
* **palantir.perm.palantir_read** - Allows users to see server & check data
* **palantir.perm.palantir_write** - Allows users to remove minions, run checks, etc.
