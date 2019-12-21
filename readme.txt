wbug - weewx extension that sends data to WeatherBug
Copyright 2014 Matthew Wall

Installation instructions:

1) run the installer:

wee_extension --install weewx-wbug.tgz

2) modify weewx.conf:

[StdRESTful]
    [[WeatherBug]]
        publisher_id = WEATHERBUG_ID
        station_number = WEATHERBUG_STATION_NUMBER
        password = WEATHERBUG_PASSWORD

3) restart weewx

sudo /etc/init.d/weewx stop
sudo /etc/init.d/weewx start
