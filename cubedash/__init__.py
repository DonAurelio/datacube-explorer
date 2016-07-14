from datacube.index import index_connect

index = index_connect()

from dateutil import parser
from datacube.model import Range
from datacube.utils import jsonify_document
from json import dumps as jsonify
from datetime import datetime
import shapely.ops
import shapely.geometry
import rasterio.warp

import flask
import os

app = flask.Flask(__name__)
static_prefix = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'frontend')


FIELDS = ['platform', 'instrument', 'product']


def as_json(o):
    return jsonify(jsonify_document(o), indent=4)


def parse_query(request):
    query = {}
    for field in FIELDS:
        query[field] = request[field]
    query['time'] = Range(parser.parse(request['after']), parser.parse(request['before']))

    def range_dodge(val):
        if isinstance(val, list):
            return Range(val[0], val[1])
        else:
            return Range(val - 0.00005, val + 0.00005)

    if 'lon' in request and 'lat' in request:
        query['lon'] = range_dodge(request['lon'])
        query['lat'] = range_dodge(request['lat'])
    return query


def datasets_union(dss):
    return shapely.ops.unary_union([shapely.geometry.Polygon(ds.extent.points) for ds in dss])


def warp_geometry(geom, crs):
    return rasterio.warp.transform_geom(crs, 'EPSG:4326', geom)


# There's probably a proper bottle way to do this.
URL_PREFIX = '/api'


@app.route(URL_PREFIX + '/products')
def products():
    types = index.datasets.types.get_all()
    return as_json({type_.name: type_.definition for type_ in types})


@app.route(URL_PREFIX + '/products/<name>')
def product(name):
    type_ = index.datasets.types.get_by_name(name)
    return as_json(type_.definition)


@app.route(URL_PREFIX + '/datasets')
def datasets():
    return as_json({'error': 'Too many. TODO: paging'})


def dataset_to_feature(ds):
    properties = {
        'id': ds.id,
        'product': ds.type.name,
        'time': ds.center_time
    }
    return {
        'type': 'Feature',
        'geometry': warp_geometry(shapely.geometry.mapping(shapely.geometry.Polygon(ds.extent.points)), str(ds.crs)),
        'properties': {
            'id': ds.id,
            'product': ds.type.name,
            'time': ds.center_time
        }
    }



@app.route(URL_PREFIX + '/datasets/<product>')
def datasets_as_features(product):
    year = 2014
    time = Range(datetime(year, 1, 1), datetime(year, 7, 1))
    datasets = index.datasets.search(product=product, time=time)
    return {
        'type': 'FeatureCollection',
        'features': [dataset_to_feature(ds) for ds in datasets]
    }


def month_iter(begin, end):
    def next_date(date):
        if date.month == 12:
            return datetime(date.year + 1, 1, 1)
        else:
            return datetime(date.year, date.month + 1, 1)

    begin = datetime(begin.year, begin.month, 1)
    while begin < end:
        yield Range(begin, next_date(begin))
        begin = next_date(begin)


@app.route(URL_PREFIX + '/timeline/<product>')
def product_timeline(product):
    result = []
    for time in month_iter(datetime(2013, 1, 1), datetime.now()):
        datasets = index.datasets.search_eager(product=product, time=time)
        result.append((time.begin, len(datasets)))
    return as_json({'data': result})


@app.route(URL_PREFIX + '/datasets/id/<id_>')
def dataset(id_):
    dataset_ = index.datasets.get(id_, include_sources=True)
    return as_json(dataset_.metadata_doc)


if __name__ == '__main__':
    app.run(port=8080, debug=True)