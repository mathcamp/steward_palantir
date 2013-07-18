""" Storage interfaces for steward_palantir """

class IStorage(object):
    """
    Storage interface for steward_palantir

    Provides an abstraction layer on top of whatever storage backend is
    available

    """
    def __init__(self, request):
        self.request = request

    def add_check_result(self, minion, check, retcode, stdout, stderr, ts):
        """
        Add a check result to the history for a minion

        Parameters
        ----------
        minion : str
            Name of the minion
        check : str
            Name of the check
        retcode : int
            Return code of the check
        stdout : str
            The stdout of the check
        stderr : str
            The stderr of the check
        ts : float
            The unix timestamp when the check was run

        Returns
        -------
        status : dict
            The same return value as check_status

        """
        raise NotImplementedError

    def get_alerts(self):
        """
        Get a list of alerts

        Returns
        -------
        alerts : list
            List of tuples of (minion, check)

        """
        raise NotImplementedError

    def last_retcode(self, minion, check, handler_id):
        """
        Get the last retcode that a handler saw for a unique minion, check pair

        Parameters
        ----------
        minion : str
            Name of the minion
        check : str
            Name of the check
        handler_id : str
            Unique id for a handler in a check

        Returns
        -------
        retcode : int

        """
        raise NotImplementedError

    def set_last_retcode(self, minion, check, handler_id, retcode):
        """
        Set the last retcode that a handler saw for a unique minion, check pair

        Parameters
        ----------
        minion : str
            Name of the minion
        check : str
            Name of the check
        handler_id : str
            Unique id for a handler in a check
        retcode : int
            The return code that was last seen by the handler

        """
        raise NotImplementedError

    def clear_last_retcode(self, minion, check):
        """
        Clear the last retcode for all handlers of a check

        Parameters
        ----------
        minion : str
            Name of the minion
        check : str
            Name of the check

        """
        raise NotImplementedError

    def add_alert(self, minion, check):
        """
        Mark a check as failing

        Parameters
        ----------
        minion : str
            Name of the minion
        check : str
            Name of the check

        """
        raise NotImplementedError

    def remove_alert(self, minion, check):
        """
        Mark a check as no longer failing

        Parameters
        ----------
        minion : str
            Name of the minion
        check : str
            Name of the check

        """
        raise NotImplementedError

    def reset_check(self, minion, check):
        """
        Reset the status of a check

        This should essentially delete all history and current status

        Parameters
        ----------
        minion : str
            Name of the minion
        check : str
            Name of the check

        """
        raise NotImplementedError

    def minion_checks(self, minion):
        """
        Get a list of all the checks that have run on the minion

        Parameters
        ----------
        minion : str
            Namem of the minion

        Returns
        -------
        checks : dict
            Dict that maps check name to the data dict returned by
            ``check_status``.

        """
        raise NotImplementedError

    def check_status(self, minion, check):
        """
        Get the stored check data for a minion

        Parameters
        ----------
        minion : str
            Name of the minion
        check : str
            Name of the check

        Returns
        -------
        retcode : int
            Current check status
        count : int
            Number of times the current retcode has been returned
        previous : int
            Previous retcode
        stdout : str
            The stdout from the last check
        stderr : str
            The stderr from the last check
        ts : float
            The unix timestamp when the check was run

        Notes
        -----
        Return value is a dict. Will return None if the check has not run yet.

        """
        raise NotImplementedError

    def delete_minion(self, minion):
        """
        Delete a minion from the database

        Parameters
        ----------
        minion : str
            Name of the minion

        """
        raise NotImplementedError

    def set_minion_enabled(self, minion, enabled):
        """
        Mark a minion as enabled or disabled

        Parameters
        ----------
        minion : str
        enabled : bool

        """
        raise NotImplementedError

    def set_check_enabled(self, check, enabled):
        """
        Mark a check as enabled or disabled

        Parameters
        ----------
        check : str
        enabled : bool

        """
        raise NotImplementedError

    def set_minion_check_enabled(self, minion, check, enabled):
        """
        Mark a check as enabled or disabled on a specific minion

        Parameters
        ----------
        minion : str
        check : str
        enabled : bool

        """
        raise NotImplementedError

    def is_minion_enabled(self, minion):
        """
        See if a minion is enabled or not

        Parameters
        ----------
        minion : str

        Returns
        -------
        enabled : bool

        """
        raise NotImplementedError

    def is_check_enabled(self, check):
        """
        See if a check is enabled or not

        Parameters
        ----------
        check : str

        Returns
        -------
        enabled : bool

        """
        raise NotImplementedError

    def is_minion_check_enabled(self, minion, check):
        """
        See if a check is enabled or not on a specific minion

        Parameters
        ----------
        minion : str
        check : str

        Returns
        -------
        enabled : bool

        """
        raise NotImplementedError

    def set_minions(self, minions):
        """
        Store the list of all minions

        Parameters
        ----------
        minions : list

        """
        raise NotImplementedError

    def get_minions(self):
        """
        Get the list of all minions

        Returns
        -------
        minions : list
            If ``set_minions`` has not been called, return an empty list

        """
        raise NotImplementedError

