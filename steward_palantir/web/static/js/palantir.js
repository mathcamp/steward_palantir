angular.module('palantir', ['ui.bootstrap', 'truncate', 'ngRoute']).
  config(function($routeProvider) {
    $routeProvider.when('/alerts', {
      templateUrl: STATIC + 'partial/alerts.html',
      controller: AlertsController
    });

    $routeProvider.when('/minions', {
      templateUrl: STATIC + 'partial/minions.html',
      controller: MinionsController
    });

    $routeProvider.when('/minion/:minion', {
      templateUrl: STATIC + 'partial/minion.html',
      controller: MinionController
    });

    $routeProvider.when('/checks', {
      templateUrl: STATIC + 'partial/checks.html',
      controller: ChecksController
    });

    $routeProvider.when('/check/:check', {
      templateUrl: STATIC + 'partial/check.html',
      controller: CheckController
    });

    $routeProvider.otherwise({redirectTo: '/alerts', controller: AlertsController});
  }).
  run(['$rootScope','$location', '$routeParams', function($rootScope, $location, $routeParams) {
    $rootScope.$on('$routeChangeSuccess', function(scope, current, pre) {
      $rootScope.location = {
        path: $location.path()
      };
    });
  }]).
  filter('fromNow', function() {
    return function(date) {
      return moment(date).fromNow();
    };
  }).
  filter('formatDate', function() {
    return function(date) {
      if (!date) { return '';}
      return moment(date).format('MMMM Do, h:mm:ss a');
    };
  });

function BaseController($scope, $rootScope, $http, $modal) {
  $scope._ = _;
  $scope.ROUTE = ROUTE;
  $scope.STATIC = STATIC;
  $scope.showDetail = function(check, event) {

    var fetchMeta = function() {
      // Get the metadata for the check
      $http.post(ROUTE.palantir_get_check, {check: $rootScope.detailCheck.check}).
        success(function(data) {
          if ($rootScope.detailCheck !== null && $rootScope.detailCheck.check === data.name) {
            $rootScope.detailCheck.meta = data.meta;
          }
        }
      );
    };

    // Show the modal if we didn't click on a link
    if (!event.target.href && event.target.localName !== 'input') {
      var params = {minion: check.minion, check: check.check};
      if (_.has(check, 'alert')) {
        $rootScope.detailCheck = check;
        $rootScope.showDetailAlert = false;
        fetchMeta();
        $http.post(ROUTE.palantir_get_alert, params).success(function(data) {
          if ($rootScope.detailCheck !== null &&
            $rootScope.detailCheck.check === data.check &&
            $rootScope.detailCheck.minion === data.minion) {
            $rootScope.detailAlert = data;
          }
        });
      } else {
        $rootScope.detailAlert = check;
        $rootScope.showDetailAlert = true;
        $http.post(ROUTE.palantir_get_minion_check, params).success(function(data) {
          if ($rootScope.detailAlert !== null &&
            $rootScope.detailAlert.check === data.check &&
            $rootScope.detailAlert.minion === data.minion) {
            $rootScope.detailCheck = data;
            fetchMeta();
          }
        });
      }
      $modal.open({
        templateUrl: STATIC + 'partial/check_detail.html',
        controller: CheckDetailController
      });
    }
  };
}

function MinionsController($scope, $http, $filter) {
  $scope.minions = null;
  $scope.checks = {};

  $http.post(ROUTE.palantir_list_minions).success(function(data) {
    $scope.minions = _.sortBy(_.values(data), 'name');
  });

  $http.post(ROUTE.palantir_list_minion_checks).success(function(data) {
    $scope.checks = data;
  });

  $scope.getSelectedMinions = function() {
    return _.where($scope.minions, {selected: true});
  };

  $scope.allEnabled = function() {
    return _.size(_.where($scope.getSelectedMinions(), {enabled: true})) > 0;
  };

  $scope.toggleSelectAll = function(value) {
    var visible = $filter('filter')($scope.minions, $scope.search);
    _.each(visible, function(minion) {
      minion.selected = value;
    });
  };

  $scope.toggleSelected = function(minion, event) {
    if (!event.target.href && event.target.localName !== 'input') {
      minion.selected = !minion.selected;
    }
  };

  $scope.toggleAll = function() {
    var newStatus = !$scope.allEnabled();
    var names = [];
    _.each($scope.getSelectedMinions(), function(minion) {
      minion.enabled = newStatus;
      names.push(minion.name);
    });
    $http.post(ROUTE.palantir_toggle_minion, {minions: names, enabled:newStatus});
  };
}

