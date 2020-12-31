import network
import utime
import json
import ntptime
import os

config = {"wifi_ssid": "zrodlo",
          "wifi_passwd": "LothLorien.#13",
          "hostname": "piec",
          "wifi_timeout": 15000,
          "wifi_ap": 0,
          "wifi_ap_auth": 3,
          "wifi_ap_ssid": "piec",
          "wifi_ap_passwd": "piec1234",
          "wifi_ap_ip": "192.168.23.1",
          "wifi_ap_netmask": "255.255.255.0",
          "ntp": 1,
          "ntp_server": "0.pl.pool.ntp.org",
          "piec_temperature": 50,
          "piec_times": {
              "06:30": 50,
              "22:00": 40}
          }


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
        ntptime.host = config["ntp_server"]
        ntptime.settime()


def clear():
    os.remove('main.py')


def czas(sec=False):
    y = utime.localtime(utime.time() + 1 * 3600)[0]
    m = utime.localtime(utime.time() + 1 * 3600)[1]
    d = utime.localtime(utime.time() + 1 * 3600)[2]
    hh = utime.localtime(utime.time() + 1 * 3600)[3]
    mm = utime.localtime(utime.time() + 1 * 3600)[4]
    if sec:
        ss = utime.localtime(utime.time() + 1 * 3600)[5]
        return "%04d-%02d-%02d %02d:%02d:%02d" % (y, m, d, hh, mm, ss)
    else:
        return "%04d-%02d-%02d %02d:%02d" % (y, m, d, hh, mm)


def log_message(message, save_to_file=True):
    print(czas(True), message)
    if save_to_file:
        log_file = open('log.txt', 'a+')
        print(czas(True), message, file=log_file)
        log_file.close()
