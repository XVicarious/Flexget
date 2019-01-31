"""Contains magic that determines the hard quality of a media file."""
from __future__ import absolute_import, division, unicode_literals
from builtins import *  # noqa pylint: disable=unused-import, redefined-builtin

import logging
import os

from pymediainfo import MediaInfo

from flexget import plugin
from flexget.event import event
from flexget.utils import qualities

PLUGIN_ID = 'mediainfo'
LOG = logging.getLogger(PLUGIN_ID)


class MediaInfoQuality(object):
    """Use mediainfo to get the quality of an object."""

    schema = {'type': 'boolean', 'default': False}

    def on_task_metainfo(self, task, config):
        for entry in task.entries:
            if 'location' not in entry:
                LOG.warning('Skipping %s, we cannot find it!', entry.get('title'))
            if os.path.isdir(entry['location']):
                continue
            LOG.debug('Parsing %s', entry.get('title'))
            entry_info = MediaInfo.parse(entry['location'])
            entry_quality = set()
            for track in entry_info.tracks:
                if track.track_type == 'Video':
                    if track.height:
                        entry_quality.add(str(track.height) + 'p')
                    if track.bit_depth and track.bit_depth == 10:
                        entry_quality.add('10bit')
                if track.track_type in {'Video', 'Audio'}:
                    if track.encoded_library_name:
                        entry_quality.add(track.encoded_library_name)
                    if track.format:
                        entry_quality.add(track.format)
            if entry.get('quality'):
                old_quality = set(str(entry['quality']).split(' '))
                entry_quality.union(old_quality)
            entry['quality'] = qualities.Quality(' '.join(entry_quality))
            if entry['quality']:
                LOG.trace('Found quality %s for %s', entry['quality'], entry['title'])


@event('plugin.register')
def register_plugin():
    plugin.register(MediaInfoQuality, PLUGIN_ID, interfaces=['task', 'metainfo_quality'], api_ver=2)
