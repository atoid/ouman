# ouman.py
## Ouman EH-200 series tool

This tool can be used to query and write Ouman EH-200 series data. These devices can be connected to a PC with RS-232 null modem cable. The tool can be also used for logging device data at defined interval in csv format. Logging is freely configurable with ouman_config.json.

## Examples

### Query id 1 which is device information

```
$ python3 ouman.py -i 1
{
    "raw": "02 06 21 00 01 1a 16 22 00 32 30 31 4c 91 41 75 67 20 20 35 20 30 33 00 00 00 00 00 00 00 00 00 00 00 00 00 ff",
    "data_type": "device",
    "sn": 2233882,
    "device": "201L",
    "version": 1.45,
    "date": "Aug  5 03"
}
```

### Query id 12 which is heating settings

```
$ python3 ouman.py -i 12
{
    "raw": "02 06 21 00 0c 20 19 14 14 23 00 00 28 0a 1e 05 0f 46 fa 00 00 64 00 64 02 05 02 01 00 00 00 4b 00 00 00 00 78",
    "data_type": "L1_settings1",
    "-20": 32,
    "0": 25,
    "20": 20,
    "min": 20,
    "max": 35,
    "motor": 2
}
```

### Query id 20 which is water flow (EH-201L)

```
$ python3 ouman.py -i 20
{
    "raw": "02 06 04 00 14 08 34 5a",
    "data_type": "temp_100",
    "temperature": 21.0
}
```

### Write id 2 which is date and time
This test writes zeroes minutes and shows the expected result. When -t option is removed the write is committed to the device.

```
$ python3 ouman.py -i 2 -w 00 -o 5 -t
{
    "raw": "02 82 09 00 02 07 e6 0a 05 16 00 26 c5",
    "data_type": "datetime",
    "date": "5.10.2022",
    "time": "22:00:38"
}
```

### Show usage

```
$ python3 ouman.py -h
ouman tool usage and options
 -h show this usage
 -i <id> query id
 -w <data>
 -o <offset>, default is 0
 -t test only, do not commit write
 -m <message> send any message
 -l <interval> listen and log csv
 -f <file> log csv to file
 -p <dev> serial device, default is /dev/ttyUSB0
```
