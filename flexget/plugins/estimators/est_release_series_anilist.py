"""Plugin to find the release date of episodes of anime from Anilist."""
from __future__ import absolute_import, division, unicode_literals

import logging
from builtins import *  # noqa pylint: disable=unused-import, redefined-builtin
from datetime import datetime
from difflib import SequenceMatcher
from http import HTTPStatus

import requests

from flexget import plugin
from flexget.event import event
from flexget.utils.requests import Session, TimedLimiter

PLUGIN_ID = 'est_release_anilist'

LOG = logging.getLogger(PLUGIN_ID)

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
    search_query = """\
            query ($query: String, $page: Int, $perPage: Int) {
                Page(page: $page, perPage: $perPage) {
                    pageInfo {
                        total
                        currentPage
                        lastPage
                        hasNextPage
                        perPage
                    }
                    media(search: $query, type: ANIME) {
                        id
                        title {
                            romaji
                            english
                            native
                        }
                    }
                }
            }\
            """
    graphql_query = """\
    query ($query: Int) {
        Media (id: $query, type: ANIME) {
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
            LOG.debug('We don\'t have the series name, can\'t continue')
            return
        anilist_id = self.search_anime(entry['series_name'])
        if not anilist_id:
            LOG.debug('No results for %s', entry['series_name'])
            return
        json_body = {
            'query': self.graphql_query,
            'variables': {
                'query': anilist_id,
            },
        }
        try:
            query_result = REQUESTS.post(self.anilist_api, headers=ANILIST_HEADERS, json=json_body)
            airing_dates = query_result.json()['data']['Media']['airingSchedule']['nodes']
            series_episode = entry.get('series_episode')
            if len(airing_dates) and series_episode:
                airdates = [date['airingAt'] for date in airing_dates if series_episode == date['episode']]
                if not len(airdates):
                    return
                airdate = datetime.fromtimestamp(airdates[0])
                if airdate > datetime.now():
                    LOG.verbose('%s episode %s airs on %s', entry['series_name'], series_episode, airdate)
                return airdate
        except requests.exceptions.HTTPError as error:
            LOG.error(error)
            LOG.debug('%s not found.', entry['series_name'])

    def fetch_search_result(self, json_query, anime_results=None):
        """Recursively gather search results from Anilist."""
        if not anime_results:
            anime_results = []
        query_result = REQUESTS.post(self.anilist_api, headers=ANILIST_HEADERS, json=json_query)
        if query_result.status_code >= HTTPStatus.BAD_REQUEST:
            raise plugin.PluginWarning('Error retrieving results from Anilist')
        query_json = query_result.json()['data']['Page']
        anime_results.extend(query_json['media'])
        page_info = query_json['pageInfo']
        if page_info['hasNextPage']:
            current_page = int(page_info['current'])
            json_query.update({'page': current_page + 1})
            return self.fetch_search_result(json_query, anime_results=anime_results)
        return anime_results

    def search_anime(self, title):
        """
        Search for an anime on Anilist.

        :param title: Title of anime we are looking for.
        :return the Anilist id for the requested anime, or None if not found.
        """
        json_body = {
            'query': self.search_query,
            'variables': {
                'query': title,
            },
        }
        anime_results = self.fetch_search_result(json_body)
        good_titles = []
        seq_match = SequenceMatcher(a=title)
        for anime in anime_results:
            titles = anime['title'].values()
            for possible_title in titles:
                if not possible_title:
                    continue
                seq_match.set_seq2(possible_title)
                match_ratio = seq_match.ratio()
                if match_ratio >= 0.9:
                    good_titles.append((anime['id'], match_ratio, possible_title))
        good_titles = sorted(good_titles, key=lambda title: title[1], reverse=True)
        if len(good_titles):
            return good_titles[0][0]


@event('plugin.register')
def register_plugin():
    """Register the plugin into Flexget."""
    plugin.register(EstimateSeriesAnilist, PLUGIN_ID, interfaces=['estimate_release'], api_ver=2)
