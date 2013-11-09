""" Palantir tasks """
import itertools
from datetime import datetime

import copy
from collections import defaultdict
from steward_salt.tasks import salt_match, salt, salt_key
from steward_tasks.tasks import pub

from .models import CheckDisabled, MinionDisabled, CheckResult, Alert
from steward_tasks import celery, StewardTask, lock


@celery.task(base=StewardTask)
def prune():
    """
    Remove minions that have been removed from salt

    Remove check results from checks that no longer exist

    """
    task = prune
    check_names = task.config.registry.palantir_checks
    task.db.query(CheckResult)\
        .filter(CheckResult.check.notin_(check_names))\
        .delete(synchronize_session=False)
    task.db.query(Alert)\
        .filter(Alert.check.notin_(check_names))\
        .delete(synchronize_session=False)

    minion_list = salt_key('list_keys')
    minions = set(minion_list)
    old_minions = set(itertools.chain.from_iterable(
        task.db.query(CheckResult.minion)
        .group_by(CheckResult.minion).all()))
    removed = old_minions - minions
    added = minions - old_minions
    if removed:
        task.db.query(MinionDisabled).filter(MinionDisabled.name.in_(removed))\
            .delete(synchronize_session=False)
        task.db.query(CheckResult).filter(CheckResult.minion.in_(removed))\
            .delete(synchronize_session=False)
        task.db.query(Alert).filter(Alert.minion.in_(removed))\
            .delete(synchronize_session=False)
    return {
        'removed': list(removed),
        'added': list(added),
    }


@celery.task(base=StewardTask)
def run_check(check_name):
    """ Run a palantir check """
    with lock.inline("palantir_check_%s" % check_name, expires=120, timeout=120):
        task = run_check

        if task.db.query(CheckDisabled).filter_by(name=check_name).first():
            return 'check disabled'

        check = task.config.registry.palantir_checks[check_name]

        def do_minion_check(minion, check):
            """ Should this check be run on this minion """
            if task.db.query(MinionDisabled).filter_by(name=minion).first():
                return False
            result = task.db.query(CheckResult).filter_by(minion=minion,
                                                          check=check).first()
            if result is not None and not result.enabled:
                return False
            return True

        expected_minions = salt_match(check.target, check.expr_form)
        i = 0
        while i < len(expected_minions):
            minion = expected_minions[i]
            if not do_minion_check(minion, check_name):
                del expected_minions[i]
                continue
            i += 1
        target = ','.join(expected_minions)
        expr_form = 'list'
        if len(expected_minions) == 0:
            return 'No minions matched'

        response = salt(target, 'cmd.run_all', kwarg=check.command,
                                expr_form=expr_form, timeout=check.timeout)

        combined_minions = set(expected_minions).union(set(response.keys()))

        # Process results for each minion
        check_results = {}
        changed_results = defaultdict(list)
        for minion in combined_minions:
            if not do_minion_check(minion, check_name):
                continue
            # Get the response. If no response, replace it with a 'salt timeout'
            # message
            result = response.get(minion, {
                'retcode': 1000,
                'stdout': '',
                'stderr': '<< SALT TIMED OUT >>',
            })

            check_result = task.db.query(CheckResult)\
                .filter_by(check=check_name, minion=minion).first()
            if check_result is None:
                check_result = CheckResult(minion, check.name)
                check_result.old_result = CheckResult(minion, check.name)
                task.db.add(check_result)
            else:
                check_result.old_result = copy.copy(check_result)
                if check_result.retcode == result['retcode']:
                    check_result.count += 1
                else:
                    check_result.count = 1
            check_result.stdout = result['stdout']
            check_result.stderr = result['stderr']
            check_result.retcode = result['retcode']
            check_result.last_run = datetime.now()

            handler_result = check.run_handler(task, check_result)

            if check_result.alert != check_result.normalized_retcode and \
                    handler_result is not True:
                changed_results[
                    check_result.normalized_retcode].append(check_result)

            check_results[minion] = check_result

        # Run all the event handlers
        for normalized_retcode, results in changed_results.iteritems():
            handle_results(task, check, normalized_retcode, results)
            for result in results:
                result.alert = result.normalized_retcode

        return check_results


def handle_results(task, check, normalized_retcode, results):
    """ Run the check handlers and raise/resolve alerts if necessary """
    minions = [result.minion for result in results]

    # delete any existing alerts
    task.db.query(Alert).filter(Alert.minion.in_(minions)).\
        filter_by(check=check.name).delete(synchronize_session=False)

    result_data = {'results': [result.__json__() for result in results]}
    if normalized_retcode == 0:
        pub('palantir/alert/resolved', data=result_data)
        check.run_alert_handlers(task, 'resolve', normalized_retcode, results)

    else:
        for result in results:
            task.db.add(Alert.from_result(result))
        pub('palantir/alert/raised', data=result_data)
        check.run_alert_handlers(task, 'raise', normalized_retcode, results)


@celery.task(base=StewardTask)
def resolve_alerts(alerts, userid='unknown'):
    """ Mark an alert as 'resolved' """
    task = resolve_alerts
    alert_checks = defaultdict(list)
    for alert in alerts:
        alert_checks[alert['check']].append(alert['minion'])

    for check_name, minions in alert_checks.iteritems():
        check = task.config.registry.palantir_checks[check_name]
        results = task.db.query(CheckResult).filter_by(check=check_name)\
            .filter(CheckResult.minion.in_(minions)).all()
        check.run_alert_handlers(task, 'resolve', 0, results,
                                 marked_resolved=True)
        for result in results:
            result.alert = 0
        task.db.query(Alert).filter_by(check=check_name)\
            .filter(Alert.minion.in_(minions))\
            .delete(synchronize_session=False)
    data = {'reason': 'Marked resolved by %s' % userid,
            'alerts': alerts,
            }
    pub('palantir/alert/resolved', data)


@celery.task(base=StewardTask)
def toggle_minion(minions, enabled):
    """
    Enable/disable a minion

    Parameters
    ----------
    minions : list
    enabled : bool

    """
    task = toggle_minion
    for minion in minions:
        if enabled:
            task.db.query(MinionDisabled).filter_by(name=minion).delete()
        else:
            task.db.merge(MinionDisabled(minion))
