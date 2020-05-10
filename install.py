# installer for WeatherBug
# Copyright 2014-2020 Matthew Wall
# Distributed under the terms of the GNU Public License (GPLv3)

from weecfg.extension import ExtensionInstaller

def loader():
    return WeatherBugInstaller()

class WeatherBugInstaller(ExtensionInstaller):
    def __init__(self):
        super(WeatherBugInstaller, self).__init__(
            version="0.8",
            name='wbug',
            description='Upload weather data to WeatherBug.',
            author="Matthew Wall",
            author_email="mwall@users.sourceforge.net",
            restful_services='user.wbug.WeatherBug',
            config={
                'StdRESTful': {
                    'WeatherBug': {
                        'publisher_id': 'INSERT_PUBLISHER_ID_HERE',
                        'station_number': 'INSERT_STATION_NUMBER_HERE',
                        'password': 'INSERT_PASSWORD_HERE'}}},
            files=[('bin/user', ['bin/user/wbug.py'])]
            )