function MinionController($scope, $route, $http) {
  $scope.minion = {};
  $http.post(ROUTE.palantir_get_minion, {minion: $route.current.params.minion}).success(function(data) {
    $scope.minion = data;
  });

  $scope.status = function(code) {
    if (code === 0) {
      return '';
    } else if (code === 1) {
      return 'warning';
    } else {
      return 'error';
    }
  };

  $scope.toggleMinion = function() {
    $scope.minion.enabled = !$scope.minion.enabled;
    var data = {minions: [$scope.minion.name], enabled:$scope.minion.enabled};
    $http.post(ROUTE.palantir_toggle_minion, data);
  };

  $scope.toggle = function(index) {
    var newStatus = !$scope.minion.checks[index].enabled;
    $scope.minion.checks[index].enabled = newStatus;
    var data = {minion: $scope.minion.name,
      checks: [$scope.minion.checks[index].check],
      enabled:newStatus};
    $http.post(ROUTE.palantir_toggle_minion_check, data);

  };
}

function AlertsController($scope, $http, $filter) {
  $scope.alerts = null;

  $http.post(ROUTE.palantir_list_alerts).success(function(data) {
    $scope.alerts = data;
  });

  $scope.getSelectedAlerts = function() {
    return _.where($scope.alerts, {selected: true});
  };

  $scope.toggleSelectAll = function(value) {
    var visible = $filter('filter')($scope.alerts, $scope.search);
    _.each(visible, function(alrt) {
      alrt.selected = value;
    });
  };

  $scope.resolveAll = function() {
    var alerts = [];
    for (var i=0; i < $scope.alerts.length; i++) {
      var alrt = $scope.alerts[i];
      if (alrt.selected) {
        alerts.push({
          minion: alrt.minion,
          check: alrt.check
        });
        $scope.alerts.splice(i, 1);
        i--;
      }
    }
    $http.post(ROUTE.palantir_resolve_alert, {alerts: alerts});
  };
}

function ChecksController($scope, $http, $filter) {
  $scope.checks = null;

  $scope.allEnabled = function() {
    return _.size(_.where($scope.getSelectedChecks(), {enabled: true})) > 0;
  };

  $scope.toggleSelectAll = function(value) {
    var visible = $filter('filter')($scope.checks, $scope.search);
    _.each(visible, function(check) {
      check.selected = value;
    });
  };

  $scope.getSelectedChecks = function() {
    return _.where($scope.checks, {selected: true});
  };

  $http.post(ROUTE.palantir_list_checks).success(function(data) {
    $scope.checks = _.sortBy(_.values(data), 'name');
  });

  $scope.toggleSelected = function(check, event) {
    if (!event.target.href && event.target.localName !== 'input') {
      check.selected = !check.selected;
    }
  };

  $scope.toggleAll = function() {
    var newStatus = !$scope.allEnabled();
    var names = [];
    _.each($scope.getSelectedChecks(), function(check) {
      check.enabled = newStatus;
      names.push(check.name);
    });
    $http.post(ROUTE.palantir_toggle_check, {checks: names, enabled:newStatus});
  };
}

function CheckController($scope, $route, $http) {
  $scope.check = {};
  $http.post(ROUTE.palantir_get_check, {check: $route.current.params.check}).success(function(data) {
    $scope.check = data;
  });

  $scope.status = function(code) {
    if (code === 0) {
      return '';
    } else if (code === 1) {
      return 'warning';
    } else {
      return 'error';
    }
  };

  $scope.toggleCheck = function() {
    $scope.check.enabled = !$scope.check.enabled;
    var data = {checks: [$scope.check.name], enabled:$scope.check.enabled};
    $http.post(ROUTE.palantir_toggle_check, data);
  };

  $scope.toggle = function(index) {
    var newStatus = !$scope.check.results[index].enabled;
    $scope.check.results[index].enabled = newStatus;
    var data = {minion: $scope.check.results[index].minion,
      checks: [$scope.check.name],
      enabled:newStatus};
    $http.post(ROUTE.palantir_toggle_minion_check, data);

  };
}

function CheckDetailController($scope) {

}
