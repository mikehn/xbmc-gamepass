"""
A Kodi-agnostic library for NFL Game Pass
"""
import codecs
import uuid
import sys
import json
import calendar
import time
import urllib
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta

import requests
import m3u8
# import pdb

class pigskin(object):
    def __init__(self, proxy_config, debug=False):
        self.debug = debug
        self.base_url = 'https://gamepass.nfl.com'
        self.user_agent = "Mozilla/5.0 (Windows NT 10.0; WOW64; rv:55.0) Gecko/20100101 Firefox/55.0"
        # self.user_agent = 'Firefox'

        self.http_session = requests.Session()
        self.access_token = None
        self.refresh_token = None
        self.config = self.make_request(self.base_url + '/service/config?format=json&cameras=true', 'get')
        self.api_url = self.config['services']['api']
        print '^^^^^^^^^^^^^^API_URL:'
        print self.api_url
        # self.client_id = self.config['modules']['API']['CLIENT_ID']
        self.nfln_shows = {}
        self.nfln_seasons = []
        # self.parse_shows() TODO: Find source of these

        if proxy_config is not None:
            proxy_url = self.build_proxy_url(proxy_config)
            if proxy_url != '':
                self.http_session.proxies = {
                    'http': proxy_url,
                    'https': proxy_url,
                }

        self.log('Debugging enabled.')
        self.log('Python Version: %s' % sys.version)

    class GamePassError(Exception):
        def __init__(self, value):
            self.value = value

        def __str__(self):
            return repr(self.value)

    def log(self, string):
        if self.debug:
            try:
                print '[pigskin]: %s' % string
            except UnicodeEncodeError:
                # we can't anticipate everything in unicode they might throw at
                # us, but we can handle a simple BOM
                bom = unicode(codecs.BOM_UTF8, 'utf8')
                print '[pigskin]: %s' % string.replace(bom, '')
            except:
                pass

    def make_request(self, url, method, params=None, payload=None, headers=None):
        """Make an HTTP request. Return the response."""
        self.log('Request URL: %s' % url)
        self.log('Method: %s' % method)
        if params:
            self.log('Params: %s' % params)
        if payload:
            self.log('Payload: %s' % payload)
        if headers:
            self.log('Headers: %s' % headers)

        if method == 'get':
            req = self.http_session.get(url, params=params, headers=headers)
        elif method == 'put':
            req = self.http_session.put(url, params=params, data=payload, headers=headers)
        else:  # post
            req = self.http_session.post(url, params=params, data=payload, headers=headers)
        self.log('Response code: %s' % req.status_code)
        self.log('Response: %s' % req.content)

        return self.parse_response(req)

    def parse_response(self, req):
        """Try to load JSON data into dict and raise potential errors."""
        try:
            response = json.loads(req.content)
        except ValueError:  # if response is not json
            response = req.content

        if isinstance(response, dict):
            for key in response.keys():
                if key.lower() == 'message':
                    if response[key]: # raise all messages as GamePassError if message is not empty
                        raise self.GamePassError(response[key])

        return response

    def build_proxy_url(self, config):
        proxy_url = ''

        if 'scheme' in config:
            scheme = config['scheme'].lower().strip()
            if scheme != 'http' and scheme != 'https':
                return ''
            proxy_url += scheme + '://'

        if 'auth' in config and config['auth'] is not None:
            try:
                username = config['auth']['username']
                password = config['auth']['password']
                if username == '' or password == '':
                    return ''
                proxy_url += '%s:%s@' % (urllib.quote(username), urllib.quote(password))
            except KeyError:
                return ''

        if 'host' not in config or config['host'].strip() == '':
            return ''
        proxy_url += config['host'].strip()

        if 'port' in config:
            try:
                port = int(config['port'])
                if port <= 0 or port > 65535:
                    return ''
                proxy_url += ':' + str(port)
            except ValueError:
                return ''

        return proxy_url

    def login(self, username, password):
        """Blindly authenticate to Game Pass. Use has_subscription() to
        determine success.
        """
        url = self.base_url + '/secure/authenticate'
        post_data = {
            'username': username,
            'password': password,
            'format': 'json',
            'accesstoken': 'true'
        }
        data = self.make_request(url, 'post', payload=post_data)
        self.access_token = data['data']['accessToken']
        subscription = data['data']['hasSubscription']
        if subscription == 'true':
            return True
        self.log('User does not have a subscription!')
        raise

    def refresh_tokens(self):
        return True
        #  TODO, work out way to do this. Seems we need to register a device etc first.

        # """Refreshes authorization tokens."""
        # url = self.base_url + '/secure/authenticate'
        # post_data = {
        #     'token': self.access_token,
        #     'format': 'json',
        #     'accesstoken': 'true'
        # }
        # data = self.make_request(url, 'post', payload=post_data)
        # pdb.set_trace()
        # self.access_token = data['data']['accessToken']

        # return True

    def get_seasons_and_weeks(self):
        """Return a multidimensional array of all seasons and weeks."""
        seasons_and_weeks = {}
        # https://nflapi.neulion.com/api_nfl/v1/schedule?format=json

        try:
            url = 'https://neulion-a.akamaihd.net/nlmobile/nfl/config/nflgp/2017/weeks.json'
            data = self.make_request(url, 'get')
        except:
            self.log('Acquiring season and week data failed.')
            raise

        try:
            for season in data['seasons']:
                weeks = []
                year = str(season['season'])
                for week in season['weeks']:
                    week_dict = {
                        'week_number': str(week['value']),
                        'week_name': week['label'],
                        'season_type': week['type']
                    }
                    weeks.append(week_dict)

                seasons_and_weeks[year] = weeks
        except KeyError:
            self.log('Parsing season and week data failed.')
            raise
        return seasons_and_weeks

    def get_current_season_and_week(self):
        """Return the current season, season type, and week in a dict."""
        try:
            url = self.api_url + 'v1/schedule?format=json'
            headers = {'Authorization': 'Bearer {0}'.format(self.access_token)}
            data = self.make_request(url, 'get', headers=headers)
        except:
            self.log('Acquiring season and week data failed.')
            raise

        current_s_w = {
            'season': data['season'],
            'season_type': data['gameType'],
            'week': data['week']
        }

        return current_s_w

    def get_weeks_games(self, season, season_type, week):
        try:
            params = {
                'week': week,
                'season': season,
                'gametype': season_type,
                'format': 'json'
            }
            url = self.api_url + 'v1/schedule'
            headers = {'Authorization': 'Bearer {0}'.format(self.access_token)}
            games_data = self.make_request(url, 'get', params=params, headers=headers)
            # pdb.set_trace()
            all_games_data = []
            if games_data['games']:
                all_games_data = games_data['games']
            else:
                self.log("we are screwed")
        except:
            self.log('Acquiring games data failed.')
            raise

        return sorted(all_games_data, key=lambda x: x['dateTimeGMT'])

    # def has_coaches_tape(self, game_id, season):
    #     """Return whether coaches tape is available for a given game."""
    #     url = self.config['modules']['ROUTES_DATA_PROVIDERS']['game_page'].replace(':season', season).replace(':gameslug', game_id)
    #     response = self.make_request(url, 'get')
    #     coaches_tape = response['modules']['singlegame']['content'][0]['coachfilmVideo']
    #     if coaches_tape:
    #         self.log('Coaches Tape found.')
    #         return coaches_tape['videoId']
    #     else:
    #         self.log('No Coaches Tape found for this game.')
    #         return False


    # def has_condensed_game(self, game_id, season):
    #     """Return whether condensed game version is available."""
    #     url = self.config['modules']['ROUTES_DATA_PROVIDERS']['game_page'].replace(':season', season).replace(':gameslug', game_id)
    #     response = self.make_request(url, 'get')
    #     condensed = response['modules']['singlegame']['content'][0]['condensedVideo']
    #     if condensed:
    #         self.log('Condensed game found.')
    #         return condensed['videoId']
    #     else:
    #         self.log('No condensed version was found for this game.')
    #         return False

    def get_stream(self, video_id, gs, game_type, game_version=None):
        """Return the URL for a stream."""
        self.refresh_tokens()

        post_data = {
            'id': video_id,
            'gs': gs,
            'gt': 1,
            'type': game_type,
            'format': 'json'
        }

        # https://gamepass.nfl.com/service/publishpoint
        url = self.api_url + 'v1/publishpoint'
        headers = {'Authorization': 'Bearer {0}'.format(self.access_token)}
        response = self.make_request(url, 'post', payload=post_data, headers=headers)
        # pdb.set_trace()
        return self.parse_m3u8_manifest(response['path'], video_id, gs)

    def get_key(self, url):
        response = self.make_request(url, 'get')
        self.log(url[:url.find(".net") + 4] + response[response.find("URI=") + 5 :response.find(".key") + 4])
        self.make_request(url[:url.find(".net") + 4] + response[response.find("URI=") + 5 :response.find(".key") + 4], 'get')

    def parse_m3u8_manifest(self, manifest_url, video_id, game_state):
        """Return the manifest URL along with its bitrate."""

        streams = {}
        m3u8_header = {
            'Connection': 'keep-alive',
            'User-Agent': self.user_agent,
        }
        streams['manifest_url'] = manifest_url + '|' + urllib.urlencode(m3u8_header)
        streams['bitrates'] = {}
        m3u8_manifest = self.make_request(manifest_url, 'get')
        m3u8_obj = m3u8.loads(m3u8_manifest)
        # pdb.set_trace()

        for playlist in m3u8_obj.playlists:
            bitrate = int(playlist.stream_info.bandwidth) / 1000
            if game_state == 1:
                streams['bitrates'][bitrate] = manifest_url[:manifest_url.find('as/live/') + 8] + playlist.uri + '?' + manifest_url.split('?')[1] + '|' + urllib.urlencode(m3u8_header)
            else:
                end_of_string_idx = manifest_url.rfind('mp4.m3u8')
                new_temp_base_url = manifest_url[:end_of_string_idx]
                new_base_url = new_temp_base_url[:new_temp_base_url.rfind('/') + 1]
                streams['bitrates'][bitrate] = new_base_url + playlist.uri + '?' + \
                                               manifest_url.split('?')[1] + '|' + urllib.urlencode(m3u8_header)
        return streams

    def redzone_on_air(self):
        """Return whether RedZone Live is currently broadcasting."""
        url = self.config['modules']['ROUTES_DATA_PROVIDERS']['redzone']
        response = self.make_request(url, 'get')
        if not response['modules']['redZoneLive']['content']:
            return False
        else:
            return True

    # def parse_shows(self):
    #     """Dynamically parse the NFL Network shows into a dict."""
    #     show_dict = {}
    #     url = self.config['modules']['API']['NETWORK_PROGRAMS']
    #     response = self.make_request(url, 'get')

    #     for show in response['modules']['programs']:
    #         season_dict = {}
    #         for season in show['seasons']:
    #             season_name = season['value']
    #             season_id = season['slug']
    #             season_dict[season_name] = season_id
    #             if season_name not in self.nfln_seasons:
    #                 self.nfln_seasons.append(season_name)
    #         show_dict[show['title']] = season_dict
    #     self.nfln_shows.update(show_dict)

    def get_shows(self, season):
        """Return a list of all shows for a season."""
        seasons_shows = []

        for show_name, show_codes in self.nfln_shows.items():
            if season in show_codes:
                seasons_shows.append(show_name)

        return sorted(seasons_shows)

    # def get_shows_episodes(self, show_name, season=None):
    #     """Return a list of episodes for a show. Return empty list if none are
    #     found or if an error occurs."""
    #     url = self.config['modules']['API']['NETWORK_PROGRAMS']
    #     programs = self.make_request(url, 'get')['modules']['programs']
    #     for show in programs:
    #         if show_name == show['title']:
    #             selected_show = show
    #             break
    #     season_slug = [x['slug'] for x in selected_show['seasons'] if season == x['value']][0]
    #     request_url = self.config['modules']['API']['NETWORK_EPISODES']
    #     episodes_url = request_url.replace(':seasonSlug', season_slug).replace(':tvShowSlug', selected_show['slug'])
    #     episodes_data = self.make_request(episodes_url, 'get')['modules']['archive']['content']
    #     for episode in episodes_data:
    #         if not episode['videoThumbnail']['templateUrl']:  # set programs thumbnail as episode thumbnail
    #             episode['videoThumbnail']['templateUrl'] = [x['thumbnail']['templateUrl'] for x in programs if x['slug'] == episode['nflprogram']][0]

    #     return episodes_data

    def parse_datetime(self, date_string, localize=False):
        """Parse NFL Game Pass date string to datetime object."""
        date_time_format = '%Y-%m-%dT%H:%M:%S.%f'
        datetime_obj = datetime(*(time.strptime(date_string, date_time_format)[0:6]))
        if localize:
            return self.utc_to_local(datetime_obj)
        else:
            return datetime_obj

    @staticmethod
    def utc_to_local(utc_dt):
        """Convert UTC time to local time."""
        # get integer timestamp to avoid precision lost
        timestamp = calendar.timegm(utc_dt.timetuple())
        local_dt = datetime.fromtimestamp(timestamp)
        assert utc_dt.resolution >= timedelta(microseconds=1)
        return local_dt.replace(microsecond=utc_dt.microsecond)
