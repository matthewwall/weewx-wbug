# Copyright 2013-2020 Matthew Wall

"""
This is a weewx extension that uploads data to WeatherBug.

http://weather.weatherbug.com

Minimal Configuration:

[StdRESTful]
    [[WeatherBug]]
        publisher_id = WEATHERBUG_ID
        station_number = WEATHERBUG_STATION_NUMBER
        password = WEATHERBUG_PASSWORD

Some information about the upload api is at the wbug developers forum:

http://backyard.weatherbug.com/group/developers/forum

This implementation uses the weatherbug API v1.4 of 4 march 2011:

http://backyard.weatherbug.com/group/developers/forum/topics/backyard-stations-publishing-api-v1-4-released

HTTP Querystring Parameters...

Required Parameters
1.action [action=live] Indicates that this is current data
         [action=hist] Indicates this is historical data. 
2.ID [Station ID as registered above]
3.Key [your self assigned PASSWORD associated with this Station ID]
4.Num [This is the StationNum element from above] 
5.dateutc - [YYYY-MM-DD HH:MM:SS (mysql format)]
6.winddir - [0-360] 
7.windspeedmph - [mph] 
8.windgustmph - [windgustmph ]
9.humidity - [%] 
10.tempf - [temperature F]
11.rainin - [rain in (hourly)] -- the accumulated rainfall in the past 60 mins
12.dailyrainin - [rain so far today in localtime]
13.baromin - [barom in]
14.tempfhi - [high for today in deg F]
15.tempflo - [low for today in deg F]
16.monthlyrainin - accumulated rain so far this month.
17.Yearlyrainin - accumulated rain so far this year.

Optional parameters
If there are additional temperature and humidity sensors then they can be
sent as tempf2, tempf3, humidity2, humidity3, etc. temp2desc can be sent as
a description of what the temperature represents (ie, water or soil or other).

1.dewptf- [dewpoint F] this is already calculated from temp and humidity.
2.weather - [text] -- metar style (+RA)
3.clouds - [text] -- SKC, FEW, SCT, BKN, OVC
4.soiltempf - [temp F]
5.soilmoisture - [%]
6.leafwetness  - [%]
7.solarradiation - [MJ/m^2]
8.UV - [index]
9.visibility - [nm]
10.softwaretype - [text] ie: vws or weatherdisplay

Example Call:
http://data.backyard2.weatherbug.com/data/livedata.aspx?ID=P000001&Key=XXXXXX&num=xxxx&dateutc=2000-01-01+10%3A32%3A35&winddir=230&windspeedmph=12&windgustmph=12&tempf=70&tempfhi=81&tempflo=50&rainin=0&baromin=29.1&dewptf=68.2&humidity=90&weather=&clouds=&softwaretype=vws%20versionxx
"""

# FIXME: weatherbug does not deal well with empty uploads.  if you try to
# upload no values, you get this from weatherbug:
#   QueryString:Av Wd Spd Er::998.98554

# FIXME: the action parameter is ill-defined. since 'live' is never actually
# the current time, technically everything is historical.

try:
    # Python 3
    import queue
except ImportError:
    # Python 2
    import Queue as queue
import calendar
import re
import sys
import time
try:
    # Python 3
    from urllib.parse import urlencode
except ImportError:
    # Python 2
    from urllib import urlencode


import weewx
import weewx.restx
import weewx.units
from weeutil.weeutil import startOfDayUTC

VERSION = "0.8"

if weewx.__version__ < "3":
    raise weewx.UnsupportedFeature("weewx 3 is required, found %s" %
                                   weewx.__version__)

try:
    # Test for new-style weewx logging by trying to import weeutil.logger
    import weeutil.logger
    import logging
    log = logging.getLogger(__name__)

    def logdbg(msg):
        log.debug(msg)

    def loginf(msg):
        log.info(msg)

    def logerr(msg):
        log.error(msg)

