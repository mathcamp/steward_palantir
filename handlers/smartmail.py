from steward_palantir.handlers import BaseHandler
from pyramid.security import unauthenticated_userid

class SmartMail(BaseHandler):
    """ A simple handler that sends pretty emails """
    name = 'smartmail'
    def __init__(self, mail_to):
        self.mail_to = mail_to

    def __call__(self, request, check, normalized_retcode, results, **kwargs):
        if normalized_retcode == 0:
            title = 'RESOLVED'
            action = 'succeeded'
        elif normalized_retcode == 1:
            title = 'WARNING'
            action = 'failed'
        else:
            title = 'ERROR'
            action = 'failed'

        if len(results) == 1:
            target = results[0].minion
        else:
            target = "%d minions" % len(results)

        subject = "[%s] %s on %s" % (title, check.name, target)

        if kwargs.get('marked_resolved'):
            minions = [result.minion for result in results]
            body = ("%s marked resolved by %s on %s" %
                    (check.name, unauthenticated_userid(request),
                     ', '.join(minions)))
        else:
            body = "%s %s on\n" % (check.name, action)
            for result in results:
                body += ("    %s %d time%s\n" % (result.minion, result.count,
                                                 's' if result.count > 1 else
                                                 ''))
                if result.stdout:
                    body += 'STDOUT:\n' + result.stdout
                if result.stderr:
                    body += 'STDERR:\n' + result.stderr

        request.subreq('mail', subject=subject, body=body, mail_to=self.mail_to)
