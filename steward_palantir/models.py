""" SQLAlchemy models """
from datetime import datetime
from sqlalchemy import Column, Integer, DateTime, UnicodeText, Boolean

from steward_sqlalchemy import declarative_base


Base = declarative_base() # pylint: disable=C0103

class CheckDisabled(Base):
    """
    Mark a check as disabled

    Parameters
    ----------
    name : str
        Name of the check

    Attributes
    ----------
    name : str

    """
    __tablename__ = 'palantir_disabled_checks'
    name = Column(UnicodeText(), primary_key=True)

    def __init__(self, name):
        self.name = name


class MinionDisabled(Base):
    """
    Mark a minion as disabled

    Parameters
    ----------
    name : str
        Name of the minion

    Attributes
    ----------
    name : str

    """
    __tablename__ = 'palantir_disabled_minions'
    name = Column(UnicodeText(), primary_key=True)

    def __init__(self, name):
        self.name = name


class Alert(Base):
    """
    A check result that has caused an alert

    Parameters
    ----------
    minion : str
        Name of the minion
    check : str
        Name of the check
    stdout : str
    stderr : str
    retcode : int

    Attributes
    ----------
    minion : str
    check : str
    stdout : str
    stderr : str
    retcode : int
    created : :class:`datetime.datetime`
        The time at which this alert was raised

    """
    __tablename__ = 'palantir_alerts'
    id = Column(Integer(), primary_key=True)
    minion = Column(UnicodeText(), nullable=False, index=True)
    check = Column(UnicodeText(), nullable=False, index=True)
    stdout = Column(UnicodeText())
    stderr = Column(UnicodeText())
    retcode = Column(Integer())
    created = Column(DateTime())

    def __init__(self, minion, check, stdout, stderr, retcode):
        self.minion = minion
        self.check = check
        self.stdout = stdout
        self.stderr = stderr
        self.retcode = retcode
        self.created = datetime.now()

    @classmethod
    def from_result(cls, result):
        """ Create an Alert from a CheckResult """
        return cls(result.minion, result.check, result.stdout, result.stderr,
                   result.retcode)

    def __json__(self, request):
        return {
            'minion': self.minion,
            'check': self.check,
            'stdout': self.stdout,
            'stderr': self.stderr,
            'retcode': self.retcode,
            'created': float(self.created.strftime('%s.%f')),
        }


class CheckResult(Base):
    """
    The results of running a check on a minion

    Parameters
    ----------
    minion : str
        Name of the minion
    check : str
        Name of the check

    Attributes
    ----------
    minion : str
    check : str
    stdout : str
    stderr : str
    retcode : int
    last_run : :class:`datetime.datetime`
        The time at which this check was last run
    count : int
        How many times this check has return ``retcode``
    alert : int
        Alert status (0 - success, 1 - warning, 2 - error)
    enabled : bool

    """
    __tablename__ = 'palantir_check_results'
    id = Column(Integer(), primary_key=True)
    minion = Column(UnicodeText(), nullable=False, index=True)
    check = Column(UnicodeText(), nullable=False, index=True)
    stdout = Column(UnicodeText())
    stderr = Column(UnicodeText())
    retcode = Column(Integer())
    last_run = Column(DateTime())
    count = Column(Integer(), nullable=False)
    alert = Column(Integer(), index=True)
    enabled = Column(Boolean(), nullable=False)

    def __init__(self, minion, check):
        self.minion = minion
        self.check = check
        self.count = 1
        self.enabled = True
        self.alert = 0

    def __json__(self, request):
        return {
            'minion': self.minion,
            'check': self.check,
            'stdout': self.stdout,
            'stderr': self.stderr,
            'retcode': self.retcode,
            'last_run': float(self.last_run.strftime('%s.%f')),
            'count': self.count,
            'alert': self.alert,
            'enabled': self.enabled,
        }
