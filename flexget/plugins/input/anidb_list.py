from __future__ import absolute_import, division, unicode_literals

import logging
import re
from builtins import *  # noqa pylint: disable=unused-import, redefined-builtin

from requests import RequestException
from flexget import plugin
from flexget.config_schema import one_or_more
from flexget.entry import Entry
from flexget.event import event
from flexget.utils.cached_input import cached
from flexget.utils.soup import get_soup

log = logging.getLogger('anidb_list')
USER_ID_RE = r'^\d{1,6}$'


class AnidbList(object):
    """
    Creates an entry for each item in your AniDB wishlist.

        anidb_list:
          user_id: <required>
          [adult_only]: (ignore)/hide/only
          [is_airing]: (ignore)/airing/finished/unknown
          [type]: # zero or more
            - tvseries
            - tvspecial
            - ova
            - movie
            - web
            - musicvideo
          [buddy_lists]: (ignore)/show_in/hide_in/show_watched/hide_watched
          [mylist]: # this option can also just be the value of "status"
            [state]: watching/unknown/collecting/stalled/dropped
            [status]: (ignore)/complete/incomplete/in_mylist/not_in_mylist/related_not_in_mylist
          [vote]: (ignore)/permanent/temporary/none/either
          [watched]: # zero or more
            - unwatched
            - partial
            - complete
            - allihave
          [mode]: (all)/undefined/watch/get/blacklist/buddy
          [pass]: <guest pass set on anidb settings>
          [strip_dates]: (no)/yes

    """

    anidb_url = 'http://anidb.net/perl-bin/'
    anidb_url_pl = anidb_url + 'animedb.pl'  # Next link already has animedb.pl

    default_user_agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebkit/537.36 ' \
        '(KHTML, like Gecko) Chrome/69.0.3497.100 Safari/537.36'

    ADULT_MODES = {
        'ignore': 0,
        'hide': 1,
        'only': 2,
    }

    AIRING_MODES = {
        'ignore': 0,
        'airing': 1,
        'finished': 2,
        'unknown': 3,
    }

    MEDIA_TYPES = [
        'tvseries',
        'tvspecial',
        'ova',
        'movie',
        'web',
        'musicvideo',
        'unknown',
    ]

    BUDDY_MODES = {
        'ignore': 0,
        'show_in': 1,
        'hide_in': 2,
        'show_watched': 3,
        'hide_watched': 4,
    }

    MYLIST_MODES = {
        'ignore': 0,
        'complete': 1,
        'incomplete': 2,
        'in_mylist': 3,
        'not_in_mylist': 4,
        'related_not_in_mylist': 5,
    }

    MYLIST_STATE = [
        'watching',
        'unknown',
        'collecting',
        'stalled',
        'dropped',
    ]

    WATCHED_STATE = [
        'unwatched',
        'partial',
        'complete',
        'allihave',
    ]

    VOTE_MODES = {
        'ignore': 0,
        'permanent': 1,
        'temporary': 2,
        'none': 3,
        'either': 4,
    }

    WISHLIST_MODES = {
        'all': 0,
        'undefined': 1,
        'watch': 2,
        'get': 3,
        'blacklist': 4,
        'buddy': 11,
    }

    schema = {
        'type': 'object',
        'properties': {
            'user_id': {
                'type': 'integer',
                'pattern': USER_ID_RE,
                'error_pattern': 'user_id must be in the form XXXXXXX'},
            'adult_only': {'type': 'string', 'enum': list(ADULT_MODES.keys())},
            'is_airing': {'type': 'string', 'enum': list(AIRING_MODES.keys())},
            'type': one_or_more({'type': 'string', 'enum': MEDIA_TYPES}),
            'buddy_lists': {'type': 'string', 'enum': list(BUDDY_MODES.keys())},
            'mylist': {
                'oneOf': [
                    {'type': 'string', 'enum': list(MYLIST_MODES.keys())},
                    {'type': 'object',
                     'properties': {
                         'status': {'type': 'string', 'enum': list(MYLIST_MODES.keys())},
                         'state': one_or_more({'type': 'string', 'enum': MYLIST_STATE}),
                     }},
                ],
            },
            'vote': {'type': 'string', 'enum': list(VOTE_MODES.keys())},
            'watched': one_or_more({'type': 'string', 'enum': WATCHED_STATE}),
            'mode': {'type': 'string', 'enum': list(WISHLIST_MODES.keys())},
            'pass': {'type': 'string'},
            'strip_dates': {
                'type': 'boolean',
                'default': False},
        },
        'additionalProperties': False,
        'required': ['user_id'],
        'error_required': 'user_id is required',
    }

    def __build_url(self, config):
        # todo: this function is a mess
        params = {
            'show': 'mywishlist',
            'uid': config['user_id'],
        }
        if 'mode' in config:
            params['mode'] = self.WISHLIST_MODES[config['mode']]
        if 'type' in config:
            if isinstance(config['type'], str):
                params['type.{0}'.format(config['type'])] = 1
            elif isinstance(config['type'], list):
                for media_type in config['type']:
                    params['type.{0}'.format(media_type)] = 1
        if 'is_airing' in config:
            params['airing'] = self.AIRING_MODES[config['is_airing']]
        if 'adult_only' in config:
            params['h'] = self.ADULT_MODES[config['adult_only']]
        if 'pass' in config:
            params['pass'] = config['pass']
        if 'vote' in config:
            params['vote'] = self.VOTE_MODES[config['vote']]
        if 'watched' in config:
            if isinstance(config['watched'], str):
                params['watched.{0}'.format(config['watched'])] = 1
            elif isinstance(config['watched'], list):
                for watched_type in config['watched']:
                    params['watched.{0}'.format(watched_type)] = 1
        if 'mylist' in config:
            if isinstance(config['mylist'], str):
                params['mylist'] = self.MYLIST_MODES[config['mylist']]
            else:
                if 'status' in config['mylist']:
                    params['mylist'] = self.MYLIST_MODES[config['mylist']['status']]
                if 'state' in config['mylist']:
                    if isinstance(config['mylist']['state'], str):
                        params['liststate.{0}'.format(config['mylist']['state'])] = 1
                    else:
                        for state in config['mylist']['state']:
                            params['liststate.{0}'.format(state)] = 1
        return params

    @cached('anidb_list', persist='2 hours')
    def on_task_input(self, task, config):
        # Create entries by parsing AniDB wishlist page html using beautifulsoup
        log.verbose('Retrieving AniDB list: mywishlist:%s')
        comp_link = self.__build_url(config)
        log.debug('Requesting: %s', comp_link)

        task_headers = task.requests.headers.copy()
        task_headers['User-Agent'] = self.default_user_agent

        try:
            page = task.requests.get(self.anidb_url_pl, headers=task_headers, params=comp_link)
        except RequestException as req_except:
            raise plugin.PluginError(str(req_except))
        if page.status_code != 200:
            raise plugin.PluginError('Unable to get AniDB list. '
                                     'Either the list is private or does not exist.')

        entries = []

        while True:
            soup = get_soup(page.text)
            soup_table = soup.find('table', class_='wishlist').find('tbody')

            trs = soup_table.find_all('tr')
            if not trs:
                log.verbose('No movies were found in AniDB list: mywishlist')
                return entries
            for tr in trs:
                a_tag = tr.find('td', class_='name').find('a')
                if not a_tag:
                    log.debug('No title link found for the row, skipping')
                    continue

                anime_title = a_tag.string
                if config.get('strip_dates'):
                    # Remove year from end of series name if present
                    anime_title = re.sub(r'\s+\(\d{4}\)$', '', anime_title)

                entry = Entry()
                entry['title'] = anime_title
                entry['url'] = (self.anidb_url + a_tag.get('href'))
                entry['anidb_id'] = tr['id'][1:]  # The <tr> tag's id is "a\d+" where "\d+" is the anime id
                log.debug('%s id is %s', entry['title'], entry['anidb_id'])
                entry['anidb_name'] = entry['title']
                entries.append(entry)
            try:
                # Try to get the link to the next page.
                next_link = soup.find('li', class_='next').find('a')['href']
            except TypeError:
                # If it isn't there, there are no more pages to be crawled.
                log.verbose('No more pages on the wishlist.')
                break
            comp_link = self.anidb_url + next_link
            log.debug('Requesting: %s', comp_link)
            try:
                page = task.requests.get(comp_link, headers=task_headers)
            except RequestException as req_except:
                log.error(str(req_except))
            if page.status_code != 200:
                log.warning('Unable to retrieve next page of wishlist.')
                break
        return entries


@event('plugin.register')
def register_plugin():
    plugin.register(AnidbList, 'anidb_list', api_ver=2, interfaces=['task'])
