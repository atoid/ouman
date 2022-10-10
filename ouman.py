import serial
import sys
import struct
import getopt
import json
import time
import socket
import os

#
# Some ID numbers, for more information see
# http://ouman.fi/documentbank/MODBUS-200__manual__fi.pdf
#
# 1 = laitetiedot
# 2,3 = päiväys
# 12 = menovesi asetukset 1
# 13 = menovesi asetukset 2
# 15 = menovesi info
# 17 = mittausten konfigurointi
# 44 = yleiset asetukset
# 18-34 = mittaukset
#

#
# Example write command
#
# Moottorivalinta 230V 3-tila
# $ python3 ouman.py -i 12 -w 03 -o 21
#

#
# ouman_config.json format for log configuration
# {
#    # array of ids to query
#    "ids": [18, 15, 3],
#    # array of names to log, integer names log bytes from the raw result
#    "names": ["temperature", "L1_target", ["time", "date", 0, 1]]
# }
#

class IdType:
    def __init__(self, id_start, id_end, data_type):
        self.id_start = id_start
        self.id_end = id_end
        self.data_type = data_type

    def match(self, id):
        if id == self.id_start:
            return True
        elif id >= self.id_start and id <= self.id_end:
            return True
        else:
            return False

ID_TYPES = [
    IdType(1, 0, "device"),
    IdType(2, 3, "datetime"),
    IdType(12, 0, "L1_settings1"),
    IdType(13, 0, "L1_settings2"),
    IdType(15, 0, "L1_info"),
    IdType(18, 34, "temp_100"),
]

def parse_data(msg, res, data_type):
    res["data_type"] = data_type

    if data_type == "temp_100":
        v = struct.unpack_from(">h", msg)[0]
        v = float(v) / 100.0
        res["temperature"] = v
    elif data_type == "device":
        ser = struct.unpack_from("<L", msg, 0)[0]
        dev = msg[4:8].decode()
        ver = float(msg[8]) / 100.0
        dat = msg[9:18].decode()
        res["sn"] = ser
        res["device"] = dev
        res["version"] = ver
        res["date"] = dat
    elif data_type == "datetime":
        tmp = struct.unpack_from(">HBBBBB", msg, 0)
        res["date"] = "{}.{}.{}".format(tmp[2], tmp[1], tmp[0])
        res["time"] = "{}:{:02}:{:02}".format(tmp[3], tmp[4], tmp[5])
    elif data_type == "L1_settings1":
        #                         012345678901234567890123456789
        tmp = struct.unpack_from("BBBBBxxxxxxxxxxxxxxxxB", msg, 0)
        res["-20"] = tmp[0]
        res["0"] = tmp[1]
        res["20"] = tmp[2]
        res["min"] = tmp[3]
        res["max"] = tmp[4]
        res["motor"] = tmp[5]
    elif data_type == "L1_settings2":
        #                         012345678901234567890123456789
        tmp = struct.unpack_from("xxxxxxxxxxB", msg, 0)
        res["motor_runtime"] = tmp[0]
    elif data_type == "L1_info":
        #                         012345678901234567890123456789
        tmp = struct.unpack_from("BxxxxxxxxxxxxxB", msg, 0)
        res["L1_curve"] = tmp[0]
        res["L1_target"] = tmp[1]

def parse_message(res):
    msg = res.get("raw", bytearray())
    res["raw"] = msg.hex(" ")

    if len(msg) >= 6:
        id = msg[4]
        msg_data = msg[5:-1]

        if len(msg_data) != 0:
            for t in ID_TYPES:
                if t.match(id):
                    parse_data(msg_data, res, t.data_type)
                    break

def add_crc(msg):
    crc = 0
    for v in msg[1:]:
        crc += v
    msg.append(crc & 0xff)

def check_crc(msg):
    crc = 0
    for v in msg[1:-1]:
        crc += v

    crc &= 0xff
    if crc == msg[-1]:
        return True, crc
    else:
        return False, crc

def run_server(sp):
    s = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    s.bind("\x00ouman_server")

    while True:
        msg, sock = s.recvfrom(1024)
        res = dict()
        send_rcv_sp(sp, bytearray(msg), res)
        res["raw"] = res["raw"].hex(" ")
        s.sendto(json.dumps(res).encode(), sock)

def send_rcv(sp, msg, res):
    if sp:
        send_rcv_sp(sp, msg, res)
    else:
        try:
            send_rcv_dgram(msg, res)
        except:
            res["error"] = "socket"

def send_rcv_dgram(msg, res):
    s = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    s.bind("\x00ouman_client{}".format(os.getpid()))
    s.sendto(bytes(msg), "\x00ouman_server")
    s.settimeout(5)
    msg, sock = s.recvfrom(1024)
    s.close()
    msg = json.loads(msg)
    msg["raw"] = bytearray.fromhex(msg["raw"])
    res.update(msg)

