""" Highlight's Steward web interface """
from pyramid.view import view_config


@view_config(route_name='palantir', renderer='palantir.jinja2')
def do_index(request):
    """ Render the index page """
    return {}


def includeme(config):
    """ Configure the app """

    config.add_static_view('palantir/static', 'steward_palantir.web:static/',
                           permission='palantir_read')

    config.add_route('palantir', '/palantir')
    config.add_steward_web_app('Palantir', 'palantir')

    config.scan()
