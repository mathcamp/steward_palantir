from steward_palantir.check import Check

class HealthCheck(Check):
    def __init__(self):
        super(HealthCheck, self).__init__(
            'health',
            {'cmd': 'echo "Salt is running"'},
            {'seconds': 10},
            target='*',
            handlers=(
                {'log': None},
            ),
        )