def send_rcv_sp(sp, msg, res):
    add_crc(msg)
    sp.write(msg)

    rcv = bytearray()
    res["raw"] = rcv

    while True:
        d = sp.read()
        if len(d) == 0:
            res["error"] = "timeout"
            return
        rcv.append(d[0])

        if len(rcv) == 1:
            if rcv[0] != 0x02:
                res["error"] = "protocol"
                return
        elif len(rcv) <= 3:
            pass
        elif (len(rcv)-4) >= rcv[2]:
            break

    ok, crc = check_crc(rcv)
    if not ok:
        res["error"] = "crc {:02x}".format(crc)

def query_data(sp, id, res):
    msg = [0x02, 0x81, 0x02, 0x00, id]
    return send_rcv(sp, msg, res)

def replace_data(msg, offset, data):
    di = 5 + offset
    for d in data:
        msg[di] = d
        di += 1

def write_data(sp, id, res, offset, data, test):
    query_data(sp, id, res)
    if not res.get("error"):
        msg = res["raw"]
        replace_data(msg, offset, data)
        msg = msg[:-1]
        msg[1] = 0x82
        if not test:
            msg = send_rcv(sp, msg, res)
        else:
            add_crc(msg)
            res["raw"] = msg

def opt_to_bytearray(opt_str):
    tmp = opt_str.split()
    msg = []
    for d in tmp:
        msg.append(int(d, 16))
    return msg

def get_attr(res, attr):
    if type(attr) == str:
        return res.get(attr, 0)
    elif type(attr) == int:
        di = (5+attr) * 3
        return int(res.get("raw")[di:di+2], 16)
    return 0

def listen(sp, opt_listen, opt_file):
    f_json = open("ouman_config.json")
    cfg = json.load(f_json)
    f_json.close()

    ids = cfg.get("ids")
    names = cfg.get("names")

    if opt_file:
        f_log = open(opt_file, "a")

    while True:
        res = dict()
        vals = []
        for i in range(len(ids)):
            query_data(sp, ids[i], res)
            parse_message(res)
            if type(names[i]) == list:
                for attr in names[i]:
                    vals.append(get_attr(res, attr))
            else:
                vals.append(get_attr(res, names[i]))

        if not res.get("error"):
            log_str = ("{}," * len(vals) + "{}").format(int(time.time()), *vals)
            if opt_file:
                print(log_str, file=f_log)
                f_log.flush()
            else:    
                print(log_str)

        if opt_listen > 0:
            time.sleep(opt_listen)
        else:
            if opt_file:
                f_log.close()
            sys.exit(0)

def usage():
    print("ouman tool usage and options")
    print(" -h show this usage")
    print(" -i <id> query id")
    print(" -w <data>")
    print(" -o <offset>, default is 0")
    print(" -t test only, do not commit write")
    print(" -m <message> send any message")
    print(" -l <interval> listen and log csv")
    print(" -f <file> log csv to file")
    print(" -p <dev> serial device, default is /dev/ttyUSB0")
    print(" -s run server")
    print(" -c run client")

# MAIN

def main():
    sp = None
    opt_id = 20
    opt_port = "/dev/ttyUSB0"
    #opt_msg = "02 81 02 00 1a"
    opt_msg = None
    opt_listen = None
    opt_write = None
    opt_offset = 0
    opt_test = False
    opt_file = None
    opt_client = False
    opt_server = False
    
    try:
        opts, args = getopt.getopt(sys.argv[1:], "htsci:m:p:l:w:o:f:")
    except getopt.GetoptError as err:
        print(err)
        sys.exit(2)

    for o, a in opts:
        if o == "-h":
            usage()
            sys.exit()
        elif o == "-i":
            opt_id = int(a)
        elif o == "-m":
            opt_msg = a
        elif o == "-p":
            opt_port = a
        elif o == "-l":
            opt_listen = int(a)
        elif o == "-f":
            opt_file = a
        elif o == "-t":
            opt_test = True
        elif o == "-s":
            opt_server = True
        elif o == "-c":
            opt_client = True
        elif o == "-w":
            opt_write = a
        elif o == "-o":
            opt_offset = int(a)
        else:
            assert False, "unhandled option"

    if opt_client and opt_server:
        print("Cannot run in server and client mode")
        sys.exit(2)

    if not opt_client:
        sp = serial.Serial(opt_port, 4800, timeout=2, exclusive=True)

    if opt_server:
        print("Server mode, Ctrl+C to exit")
        run_server(sp)
        sys.exit()

    if opt_listen != None:
        if opt_listen > 0:
            print("Listening, Ctrl+C to exit")
        listen(sp, opt_listen, opt_file)

    res = dict()
    if opt_write:
        data = opt_to_bytearray(opt_write)
        write_data(sp, opt_id, res, opt_offset, data, opt_test)
    elif opt_msg:
        msg = opt_to_bytearray(opt_msg)
        send_rcv(sp, msg, res)
    else:
        query_data(sp, opt_id, res)

    parse_message(res)
    res_json = json.dumps(res, indent=4)
    print(res_json)

    if sp:
        sp.close()

if __name__ == "__main__":
    main()