except ImportError:
    # Old-style weewx logging
    import syslog

    def logmsg(level, msg):
        syslog.syslog(level, 'WeatherBug: %s' % msg)

    def logdbg(msg):
        logmsg(syslog.LOG_DEBUG, msg)

    def loginf(msg):
        logmsg(syslog.LOG_INFO, msg)

    def logerr(msg):
        logmsg(syslog.LOG_ERR, msg)

def _get_rain(dbm, start_ts, end_ts):
    val = dbm.getSql("SELECT SUM(rain) FROM %s "
                     "WHERE dateTime>? AND dateTime<=?" %
                     dbm.table_name, (start_ts, end_ts))
    return val[0] if val is not None else None

def _get_month_rain(dbm, ts):
    tt = time.gmtime(ts)
    som_ts = calendar.timegm((tt.tm_year, tt.tm_mon, 1, 0, 0, 0, 0, 0, -1))
    return _get_rain(dbm, int(som_ts), ts)

def _get_year_rain(dbm, ts):
    tt = time.gmtime(ts)
    soy_ts = calendar.timegm((tt.tm_year, 1, 1, 0, 0, 0, 0, 0, -1))
    return _get_rain(dbm, int(soy_ts), ts)

def _get_day_max_temp(dbm, ts):
    sod = startOfDayUTC(ts)
    val = dbm.getSql("SELECT MAX(outTemp) FROM %s "
                     "WHERE dateTime>? AND dateTime<=?" %
                     dbm.table_name, (sod, ts))
    return val[0] if val is not None else None

def _get_day_min_temp(dbm, ts):
    sod = startOfDayUTC(ts)
    val = dbm.getSql("SELECT MIN(outTemp) FROM %s "
                     "WHERE dateTime>? AND dateTime<=?" %
                     dbm.table_name, (sod, ts))
    return val[0] if val is not None else None

class WeatherBug(weewx.restx.StdRESTbase):
    def __init__(self, engine, config_dict):
        """This service recognizes standard restful options plus the following:

        publisher_id: WeatherBug publisher identifier

        station_number: WeatherBug station number

        password: WeatherBug password

        latitude: Station latitude in decimal degrees
        Default is station latitude

        longitude: Station longitude in decimal degrees
        Default is station longitude
        """
        super(WeatherBug, self).__init__(engine, config_dict)
        loginf("service version is %s" % VERSION)

        site_dict = weewx.restx.get_site_dict(config_dict, 'WeatherBug', 'publisher_id',
                                              'station_number', 'password')
        if site_dict is None:
            return
        site_dict.setdefault('latitude', engine.stn_info.latitude_f)
        site_dict.setdefault('longitude', engine.stn_info.longitude_f)
        site_dict['manager_dict'] = weewx.manager.get_manager_dict(
            config_dict['DataBindings'], config_dict['Databases'], 'wx_binding')

        self.archive_queue = queue.Queue()
        self.archive_thread = WeatherBugThread(self.archive_queue, **site_dict)
        self.archive_thread.start()
        self.bind(weewx.NEW_ARCHIVE_RECORD, self.new_archive_record)
        loginf("Data will be uploaded for station_number=%s publisher_id=%s" % 
               (site_dict['station_number'], site_dict['publisher_id']))

    def new_archive_record(self, event):
        self.archive_queue.put(event.record)

