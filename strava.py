#!/usr/bin/env python3
# -*- encoding: utf-8 -*-

import logging.config
from bottle import Bottle, run, route, response, template, request, redirect
from pygments import highlight, lexers, formatters
from requests import post, get
from json import dumps
from os.path import exists, expanduser, abspath, join
from datetime import datetime, timedelta, time
from math import floor
from configparser import ConfigParser


APP_NAME = 'strava_data_analyzer'

HTTP_HOST = '127.0.0.1'
HTTP_PORT = 5000
HTTP_AUTH = '/authorize'
HTTP_VALIDATE = '/validate'
HTTP_STATS = '/stats'
HTTP_DEBUG = True

STRAVA_API = 'https://www.strava.com/api/v3'
STRAVA_SCOPE = ['read',
                'read_all',
                'profile:read_all',
                'profile:write',
                'activity:read',
                'activity:read_all',
                'activity:write',
                ]

HTML_INDEX = """
<html>
  <body>
  <b>{{application}}</b>.<br/>
  Strava OAuth Server<br/>
  </body>
</html>
"""

STATS_TPL = """
%# disp_table.tpl
<p>Stats:</p>
<table border="1">
%for r in rows:
  <tr>
    <td>{{r}}</td>
  </tr>
%end
</table>
"""

MONTHLY = {
    "monthly distance": [
        {"id": 1, "target": 80, "state": "", "date": "", "remaining": 80, "total": 0, "elevation": 0},
        {"id": 2, "target": 80, "state": "", "date": "", "remaining": 80, "total": 0, "elevation": 0},
        {"id": 3, "target": 80, "state": "", "date": "", "remaining": 80, "total": 0, "elevation": 0},
        {"id": 4, "target": 80, "state": "", "date": "", "remaining": 80, "total": 0, "elevation": 0},
        {"id": 5, "target": 80, "state": "", "date": "", "remaining": 80, "total": 0, "elevation": 0},
        {"id": 6, "target": 80, "state": "", "date": "", "remaining": 80, "total": 0, "elevation": 0},
        {"id": 7, "target": 80, "state": "", "date": "", "remaining": 80, "total": 0, "elevation": 0},
        {"id": 8, "target": 80, "state": "", "date": "", "remaining": 80, "total": 0, "elevation": 0},
        {"id": 9, "target": 80, "state": "", "date": "", "remaining": 80, "total": 0, "elevation": 0},
        {"id": 10, "target": 80, "state": "", "date": "", "remaining": 80, "total": 0, "elevation": 0},
        {"id": 11, "target": 80, "state": "", "date": "", "remaining": 80, "total": 0, "elevation": 0},
        {"id": 12, "target": 80, "state": "", "date": "", "remaining": 80, "total": 0, "elevation": 0}
    ]
}

YEARLY = {
    "yearly distance": [
        {"id": 1, "target": 400, "remaining": 400, "state": "", "date": "", "elevation": 0},
        {"id": 2, "target": 600, "remaining": 600, "state": "", "date": "", "elevation": 0},
        {"id": 3, "target": 800, "remaining": 800, "state": "", "date": "", "elevation": 0},
        {"id": 4, "target": 1000, "remaining": 1000, "state": "", "date": "", "elevation": 0},
        {"id": 5, "target": 1200, "remaining": 1200, "state": "", "date": "", "elevation": 0},
    ]
}


api = Bottle()
access_token = ''
glob_stats = {}


@api.route('/')
def index():
    return template(HTML_INDEX, APP_NAME)


@api.route('{}'.format(HTTP_AUTH), method=['GET'])
def authorize():
    redirect_url = 'http://{}:{}{}'.format(HTTP_HOST, HTTP_PORT, HTTP_VALIDATE)
    scope = '{},{},{}'.format(STRAVA_SCOPE[0], STRAVA_SCOPE[2], STRAVA_SCOPE[5])  # make it dynamic
    resp_type = 'code'
    approval_prompt = 'force'
    url = 'https://www.strava.com/oauth/mobile/authorize?client_id={}&redirect_uri={}&response_type={}&approval_prompt={}&scope={}'.format(strava_clt_id, redirect_url, resp_type, approval_prompt, scope)
    redirect(url)


@api.route('{}'.format(HTTP_STATS), method=['GET'])
def stats_template():
    return template(STATS_TPL, row=glob_stats)