class IDictStorage(IStorage):
    """ Extension of IStorage that is backed by a dict """
    db = None

    def _add_minion_key(self, minion, key):
        """ Keep track of all keys belonging to a minion """
        keys = self.db.get(minion + '_keys', [])
        keys.append(key)
        self.db[minion + '_keys'] = keys

    def add_check_result(self, minion, check, retcode, stdout, stderr, ts):
        minion_check = minion + '_' + check
        if minion_check not in self.db:
            self._add_minion_key(minion, minion_check)

        checks = self.db.get(minion + '_checks', [])
        if check not in checks:
            checks.append(check)
        self.db[minion + '_checks'] = checks

        result = self.db.get(minion_check, {'retcode':0, 'count':0,
                                            'previous':0})

        if result['retcode'] == retcode:
            result['count'] += 1
        else:
            result['previous'] = result['retcode']
            result['retcode'] = retcode
            result['count'] = 1


        result['stdout'] = stdout
        result['stderr'] = stderr
        result['ts'] = ts
        self.db[minion_check] = result
        return result

    def last_retcode(self, minion, check, handler_id):
        return self.db.get('_'.join([minion, check, handler_id]), 0)

    def set_last_retcode(self, minion, check, handler_id, retcode):
        key = '_'.join([minion, check, handler_id])
        self.db[key] = retcode
        self._add_minion_key(minion, key)
        retcode_key = minion + '_' + check + '_retcode'
        last_retcodes = self.db.get(retcode_key, [])
        last_retcodes.append(key)
        self.db[retcode_key] = last_retcodes
        self._add_minion_key(minion, retcode_key)

    def clear_last_retcode(self, minion, check):
        retcode_key = minion + '_' + check + '_retcode'
        for key in self.db.get(retcode_key, []):
            if key in self.db:
                del self.db[key]
        self.db[retcode_key] = []

    def get_alerts(self):
        return self.db.get('alerts', [])

    def add_alert(self, minion, check):
        alerts = self.db.get('alerts', [])
        alerts.append((minion, check))
        self.db['alerts'] = alerts

    def remove_alert(self, minion, check):
        alerts = self.db.get('alerts', [])
        alerts.remove((minion, check))
        self.db['alerts'] = alerts

    def reset_check(self, minion, check):
        key = minion + '_' + check
        if key in self.db:
            del self.db[key]

    def minion_checks(self, minion):
        result = {}
        for check in self.db.get(minion + '_checks', []):
            result[check] = self.check_status(minion, check)
        return result

    def check_status(self, minion, check):
        return self.db.get(minion + '_' + check)

    def delete_minion(self, minion):
        for key in self.db.get(minion + '_keys'):
            if key in self.db:
                del self.db[key]
        del self.db[minion + '_keys']

        if minion + '_checks' in self.db:
            del self.db[minion + '_checks']

        alerts = self.db.get('alerts', [])
        index = 0
        while index < len(alerts):
            if minion == alerts[index][0]:
                del alerts[index]
                continue
            index += 1
        self.db['alerts'] = alerts

    def set_minion_enabled(self, minion, enabled):
        key = 'minion:' + minion + ':enabled'
        self.db[key] = enabled
        self._add_minion_key(minion, key)

    def set_check_enabled(self, check, enabled):
        key = 'check:' + check + ':enabled'
        self.db[key] = enabled

    def set_minion_check_enabled(self, minion, check, enabled):
        key = 'minion:' + minion + ':' + check + ':enabled'
        self.db[key] = enabled
        self._add_minion_key(minion, key)

    def is_minion_enabled(self, minion):
        return self.db.get('minion:' + minion + ':enabled', True)

    def is_check_enabled(self, check):
        return self.db.get('check:' + check + ':enabled', True)

    def is_minion_check_enabled(self, minion, check):
        return self.db.get('minion:' + minion + ':' + check + ':enabled', True)

    def set_minions(self, minions):
        self.db['all_minions'] = minions

    def get_minions(self):
        return self.db.get('all_minions', [])

class MemoryStorage(IDictStorage):
    """
    Simple in-memory storage

    Notes
    =====
    This is suitable for testing only

    .. warning::
        If your server spawns multiple threads and/or processes, this storage
        backend will not work properly and you will be a sad panda.

    """
    @property
    def db(self):
        """ Accessor for in-memory dict """
        if not hasattr(self.request.registry, 'palantir_storage_impl'):
            self.request.registry.palantir_storage_impl = {}
        return self.request.registry.palantir_storage_impl


class SqliteDictStorage(IDictStorage):
    """
    Storage system using steward_sqlitedict

    Notes
    =====
    .. warning::
        There are known race conditions in this storage backend. Data integrity
        is not *super* important, so it can still operate reasonably well, but
        be aware that it's not perfect.

    """
    @property
    def db(self):
        """ Accessor for sqlitedict """
        return self.request.sqld('palantir')
