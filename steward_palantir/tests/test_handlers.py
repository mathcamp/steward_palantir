""" Test handlers """
from mock import MagicMock
from pyramid.testing import DummyRequest
from unittest import TestCase

from ..check import Check
from ..handlers import absorb
from ..models import CheckResult


class HandlerTest(TestCase):
    """ Base class for handler tests """
    def setUp(self):
        super(HandlerTest, self).setUp()
        self.request = DummyRequest()
        self.db = self.request.palantir_db = MagicMock()
        self.check = Check('testcheck', {'target':'', 'command':'',
                                         'schedule':None ,'handlers':[]})

    def result(self, retcode=0, count=1, stdout='', stderr=''):
        """ Convenience method for creating a result """
        result = CheckResult('', self.check)
        result.retcode = retcode
        result.count = count
        result.stdout = stdout
        result.stderr = stderr
        return result

class TestAbsorb(HandlerTest):
    """ Test the absorb handler """
    # success
    def test_absorb_success(self):
        """ If success=True, absorb a successful check """
        result = absorb(self.request, self.result(), success=True)
        self.assertTrue(result)

    def test_not_absorb_not_success(self):
        """ If success=True, don't absorb fail checks """
        result = absorb(self.request, self.result(1), success=True)
        self.assertFalse(result)

    def test_not_absorb_success(self):
        """ If success=False, don't absorb even if other rules apply """
        result = absorb(self.request, self.result(0), success=False,
                        success_count=2)
        self.assertFalse(result)

    def test_absorb_not_success(self):
        """ If success=False, okay to absorb fail checks """
        result = absorb(self.request, self.result(1), success=False, count=2)
        self.assertTrue(result)

    # warn
    def test_absorb_warn(self):
        """ If warn=True, absorb a warn result """
        result = absorb(self.request, self.result(1), warn=True)
        self.assertTrue(result)

    def test_not_absorb_warn_error(self):
        """ If warn=True, don't absorb fail checks """
        result = absorb(self.request, self.result(2), warn=True)
        self.assertFalse(result)

    def test_not_absorb_warn_success(self):
        """ If warn=True, don't absorb fail checks """
        result = absorb(self.request, self.result(0), warn=True)
        self.assertFalse(result)

    def test_not_absorb_warn(self):
        """ If warn=False, don't absorb even if other rules apply """
        result = absorb(self.request, self.result(1), warn=False, count=2)
        self.assertFalse(result)

    def test_absorb_not_warn(self):
        """ If warn=False, okay to absorb error checks """
        result = absorb(self.request, self.result(2), warn=False, count=2)
        self.assertTrue(result)

    # error
    def test_absorb_error(self):
        """ If error=True, absorb a error result """
        result = absorb(self.request, self.result(2), error=True)
        self.assertTrue(result)

    def test_not_absorb_error_error(self):
        """ If error=True, don't absorb success checks """
        result = absorb(self.request, self.result(0), error=True)
        self.assertFalse(result)

    def test_not_absorb_error_success(self):
        """ If error=True, don't absorb warn checks """
        result = absorb(self.request, self.result(1), error=True)
        self.assertFalse(result)

    def test_not_absorb_error(self):
        """ If error=False, don't absorb even if other rules apply """
        result = absorb(self.request, self.result(2), error=False, count=2)
        self.assertFalse(result)

    def test_absorb_not_error(self):
        """ If error=False, okay to absorb warn checks """
        result = absorb(self.request, self.result(1), error=False, count=2)
        self.assertTrue(result)

    # count
    def test_count(self):
        """ If result.count < count, absorb """
        result = absorb(self.request, self.result(2), count=2)
        self.assertTrue(result)

    def test_exceed_count(self):
        """ If result.count >= count, don't absorb """
        result = absorb(self.request, self.result(2, 2), count=2)
        self.assertFalse(result)

    def test_count_not_success(self):
        """ Count should not absorb success checks """
        result = absorb(self.request, self.result(0), count=2)
        self.assertFalse(result)

    # success_count
    def test_success_count(self):
        """ If result.count < success_count on success check, absorb """
        result = absorb(self.request, self.result(0), success_count=2)
        self.assertTrue(result)

    def test_exceed_success_count(self):
        """ If result.count >= success_count, don't absorb """
        result = absorb(self.request, self.result(0, 2), success_count=2)
        self.assertFalse(result)

    def test_success_count_not_error(self):
        """ success_count should not absorb fail checks """
        result = absorb(self.request, self.result(2), success_count=2)
        self.assertFalse(result)

    def test_retcode_match_int(self):
        """ absorb events that match a single int in retcode """
        result = absorb(self.request, self.result(2), retcodes=2)
        self.assertTrue(result)

    def test_retcode_match_list(self):
        """ absorb events that match an int list in retcode """
        result = absorb(self.request, self.result(2), retcodes='1,2')
        self.assertTrue(result)

    def test_retcode_match_range(self):
        """ absorb events that match an int range in retcode """
        result = absorb(self.request, self.result(4), retcodes='1-4,10-17')
        self.assertTrue(result)

    def test_retcode_match_open_range(self):
        """ absorb events that match an open-ended range in retcode """
        result = absorb(self.request, self.result(10), retcodes='1-4,6-')
        self.assertTrue(result)

    def test_out_match(self):
        """ if out_match matches stdout, absorb """
        result = absorb(self.request, self.result(0), out_match='.*')
        self.assertTrue(result)

    def test_out_not_match(self):
        """ if out_match doesn't match stdout, don't absorb """
        result = absorb(self.request, self.result(0), out_match='not matching')
        self.assertFalse(result)

    def test_err_match(self):
        """ if err_match matches stderr, absorb """
        result = absorb(self.request, self.result(0), err_match='.*')
        self.assertTrue(result)

    def test_err_not_match(self):
        """ if err_match doesn't match stderr, don't absorb """
        result = absorb(self.request, self.result(0), err_match='not matching')
        self.assertFalse(result)

    def test_out_err_match_out(self):
        """ if out_err_match matches stdout, absorb """
        result = absorb(self.request, self.result(0, stdout='out',
                                                  stderr='err'),
                        out_err_match='ou.')
        self.assertTrue(result)

    def test_out_err_match_err(self):
        """ if out_err_match matches stderr, absorb """
        result = absorb(self.request, self.result(0, stdout='out',
                                                  stderr='err'),
                        out_err_match='er.')
        self.assertTrue(result)

    def test_out_err_not_match(self):
        """ if out_err_match doesn't match stdout or stderr, don't absorb """
        result = absorb(self.request, self.result(0), out_match='not matching')
        self.assertFalse(result)