class WeatherBugThread(weewx.restx.RESTThread):

    _SERVER_URL = 'http://data.backyard2.weatherbug.com/data/livedata.aspx'
    _DATA_MAP = {'tempf':          ('outTemp',     '%.1f'), # F
                 'humidity':       ('outHumidity', '%.0f'), # percent
                 'winddir':        ('windDir',     '%.0f'), # degree [0-360]
                 'windspeedmph':   ('windSpeed',   '%.1f'), # mph
                 'windgustmph':    ('windGust',    '%.1f'), # mph
                 'baromin':        ('barometer',   '%.3f'), # inHg
                 'rainin':         ('hourRain',    '%.2f'), # in
                 'dailyRainin':    ('dayRain',     '%.2f'), # in
                 'monthlyrainin':  ('monthRain',   '%.2f'), # in
                 'tempfhi':        ('outTempMax',  '%.1f'), # F (for the day)
                 'tempflo':        ('outTempMin',  '%.1f'), # F (for the day)
                 'Yearlyrainin':   ('yearRain',    '%.2f'), # in
                 'dewptf':         ('dewpoint',    '%.1f'), # F
                 'solarradiation': ('radiation',   '%.1f'), # MJ/m^2
                 'UV':             ('UV',          '%.0f'), # index
                 'soiltempf':      ('soilTemp1',   '%.1f'), # F
                 'soiltempf2':     ('soilTemp2',   '%.1f'), # F
                 'soiltempf3':     ('soilTemp3',   '%.1f'), # F
                 'soiltempf4':     ('soilTemp4',   '%.1f'), # F
                 'soilmoisture':   ('soilMoist1',  '%.1f'), # %
                 'soilmoisture2':  ('soilMoist2',  '%.1f'), # %
                 'soilmoisture3':  ('soilMoist3',  '%.1f'), # %
                 'soilmoisture4':  ('soilMoist4',  '%.1f'), # %
                 'leafwetness':    ('leafWet1',    '%.1f'), # %
                 'leafwetness':    ('leafWet1',    '%.1f'), # %
                 'tempf2':         ('extraTemp1',  '%.1f'), # F
                 'tempf3':         ('extraTemp2',  '%.1f'), # F
                 'tempf4':         ('extraTemp3',  '%.1f'), # F
                 'humidity2':      ('extraHumid1', '%.0f'), # %
                 'humidity3':      ('extraHumid2', '%.0f'), # %
                 }

    def __init__(self, q,
                 publisher_id, station_number, password, latitude, longitude,
                 manager_dict,
                 server_url=_SERVER_URL, skip_upload=False,
                 post_interval=None, max_backlog=sys.maxsize, stale=None,
                 log_success=True, log_failure=True,
                 timeout=60, max_tries=3, retry_wait=5):
        super(WeatherBugThread, self).__init__(q,
                                               protocol_name='WeatherBug',
                                               manager_dict=manager_dict,
                                               post_interval=post_interval,
                                               max_backlog=max_backlog,
                                               stale=stale,
                                               log_success=log_success,
                                               log_failure=log_failure,
                                               max_tries=max_tries,
                                               timeout=timeout,
                                               retry_wait=retry_wait,
                                               skip_upload=skip_upload)
        self.publisher_id = publisher_id
        self.station_number = station_number
        self.password = password
        self.latitude = float(latitude)
        self.longitude = float(longitude)
        self.server_url = server_url

    def get_record(self, record, dbm):
        rec = super(WeatherBugThread, self).get_record(record, dbm)
        # Must have non-null windSpeed
        if 'windSpeed' not in rec or rec['windSpeed'] is None:
            raise weewx.restx.FailedPost("No windSpeed in record")
        # put everything into the right units
        rec = weewx.units.to_US(rec)
        # add the fields specific to weatherbug
        rec['monthRain'] = _get_month_rain(dbm, rec['dateTime'])
        rec['yearRain'] = _get_year_rain(dbm, rec['dateTime'])
        rec['outTempMax'] = _get_day_max_temp(dbm, rec['dateTime'])
        rec['outTempMin'] = _get_day_min_temp(dbm, rec['dateTime'])
        # be sure additional fields are correct units
        if rec['usUnits'] != record['usUnits']:
            (from_unit, _) = weewx.units.getStandardUnitType(
                record['usUnits'], 'rain')
            if 'dayRain' in rec and rec['dayRain']:
                from_t = (rec['dayRain'], from_unit, 'group_rain')
                rec['dayRain'] = weewx.units.convert(from_t, 'inch')[0]
            if 'monthRain' in rec and rec['monthRain']:
                from_t = (rec['monthRain'], from_unit, 'group_rain')
                rec['monthRain'] = weewx.units.convert(from_t, 'inch')[0]
            if 'yearRain' in rec and rec['yearRain']:
                from_t = (rec['yearRain'], from_unit, 'group_rain')
                rec['yearRain'] = weewx.units.convert(from_t, 'inch')[0]
            (from_unit, _) = weewx.units.getStandardUnitType(
                record['usUnits'], 'outTemp')
            if 'outTempMax' in rec and rec['outTempMax']:
                from_t = (rec['outTempMax'], from_unit, 'group_temperature')
                rec['outTempMax'] = weewx.units.convert(from_t, 'degree_F')[0]
            if 'outTempMin' in rec and rec['outTempMin']:
                from_t = (rec['outTempMin'], from_unit, 'group_temperature')
                rec['outTempMin'] = weewx.units.convert(from_t, 'degree_F')[0]
        return rec

    def check_response(self, response):
        for line in response:
            if not line.startswith('Successfully Received'):
                raise weewx.restx.FailedPost("Server response: %s" % line)

    def format_url(self, record):
        logdbg("record: %s" % record)
        # put data into expected structure and format
        values = { 'action':'live' }
        values['softwaretype'] = 'weewx_%s' % weewx.__version__
        values['ID'] = self.publisher_id
        values['Num'] = self.station_number
        values['Key'] = self.password
        time_tt = time.gmtime(record['dateTime'])
        values['dateutc'] = time.strftime("%Y-%m-%d %H:%M:%S", time_tt)
        for key in self._DATA_MAP:
            rkey = self._DATA_MAP[key][0]
            if rkey in record and record[rkey] is not None:
                values[key] = self._DATA_MAP[key][1] % record[rkey]
        url = self.server_url + '?' + urlencode(values)
        if weewx.debug >= 2:
            logdbg('url: %s' % re.sub(r"Key=[^\&]*", "Key=XXX", url))
        return url


