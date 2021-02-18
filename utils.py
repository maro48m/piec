import network
import utime
import json
import ntptime
import os
import gc
import sys

files_in_use = {}

config = {}


def val_map(x, in_min, in_max, out_min, out_max):
    return max(min(out_max, (x - in_min) * (out_max - out_min) // (in_max - in_min) + out_min), out_min)


def map_temp_to_servo(temp):
    min_servo = int(get_config("servo_min", 37))
    max_servo = int(get_config("servo_max", 115))
    servo_pos = val_map(temp, 30, 90, min_servo, max_servo)
    return servo_pos


def load_config():
    global config
    try:
        with open('/config.json') as infile:
            config = json.load(infile)
            infile.close()
    except Exception as err:
        print(err)

    try:
        fn = 'config_%s.json' % sys.platform
        with open(fn) as infile:
            cf = json.load(infile)
            infile.close()
            config.update(cf)
    except Exception as err:
        print(err)


def save_config():
    global config
    fn = 'config_%s.json' % sys.platform
    with open(fn, 'w') as outfile:
        json.dump(config, outfile)
        outfile.close()
    wait_for_file()


def set_config(name, value, save=True):
    config[name] = value
    if save:
        save_config()


def get_config(name, defval=None):
    if name in config.keys():
        return config[name]
    else:
        return defval


def update_config(cfg):
    p = json.loads(cfg)
    config.update(p)
    save_config()


def wifi_connect():
    sta_if = network.WLAN(network.STA_IF)
    ap_if = network.WLAN(network.AP_IF)

    if get_config("wifi_ap_enabled", False) is True:
        ap_if.active(True)
        ap_if.config(essid=get_config("wifi_ap_ssid"),
                     authmode=int(get_config("wifi_ap_auth", 0)),
                     password=get_config("wifi_ap_passwd", ""))

        ap_if.ifconfig((get_config("wifi_ap_ip"),
                        get_config("wifi_ap_netmask"),
                        "0.0.0.0",
                        "0.0.0.0"))
    else:
        ap_if.active(False)


    if not sta_if.isconnected():
        sta_if.active(True)
        if sta_if.status() not in (network.STAT_CONNECTING, network.STAT_GOT_IP):
            try:
                sta_if.config(dhcp_hostname=get_config("hostname"))
            except OSError as eeee:
                #log_message('WIFI CONNECT ERROR',2)
                log_exception(eeee, 2)

            sta_if.connect(get_config("wifi_ssid"), get_config("wifi_passwd"))
        t1 = utime.ticks_ms()
        while sta_if.status() != network.STAT_GOT_IP and utime.ticks_ms() - t1 < get_config("wifi_timeout"):
            utime.sleep_ms(100)
            if sta_if.status() in (network.STAT_CONNECTING, network.STAT_NO_AP_FOUND):
                pass
            elif (sys.platform == 'esp8266' and sta_if.status() == network.STAT_CONNECT_FAIL) or (
                    sta_if.status() == network.STAT_WRONG_PASSWORD):
                break

    return sta_if.status()


def wifi_signal():
    sta_if = network.WLAN(network.STA_IF)
    return sta_if.status("rssi")


def wifi_connected():
    sta_if = network.WLAN(network.STA_IF)
    return sta_if.isconnected()


def wifi_config():
    sta_if = network.WLAN(network.STA_IF)
    return sta_if.ifconfig()


def wifi_disconnect():
    sta_if = network.WLAN(network.STA_IF)
    if sta_if.isconnected():
        sta_if.disconnect()
    sta_if.active(False)

    if get_config("wifi_ap_enabled", False) is True:
        ap_if = network.WLAN(network.AP_IF)
        ap_if.active(False)


def settime():
    if get_config("ntp_enabled", True) is True:
        try:
            #log_message("NTP TIME", 3)
            ntptime.host = config["ntp_server"]
            ntptime.settime()
        except OSError as err:
            log_exception(err, 2)
            pass


def clear():
    os.remove('main.py')


def czas(sec=False):
    (y, m, d, hh, mm, ss, wd, yd) = utime.localtime(utime.time() + 1 * 3600)
    if sec:
        return "%04d-%02d-%02d %02d:%02d:%02d" % (y, m, d, hh, mm, ss)
    else:
        return "%04d-%02d-%02d %02d:%02d" % (y, m, d, hh, mm)


def log_exception(exception, log_level=1, save_to_file=True):
    print(czas(True))
    if log_level < int(get_config("log_level",1)):
        return

    sys.print_exception(exception)

    global files_in_use
    hf = 'log.txt'
    if save_to_file:
        if hf in files_in_use.keys():
            while files_in_use[hf] == 1:
                utime.sleep_ms(1)

        files_in_use[hf] = 1
        log_file = open('log.txt', 'a+')

        print(czas(True), file=log_file)
        sys.print_exception(exception, log_file)

        log_file.close()
        wait_for_file()
        files_in_use[hf] = 0


def log_message(message, log_level=1, save_to_file=False):
    if log_level < int(get_config("log_level", 1)):
        return
    print(czas(True), message)
    global files_in_use
    hf = 'log.txt'
    if save_to_file:
        if hf in files_in_use.keys():
            while files_in_use[hf] == 1:
                utime.sleep_ms(1)

        files_in_use[hf] = 1
        log_file = open('log.txt', 'a+')
        if type(message) == Exception:
            print(czas(True), file=log_file)
            sys.print_exception(message, log_file)
        else:
            print(czas(True), message, file=log_file)
        log_file.close()
        wait_for_file()
        files_in_use[hf] = 0


def save_to_hist(val, hist_file):
    global files_in_use
    c = czas(True)
    hf = hist_file
    if hf in files_in_use.keys():
        while files_in_use[hf] == 1:
            utime.sleep_ms(1)

    files_in_use[hf] = 1
    try:
        with open(hf, 'a+') as ff:
            ff.write('%s - %s\n' % (c, str(val)))
            ff.close()
    except Exception as jerr:
        pass

    wait_for_file()
    files_in_use[hf] = 0


def file_locked(file_name):
    global files_in_use
    if file_name in files_in_use.keys():
        return files_in_use[file_name] == 1
    else:
        return False


def lock_file(file_name):
    global files_in_use
    files_in_use[file_name] = 1


def unlock_file(file_name):
    global files_in_use
    files_in_use[file_name] = 0


def wait_for_file():
    utime.sleep_ms(250)


def remove_hist(file):
    files = []
    if file & 1:
        files.append('piec.hist')
    if file & 2:
        files.append('termometr.hist')
    if file & 4:
        files.append('log.txt')

    for hf in files:
        try:
            if hf in files_in_use.keys():
                while files_in_use[hf] == 1:
                    utime.sleep_ms(1)
            files_in_use[hf] = 1
            os.remove(hf)
            files_in_use[hf] = 0
        except:
            pass


def get_epoch(dts):
    tt = dts.split(" ")
    dt = tt[0].split("-")
    ht = tt[1].split(":")
    ep = utime.mktime((int(dt[0]), int(dt[1]), int(dt[2]), int(ht[0]), int(ht[1]), int(ht[2]), 0, 0))
    return ep


def get_data():
    dane = {}
    dane["czas"] = czas()
    dane["termometr"] = 0
    dane["temperatura"] = int(get_config('piec_temperatura', 40))
    dane["ostatnia_zmiana"] = get_config('piec_ostatnia_aktualizacja', '')

    fs_stat = os.statvfs(os.getcwd())
    fs_size = fs_stat[0] * fs_stat[2]
    fs_free = fs_stat[0] * fs_stat[3]
    dane["fs_size"] = fs_size
    dane["fs_free"] = fs_free
    dane["mem_free"] = gc.mem_free()
    dane["mem_size"] = gc.mem_alloc() + dane["mem_free"]
    dane["rssi"] = wifi_signal()

    times = get_config('piec_czasy', {})
    tm = ''
    for t in sorted(times):
        tm += t + ' - ' + str(times[t]) + '\n'

    dane["harmonogram"] = tm

    return dane


