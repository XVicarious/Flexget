from __future__ import unicode_literals, division, absolute_import
from builtins import *  # noqa pylint: disable=unused-import, redefined-builtin

import datetime
import logging

import requests
from flexget import plugin
from flexget.event import event
from flexget.utils.requests import Session, TimedLimiter

PLUGIN_ID = 'est_release_anilist'

log = logging.getLogger(PLUGIN_ID)

REQUESTS = Session()
REQUESTS.add_domain_limiter(TimedLimiter('graphql.anilist.co', '2 seconds'))
        
ANILIST_HEADERS = {
    'Content-Type': 'application/json',
    'User-Agent': PLUGIN_ID,
    'Accept': 'application/json',
}


class EstimateSeriesAnilist(object):
    """Estimate release of Anime from Anilist."""

    anilist_api = 'https://graphql.anilist.co'
    graphql_query = """\
    query ($query: String) {
        Media (search: $query, type: ANIME) {
            id
            airingSchedule {
                nodes {
                    airingAt
                    episode
                }
            }
       }
    }\
    """

    @plugin.priority(2)
    def estimate(self, entry):
        """Estimate when entry will be available."""
        if 'series_name' not in entry:
            log.debug('We don\'t have the series name, can\'t continue')
            return
        json_body = {
            'query': self.graphql_query,
            'variables': {
                'query': entry['series_name'],
            },
        }
        try:
            query_result = REQUESTS.post(self.anilist_api, headers=ANILIST_HEADERS, json=json_body)
            airing_dates = query_result.json()['data']['Media']['airingSchedule']['nodes']
            series_episode = entry.get('series_episode')
            if len(airing_dates) and series_episode:
                airdate = datetime.datetime.fromtimestamp(airing_dates[series_episode - 1]['airingAt'])
                log.verbose('%s episode %s airs on %s', entry['series_name'], series_episode, airdate)
                return airdate
        except requests.exceptions.HTTPError as error:
            log.error(error)
            log.debug(entry['series_name'])


@event('plugin.register')
def register_plugin():
    plugin.register(EstimateSeriesAnilist, PLUGIN_ID, interfaces=['estimate_release'], api_ver=2)
