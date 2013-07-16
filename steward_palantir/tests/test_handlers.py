""" Test handlers """
from unittest import TestCase
from pyramid.testing import DummyRequest
from ..handlers import absorb, fork
from ..check import Check
from mock import MagicMock, ANY

def status(retcode=0, count=1, previous=0, stdout='', stderr=''):
    """ Convenience method for creating a status """
    return {'retcode': retcode,
            'count': count,
            'previous': previous,
            'stdout': stdout,
            'stderr': stderr}

class HandlerTest(TestCase):
    """ Base class for handler tests """
    def setUp(self):
        super(HandlerTest, self).setUp()
        self.request = DummyRequest()
        self.db = self.request.palantir_db = MagicMock()
        self.check = Check('testcheck', {'target':'', 'command':'',
                                         'schedule':None ,'handlers':[]})

class TestFork(HandlerTest):
    """ Test the fork handler """
    def setUp(self):
        super(TestFork, self).setUp()
        self.h1 = MagicMock()
        self.h2 = MagicMock()
        self.request.registry.palantir_handlers = {'handler1': self.h1,
                                                   'handler2': self.h2}
        self.handlers = [{'handler1':None}, {'handler2':None}]


    def test_handler_sequence(self):
        """ Fork runs all the handlers in sequence """
        fork(self.request, None, self.check, status(), '',
             handlers=self.handlers)
        self.assertTrue(self.h1.called)
        self.assertTrue(self.h2.called)

    def test_handler_stop_propagation(self):
        """ If a handler returns True, fork doesn't run successive handlers """
        self.h1.return_value = True
        fork(self.request, None, self.check, status(), '',
             handlers=self.handlers)
        self.assertTrue(self.h1.called)
        self.assertFalse(self.h2.called)

    def test_handler_error_stop_propagation(self):
        """ If a handler raises an exception, successive handlers don't run """
        def bomb():
            """ drop the bombshell """
            raise Exception()
        self.h1.side_effect = bomb
        fork(self.request, None, self.check, status(), '',
             handlers=self.handlers)
        self.assertTrue(self.h1.called)
        self.assertFalse(self.h2.called)

    def test_update_last_retcode(self):
        """ Fork updates the last_retcode after running a handler """
        self.h1.return_value = True
        fork(self.request, None, self.check, status(), '',
             handlers=self.handlers)
        self.assertTrue(self.db.set_last_retcode.call_count, 1)

    def test_render(self):
        """ Fork renders keyword arguments to handlers using jinja2 """
        self.handlers = [{'handler1':{
            'minion':'{{ minion }}',
            'check':'{{ check }}',
            'status':'{{ status }}',
        }
        }]
        minion = None
        check = self.check
        stat = status()
        fork(self.request, minion, check, stat, '', handlers=self.handlers)
        self.h1.assert_called_once_with(self.request, minion, check, stat, ANY,
                                        minion=str(minion), status=str(stat),
                                        check=str(check))