@api.route('{}'.format(HTTP_VALIDATE), method=['GET'])
def validate():
    request.accept = 'application/json'
    response.content_type = 'application/json'
    params = {
        'client_id': strava_clt_id,
        'client_secret': '{}'.format(strava_clt_secret),
        'code': request.query.code,
        'grant_type': 'authorization_code'
    }
    access_token = post("https://www.strava.com/oauth/token", params).json()
    logs.info('strava authentication result: {}'.format(access_token))

    headers = {
        'accept': 'application/json',
        'Content-Type': 'application/json',
        'Authorization': 'Bearer {}'.format(access_token['access_token']),
    }

    after = datetime(datetime.now().year, 1, 1, 0, 0).timestamp()  # current year
    per_page = 100

    activities = []
    yearly_dist = 0
    yearly_duration = 0

    for activity in get('{}/athlete/activities?after={}&per_page={}&page=1'.format(STRAVA_API, after, per_page),
                        headers=headers).json():
        data = get('{}/activities/{}?include_all_efforts=True'.format(STRAVA_API, activity['id']),
                    headers=headers).json()
        if data["type"] == "Run":
            yearly_dist += round(data["distance"] / 1000, 2)
            yearly_duration += data["moving_time"]
            avg_kmh = ms_to_kmh(data["average_speed"])
            pace_min, pace_sec = ms_to_minkm(avg_kmh)
            activities.append({"id": data["id"],
                               "date": data["start_date_local"].split('T')[0],
                               "distance": round(data["distance"] / 1000, 2),
                               "time": str(timedelta(seconds=data["moving_time"])),
                               "d+": int(round(data["total_elevation_gain"], 0)),
                               "pace": time(minute=pace_min, second=int(pace_sec)).strftime('%M:%S'),
                               "speed": round(avg_kmh, 2)
                               })

            compute_yearly_dist(yearly_dist,
                                data["start_date_local"].split('T')[0],
                                data["total_elevation_gain"])

            compute_monthly_dist(round(data["distance"] / 1000, 2),
                                 data["start_date_local"].split('T')[0],
                                 data["total_elevation_gain"])

    glob_stats.update({"activities": activities,
                    "total km": yearly_dist,
                    'total time': str(timedelta(seconds=yearly_duration))})
    glob_stats.update(YEARLY)
    glob_stats.update(MONTHLY)

    # redirect('http://{}:{}{}'.format(HTTP_HOST, HTTP_PORT, HTTP_STATS))
    return '{}'.format(dumps(glob_stats, indent=4))


def compute_monthly_dist(dist, run_date, elevation):
    m = int(run_date.split('-')[1]) - 1
    MONTHLY["monthly distance"][m]["total"] = round(MONTHLY["monthly distance"][m]["total"] + dist, 2)
    MONTHLY["monthly distance"][m]["elevation"] += elevation

    res = MONTHLY["monthly distance"][m]["target"] - MONTHLY["monthly distance"][m]["total"]

    if MONTHLY["monthly distance"][m]["remaining"] != 0:
        if res <= 0:
            MONTHLY["monthly distance"][m]["remaining"] = 0
            MONTHLY["monthly distance"][m]["state"] = "reached"
            MONTHLY["monthly distance"][m]["date"] = run_date
        else:
            MONTHLY["monthly distance"][m]["remaining"] -= dist
            MONTHLY["monthly distance"][m]["state"] = "ongoing"


def compute_yearly_dist(dist, run_date, elevation):
    for data in YEARLY["yearly distance"]:
        if data['remaining'] != 0:
            res = round(data["target"] - dist, 2)
            if res <= 0:
                data["remaining"] = 0
                data["state"] = "reached"
                data["date"] = run_date
                data["elevation"] = round(data["elevation"] + elevation, 2)
            else:
                data["remaining"] = res
                data["state"] = "ongoing"
                data["elevation"] = round(data["elevation"] + elevation, 2)


def ms_to_kmh(speed):
    """ convert speed in m/s to km/h """
    return speed * 3.6


def ms_to_minkm(speed):
    """ convert speed in ms to pace in min/km"""
    pace_min = floor(60 / speed)
    pace_sec = round(((60 / speed - floor(60 / speed)) * 60), 0)
    if pace_sec == 60:
        pace_min += 1
        pace_sec = 0
    return pace_min, pace_sec


def strava_config():
    config = ConfigParser()
    if exists(full_path('~/.config/strava/strava.ini')):
        config.read(full_path('~/.config/strava/strava.ini'))
        if not config.has_section('default'):
            logs.error('Missing default section in config file')
            exit(-1)
        else:
            strava_clt_id = config.get('default', 'STRAVA_CLT_ID', raw=False)
            strava_clt_secret = config.get('default', 'STRAVA_CLT_SECRET', raw=False)
            return strava_clt_id, strava_clt_secret
    else:
        logs.error('Missing config file')
        exit(-1)


def json_formatter(data, colorize=False, sort=True, comments=''):
    if data != {}:
        output = dumps(data, indent=4, sort_keys=sort, ensure_ascii=False)
        if colorize:
            print(highlight('{}{}'.format(comments, output), lexers.JsonLexer(), formatters.TerminalFormatter()))
        else:
            print('{}{}'.format(comments, output))


def initialize_logger():
    logger = logging.getLogger('{}'.format(APP_NAME))
    logger.setLevel(logging.INFO)
    sh = logging.handlers.SysLogHandler()
    sh.setLevel(logging.INFO)
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    # create formatter and add it to the handlers
    sh_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    ch_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    sh.setFormatter(sh_formatter)
    ch.setFormatter(ch_formatter)
    # add the handlers to the logger
    logger.addHandler(sh)
    logger.addHandler(ch)
    return logger


def full_path(path):
    # to prevent errors with debian container under Windows
    if path[0] == '~' and not exists(path):
        path = expanduser(path)
    return abspath(path)


if __name__ == '__main__':
    logs = initialize_logger()
    strava_clt_id, strava_clt_secret = strava_config()
    api.run(host=HTTP_HOST, port=HTTP_PORT, debug=HTTP_DEBUG)
