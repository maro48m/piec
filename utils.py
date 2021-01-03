import network
import utime
import json
import ntptime
import os
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
        with open('config.json') as infile:
            config = json.load(infile)
            infile.close()
    except Exception as err:
        print(err)


def save_config():
    global config
    with open('config.json', 'w') as outfile:
        json.dump(config, outfile)
        outfile.close()


def set_config(name, value, save=True):
    config[name] = value
    if save:
        save_config()


def get_config(name, defval=None):
    if name in config.keys():
        return config[name]
    else:
        return defval


def wifi_connect():
    sta_if = network.WLAN(network.STA_IF)

    if get_config("wifi_ap_enabled") != 0:
        ap_if = network.WLAN(network.AP_IF)
        ap_if.active(True)
        ap_if.config(essid=get_config("wifi_ap_ssid"),
                     authmode=get_config("wifi_ap_auth", ""),
                     password=get_config("wifi_ap_passwd", ""))

        ap_if.ifconfig((get_config("wifi_ap_ip"),
                        get_config("wifi_ap_netmask"),
                        "0.0.0.0",
                        "0.0.0.0"))

    if not sta_if.isconnected():
        if sta_if.status() == 255:
            sta_if.active(True)
        if sta_if.status() not in (network.STAT_CONNECTING, network.STAT_GOT_IP):
            sta_if.config(dhcp_hostname=get_config("hostname"))
            sta_if.connect(get_config("wifi_ssid"), get_config("wifi_passwd"))
        t1 = utime.ticks_ms()
        while sta_if.status() != network.STAT_GOT_IP and utime.ticks_ms() - t1 < get_config("wifi_timeout"):
            utime.sleep_ms(100)
            if sta_if.status() in (network.STAT_CONNECTING, network.STAT_NO_AP_FOUND):
                pass
            elif sta_if.status() in (network.STAT_CONNECT_FAIL, network.STAT_WRONG_PASSWORD):
                break

    return sta_if.status()


def wifi_connected():
    sta_if = network.WLAN(network.STA_IF)
    sta_if.config("mac")
    return sta_if.isconnected()


def wifi_config():
    sta_if = network.WLAN(network.STA_IF)
    return sta_if.ifconfig()


def wifi_disconnect():
    sta_if = network.WLAN(network.STA_IF)
    sta_if.active(False)

    if get_config("wifi_ap_enabled") != 0:
        ap_if = network.WLAN(network.AP_IF)
        ap_if.active(False)


def settime():
    if config["ntp_enabled"] == 1:
        log_message('SET TIME')
        ntptime.host = config["ntp_server"]
        ntptime.settime()


def clear():
    os.remove('main.py')


def czas(sec=False):
    (y, m, d, hh, mm, ss, wd, yd) = utime.localtime(utime.time() + 1 * 3600)
    if sec:
        return "%04d-%02d-%02d %02d:%02d:%02d" % (y, m, d, hh, mm, ss)
    else:
        return "%04d-%02d-%02d %02d:%02d" % (y, m, d, hh, mm)

def log_exception(exception, save_to_file=True):
    print(czas(True))
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
        files_in_use[hf] = 0

def log_message(message, save_to_file=True):
    if type(message) == Exception:
        print(czas(True))
        sys.print_exception(message)
    else:
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

    files_in_use[hf] = 0


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