class TestAbsorb(HandlerTest):
    """ Test the absorb handler """
    # success
    def test_absorb_success(self):
        """ If success=True, absorb a successful check """
        result = absorb(self.request, None, self.check, status(), '',
                        success=True)
        self.assertTrue(result)

    def test_not_absorb_not_success(self):
        """ If success=True, don't absorb fail checks """
        result = absorb(self.request, None, self.check, status(1), '',
                        success=True)
        self.assertFalse(result)

    def test_not_absorb_success(self):
        """ If success=False, don't absorb even if other rules apply """
        result = absorb(self.request, None, self.check, status(0), '',
                        success=False, success_count=2)
        self.assertFalse(result)

    def test_absorb_not_success(self):
        """ If success=False, okay to absorb fail checks """
        result = absorb(self.request, None, self.check, status(1), '',
                        success=False, count=2)
        self.assertTrue(result)

    # warn
    def test_absorb_warn(self):
        """ If warn=True, absorb a warn result """
        result = absorb(self.request, None, self.check, status(1), '',
                        warn=True)
        self.assertTrue(result)

    def test_not_absorb_warn_error(self):
        """ If warn=True, don't absorb fail checks """
        result = absorb(self.request, None, self.check, status(2), '',
                        warn=True)
        self.assertFalse(result)

    def test_not_absorb_warn_success(self):
        """ If warn=True, don't absorb fail checks """
        result = absorb(self.request, None, self.check, status(0), '',
                        warn=True)
        self.assertFalse(result)

    def test_not_absorb_warn(self):
        """ If warn=False, don't absorb even if other rules apply """
        result = absorb(self.request, None, self.check, status(1), '',
                        warn=False, count=2)
        self.assertFalse(result)

    def test_absorb_not_warn(self):
        """ If warn=False, okay to absorb error checks """
        result = absorb(self.request, None, self.check, status(2), '',
                        warn=False, count=2)
        self.assertTrue(result)

    # error
    def test_absorb_error(self):
        """ If error=True, absorb a error result """
        result = absorb(self.request, None, self.check, status(2), '',
                        error=True)
        self.assertTrue(result)

    def test_not_absorb_error_error(self):
        """ If error=True, don't absorb success checks """
        result = absorb(self.request, None, self.check, status(0), '',
                        error=True)
        self.assertFalse(result)

    def test_not_absorb_error_success(self):
        """ If error=True, don't absorb warn checks """
        result = absorb(self.request, None, self.check, status(1), '',
                        error=True)
        self.assertFalse(result)

    def test_not_absorb_error(self):
        """ If error=False, don't absorb even if other rules apply """
        result = absorb(self.request, None, self.check, status(2), '',
                        error=False, count=2)
        self.assertFalse(result)

    def test_absorb_not_error(self):
        """ If error=False, okay to absorb warn checks """
        result = absorb(self.request, None, self.check, status(1), '',
                        error=False, count=2)
        self.assertTrue(result)

    # only_change
    def test_only_change(self):
        """ If only_change=True, absorb when no change occurs """
        self.db.last_retcode.return_value = 0
        result = absorb(self.request, None, self.check, status(0), '',
                        only_change=True)
        self.assertTrue(result)

    def test_not_only_change(self):
        """ If only_change=True, don't absorb when there is a change """
        self.db.last_retcode.return_value = 1
        result = absorb(self.request, None, self.check, status(0), '',
                        only_change=True)
        self.assertFalse(result)

    # only_change_status
    def test_only_change_status(self):
        """ If only_change_status=True, absorb error-to-error """
        self.db.last_retcode.return_value = 3
        result = absorb(self.request, None, self.check, status(8), '',
                        only_change_status=True)
        self.assertTrue(result)

    def test_not_only_change_status(self):
        """ If only_change_status=True, don't absorb when there is a change """
        self.db.last_retcode.return_value = 5
        result = absorb(self.request, None, self.check, status(1), '',
                        only_change=True)
        self.assertFalse(result)

    # count
    def test_count(self):
        """ If status['count'] < count, absorb """
        result = absorb(self.request, None, self.check, status(2), '',
                        count=2)
        self.assertTrue(result)

    def test_exceed_count(self):
        """ If status['count'] >= count, don't absorb """
        result = absorb(self.request, None, self.check, status(2, 2), '',
                        count=2)
        self.assertFalse(result)

    def test_count_not_success(self):
        """ Count should not absorb success checks """
        result = absorb(self.request, None, self.check, status(0), '',
                        count=2)
        self.assertFalse(result)

    # success_count
    def test_success_count(self):
        """ If status['count'] < success_count on success check, absorb """
        result = absorb(self.request, None, self.check, status(0), '',
                        success_count=2)
        self.assertTrue(result)

    def test_exceed_success_count(self):
        """ If status['count'] >= success_count, don't absorb """
        result = absorb(self.request, None, self.check, status(0, 2), '',
                        success_count=2)
        self.assertFalse(result)

    def test_success_count_not_error(self):
        """ success_count should not absorb fail checks """
        result = absorb(self.request, None, self.check, status(2), '',
                        success_count=2)
        self.assertFalse(result)

    def test_retcode_match_int(self):
        """ absorb events that match a single int in retcode """
        result = absorb(self.request, None, self.check, status(2), '',
                        retcodes=2)
        self.assertTrue(result)

    def test_retcode_match_list(self):
        """ absorb events that match an int list in retcode """
        result = absorb(self.request, None, self.check, status(2), '',
                        retcodes='1,2')
        self.assertTrue(result)

    def test_retcode_match_range(self):
        """ absorb events that match an int range in retcode """
        result = absorb(self.request, None, self.check, status(4), '',
                        retcodes='1-4,10-17')
        self.assertTrue(result)

    def test_retcode_match_open_range(self):
        """ absorb events that match an open-ended range in retcode """
        result = absorb(self.request, None, self.check, status(10), '',
                        retcodes='1-4,6-')
        self.assertTrue(result)

    def test_out_match(self):
        """ if out_match matches stdout, absorb """
        result = absorb(self.request, None, self.check, status(0), '',
                        out_match='.*')
        self.assertTrue(result)

    def test_out_not_match(self):
        """ if out_match doesn't match stdout, don't absorb """
        result = absorb(self.request, None, self.check, status(0), '',
                        out_match='not matching')
        self.assertFalse(result)

    def test_err_match(self):
        """ if err_match matches stderr, absorb """
        result = absorb(self.request, None, self.check, status(0), '',
                        err_match='.*')
        self.assertTrue(result)

    def test_err_not_match(self):
        """ if err_match doesn't match stderr, don't absorb """
        result = absorb(self.request, None, self.check, status(0), '',
                        err_match='not matching')
        self.assertFalse(result)

    def test_out_err_match_out(self):
        """ if out_err_match matches stdout, absorb """
        result = absorb(self.request, None, self.check, status(0, stdout='out',
                                                               stderr='err'),
                        '', out_err_match='ou.')
        self.assertTrue(result)

    def test_out_err_match_err(self):
        """ if out_err_match matches stderr, absorb """
        result = absorb(self.request, None, self.check, status(0, stdout='out',
                                                               stderr='err'),
                        '', out_err_match='er.')
        self.assertTrue(result)

    def test_out_err_not_match(self):
        """ if out_err_match doesn't match stdout or stderr, don't absorb """
        result = absorb(self.request, None, self.check, status(0), '',
                        out_match='not matching')
        self.assertFalse(result)
