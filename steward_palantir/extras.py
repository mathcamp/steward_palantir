""" Extra handlers """
from .handlers import BaseHandler


class TwilioHandler(BaseHandler):

    """
    Check handler that sends SMS via twilio

    Requires that the twilio client be installed ("pip install twilio")

    Parameters
    ----------
    to : str or list
        The number or list of numbers to send the SMS to.
    body : str
        The message body. Will be truncated at 160 chars.
    sid : str, optional
        The account SID (may be specified in config.ini as palantir.twilio.sid)
    token : str, optional
        The auth token (may be specified in config.ini as palantir.twilio.token)
    from_num : str, optional
        The phone number to send the SMS from (may be specified in config.ini
        as palantir.twilio.from_num)

    """
    name = 'twilio'

    def __init__(self, to=(), body="", sid=None, token=None, from_num=None):
        if isinstance(to, basestring):
            self.to = [num.strip() for num in to.split(',')]
        else:
            self.to = to
        if len(body) > 160:
            self.body = self.body[:159] + u'\u2026'
        else:
            self.body = body
        self.sid = sid
        self.token = token
        self.from_num = from_num

    def __call__(self, request, check, normalized_retcode, results, **kwargs):
        token = request.registry.settings.get('palantir.twilio.token',
                                              self.token)
        sid = request.registry.settings.get('palantir.twilio.sid', self.sid)
        from_num = request.registry.settings.get('palantir.twilio.from_num',
                                                 self.from_num)

        from twilio.rest import TwilioRestClient
        client = TwilioRestClient(sid, token)

        for to_num in self.to:
            client.sms.messages.create(
                body=self.body,
                to=to_num,
                from_=from_num)