wbug - weewx extension that sends data to WeatherBug
Copyright 2014-2020 Matthew Wall
Distributed under the terms of the GNU Public License (GPLv3)

Installation instructions:

1) download

wget -O weewx-wbug.zip https://github.com/matthewwall/weewx-wbug/archive/master.zip

2) run the installer:

wee_extension --install weewx-wbug.ziop

3) modify weewx.conf:

[StdRESTful]
    [[WeatherBug]]
        publisher_id = WEATHERBUG_ID
        station_number = WEATHERBUG_STATION_NUMBER
        password = WEATHERBUG_PASSWORD

4) restart weewx

sudo /etc/init.d/weewx stop
sudo /etc/init.d/weewx start
