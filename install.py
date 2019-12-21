# $Id: install.py 1373 2015-10-14 13:50:32Z mwall $
# installer for WeatherBug
# Copyright 2014 Matthew Wall

from setup import ExtensionInstaller

def loader():
    return WeatherBugInstaller()

class WeatherBugInstaller(ExtensionInstaller):
    def __init__(self):
        super(WeatherBugInstaller, self).__init__(
            version="0.7",
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
