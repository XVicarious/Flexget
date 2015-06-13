import json
import os
from mock import patch

from tests import FlexGetBase, MockManager
from flexget import __version__
from flexget.manager import Manager
from flexget.api import app, API_VERSION


class APITest(FlexGetBase):

    def __init__(self):
        self.client = app.test_client()
        FlexGetBase.__init__(self)

    def json_post(self, *args, **kwargs):
        if 'header' not in kwargs:
            kwargs['headers'] = [('Content-Type', 'application/json')]
        return self.client.post(*args, **kwargs)


class TestServerAPI(APITest):

    __yaml__ = """
        tasks:
          test:
            rss:
              url: http://test/rss
            mock:
              - title: entry 1
        """

    def test_pid(self):
        rsp = self.client.get('/server/pid/')
        assert rsp.status_code == 200
        assert json.loads(rsp.data) == {'pid': os.getpid()}

    @patch.object(MockManager, 'load_config')
    def test_reload(self, mocked_load_config):
        rsp = self.client.get('/server/reload/')
        assert rsp.status_code == 200
        assert mocked_load_config.called

    @patch.object(Manager, 'shutdown')
    def test_shutdown(self, mocked_shutdown):
        self.client.get('/server/shutdown/')
        assert mocked_shutdown.called

    def test_get_config(self):
        rsp = self.client.get('/server/config/')
        assert rsp.status_code == 200
        assert json.loads(rsp.data) == {
            'tasks': {
                'test': {
                    'mock': [{'title': 'entry 1'}],
                    'rss': {'url': 'http://test/rss'}
                }
            }
        }

    def test_version(self):
        rsp = self.client.get('/server/version/')
        assert rsp.status_code == 200
        assert json.loads(rsp.data) == {'flexget_version': __version__, 'api_version': API_VERSION}


class TestTaskAPI(APITest):

    __yaml__ = """
        tasks:
          test:
            rss:
              url: http://test/rss
            mock:
              - title: entry 1
        """

    def test_list_tasks(self):
        rsp = self.client.get('/tasks/')
        data = json.loads(rsp.data)
        assert data == {
            'tasks': [
                {
                    'name': 'test',
                    'config': {
                        'mock': [{'title': 'entry 1'}],
                        'rss': {'url': 'http://test/rss'}
                    },
                }
            ]
        }

    @patch.object(Manager, 'save_config')
    def test_add_task(self, mocked_save_config):
        new_task = {
            'name': 'new_task',
            'config': {
                'mock': [{'title': 'entry 1'}],
                'rss': {'url': 'http://test/rss'}
            }
        }

        rsp = self.json_post('/tasks/', data=json.dumps(new_task))

        assert rsp.status_code == 201
        assert mocked_save_config.called
        assert json.loads(rsp.data) == new_task
        assert self.manager.user_config['tasks']['new_task'] == new_task['config']

        # With defaults
        new_task['config']['rss']['ascii'] = False
        new_task['config']['rss']['group_links'] = False
        new_task['config']['rss']['silent'] = False
        new_task['config']['rss']['all_entries'] = True
        assert self.manager.config['tasks']['new_task'] == new_task['config']

    def test_add_task_existing(self):
        new_task = {
            'name': 'test',
            'config': {
                'mock': [{'title': 'entry 1'}]
            }
        }

        rsp = self.json_post('/tasks/', data=json.dumps(new_task))
        assert rsp.status_code == 409

    def test_get_task(self):
        rsp = self.client.get('/tasks/test/')
        data = json.loads(rsp.data)
        assert data == {
            'name': 'test',
            'config': {
                'mock': [{'title': 'entry 1'}],
                'rss': {'url': 'http://test/rss'}
            },
        }

    @patch.object(Manager, 'save_config')
    def test_update_task(self, mocked_save_config):
        updated_task = {
            'name': 'test',
            'config': {
                'mock': [{'title': 'entry 1'}],
                'rss': {'url': 'http://newurl/rss'}
            }
        }

        rsp = self.json_post('/tasks/test/', data=json.dumps(updated_task))

        assert rsp.status_code == 200
        assert mocked_save_config.called
        assert json.loads(rsp.data) == updated_task
        assert self.manager.user_config['tasks']['test'] == updated_task['config']

        # With defaults
        updated_task['config']['rss']['ascii'] = False
        updated_task['config']['rss']['group_links'] = False
        updated_task['config']['rss']['silent'] = False
        updated_task['config']['rss']['all_entries'] = True
        assert self.manager.config['tasks']['test'] == updated_task['config']

    @patch.object(Manager, 'save_config')
    def test_rename_task(self, mocked_save_config):
        updated_task = {
            'name': 'new_test',
            'config': {
                'mock': [{'title': 'entry 1'}],
                'rss': {'url': 'http://newurl/rss'}
            }
        }

        rsp = self.json_post('/tasks/test/', data=json.dumps(updated_task))

        assert rsp.status_code == 201
        assert mocked_save_config.called
        assert json.loads(rsp.data) == updated_task
        assert 'test' not in self.manager.user_config['tasks']
        assert 'test' not in self.manager.config['tasks']
        assert self.manager.user_config['tasks']['new_test'] == updated_task['config']

        # With defaults
        updated_task['config']['rss']['ascii'] = False
        updated_task['config']['rss']['group_links'] = False
        updated_task['config']['rss']['silent'] = False
        updated_task['config']['rss']['all_entries'] = True
        assert self.manager.config['tasks']['new_test'] == updated_task['config']

    @patch.object(Manager, 'save_config')
    def test_delete_task(self, mocked_save_config):
        rsp = self.client.delete('/tasks/test/')

        assert rsp.status_code == 200
        assert mocked_save_config.called
        assert 'test' not in self.manager.user_config['tasks']
        assert 'test' not in self.manager.config['tasks']


# TODO: Finish tests