# Do direct testing of this extension like this:
#   PYTHONPATH=WEEWX_BINDIR python WEEWX_BINDIR/user/wbug.py
if __name__ == "__main__":
    import optparse
    import weewx.manager

    weewx.debug = 2

    try:
        # WeeWX V4 logging
        weeutil.logger.setup('wbug', {})
    except NameError:
        # WeeWX V3 logging
        syslog.openlog('wbug', syslog.LOG_PID | syslog.LOG_CONS)
        syslog.setlogmask(syslog.LOG_UPTO(syslog.LOG_DEBUG))

    usage = """%prog --id=PUBLISHER-ID --station=STATION-NUMBER --pw=PASSWORD [--version] [--help]"""

    parser = optparse.OptionParser(usage=usage)
    parser.add_option('--version', dest='version', action='store_true',
                      help='display driver version')
    parser.add_option('--id', metavar='PUBLISHER-ID', help='Your publisher ID')
    parser.add_option('--station', metavar='STATION-NUMBER', help='Station ID of station to upload')
    parser.add_option('--pw', dest='pw', metavar='PASSWORD', help='your password')
    (options, args) = parser.parse_args()

    manager_dict = {
        'manager': 'weewx.manager.DaySummaryManager',
        'table_name': 'archive',
        'schema': None,
        'database_dict': {
            'SQLITE_ROOT': '/home/weewx/archive',
            'database_name': 'weewx.sdb',
            'driver': 'weedb.sqlite'
        }
    }

    if options.version:
        print("meteotemplate uploader version %s" % VERSION)
        exit(0)

    print("uploading to station %s" % options.station)
    q = queue.Queue()
    t = WeatherBugThread(q, options.id, options.station, options.pw,
                         45.0, -125.0, manager_dict)
    t.start()
    q.put({'dateTime': int(time.time() + 0.5),
           'usUnits': weewx.US,
           'outTemp': 32.5,
           'inTemp': 75.8,
           'outHumidity': 24,
           'windSpeed': 3.2})
    q.put(None)
    t.join(20)
