# rainmachine-ecowitt
Personal weather station Ecowitt devices parser for the RainMachine sprinkler controller.

This parser was created to avoid the use of cloud solutions, like WUnderground.com or Ecowitt.net (API not available yet). The parser establishes a direct connection between the Ecowitt and the RainMachine devices. You can still use WUnderground
too but now you have two sources in case either one decides to change something or has a problem.

## Setup
1. Download the file [ecowitt-parser.py](https://raw.githubusercontent.com/pjpeartree/rainmachine-ecowitt/master/ecowitt-parser.py)
2. Open the RainMachine Web Application https://xxx.xxx.xxx.xxx:8081/ui using your RainMachine IP address.
3. Login to your RainMachine device and then go to "Settings" - "Weather".
4. Click on "ADD NEW" button from the "Weather Services" section
5. Click on "Choose file" button and look for [ecowitt-parser.py](https://raw.githubusercontent.com/pjpeartree/rainmachine-ecowitt/master/ecowitt-parser.py) file on your computer.
6. Click "UPLOAD" to add the new weather data source parser.
7. After successfully uploaded the new parser will be listed under "User uploaded" tab from the "Weather Services" section.
8. Click on it and check the "Enable" option to activate the parser
9. Click on "REFRESH NOW" button to fetch the weather data for the first time.

You do not need to configure any parameter. The parser will auto-discover your device on the local network.

## Known Installation Issues
* You might encounter an issue if the [ecowitt-parser.py](https://raw.githubusercontent.com/pjpeartree/rainmachine-ecowitt/master/ecowitt-parser.py) file size is too big when using the remote access service (https://my.rainmachine.com) to upload the parser and it's preferable to use the direct local connection by just going to RainMachine IP address.
 
## Ecowitt Parser Details

### Auto Discover
The parser has the capability to auto-discover Ecowitt devices on the local network.

### Historical Data
The parser runs every 60 seconds but only adds the data daily, i.e. only one data point at mid-night of each day.
Internally the parser saves each observation and computes the following values for a day:
* MEAN, MAX and MIN TEMPERATURE
* MEAN, MAX and MIN RH
* MEAN PRESSURE
* MEAN WIND
* TOTAL RAIN
* MEAN SOLARRADIATION

## Authors

* **Pedro J. Pereira** - *Initial work* - [pjpeartree](https://github.com/pjpeartree)


## License

This project is licensed under the GNU General Public License v3.0 - see the [LICENSE.md](LICENSE.md) file for details
