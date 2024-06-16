import network
import utime
import json
import ntptime
import os
import gc
import sys
import uasyncio
import urequests

file_locks = {}
config = {}
curr_bssid = ""


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


def set_config(name, value, save=True):
    global config
    config[name] = value
    if save:
        save_config()


def get_config(name, defval=None):
    global config
    if name in config.keys():
        return config[name]
    else:
        return defval


def update_config(cfg):
    global config
    config.update(cfg)
    save_config()


def select_best_ap():
    sta_if = network.WLAN(network.STA_IF)
    min_rssi = -100
    bssid = b''
    if not sta_if.active():
        # sta_if.wifi_ps(network.WIFI_PS_NONE)
        sta_if.active(True)
    for ap in sta_if.scan():
        if ap[0].decode('utf-8') == get_config("wifi_ssid"):
            if min_rssi < ap[3]:
                bssid = ap[1]
                min_rssi = ap[3]
    return bssid


def wifi_connect():
    global curr_bssid
    bssid = ""
    sta_if = network.WLAN(network.STA_IF)
    ap_if = network.WLAN(network.AP_IF)

    if get_config("wifi_ap_enabled", False) is True:
        ap_if.active(True)
        ap_if.config(essid=get_config("wifi_ap_ssid"),
                     authmode=int(get_config("wifi_ap_auth", 0)),
                     password=get_config("wifi_ap_passwd", ""))

        ap_if.ifconfig((get_config("wifi_ap_ip"),
                        get_config("wifi_ap_netmask"),
                        get_config("wifi_ap_ip"),
                        get_config("wifi_ap_ip")))
    else:
        ap_if.active(False)

    if not sta_if.active():
        # sta_if.wifi_ps(network.WIFI_PS_NONE)
        sta_if.active(True)

    if sta_if.isconnected():
        if wifi_signal() < -40:
            bssid = select_best_ap()
            if bssid != curr_bssid:
                wifi_disconnect()

    if not sta_if.isconnected():
        if sta_if.status() not in (network.STAT_CONNECTING, network.STAT_GOT_IP):
            try:
                sta_if.config(dhcp_hostname=get_config("hostname"))
            except OSError as eeee:
                # log_message('WIFI CONNECT ERROR',2)
                log_exception(eeee, 2)
            bssid = select_best_ap()
            sta_if.connect(get_config("wifi_ssid"), get_config("wifi_passwd"), bssid=bssid)
        t1 = utime.ticks_ms()
        while sta_if.status() != network.STAT_GOT_IP and utime.ticks_ms() - t1 < get_config("wifi_timeout"):
            utime.sleep_ms(100)
            if sta_if.status() in (network.STAT_CONNECTING, network.STAT_NO_AP_FOUND):
                pass
            elif (sys.platform == 'esp8266' and sta_if.status() == network.STAT_CONNECT_FAIL) or (
                    sta_if.status() == network.STAT_WRONG_PASSWORD):
                break
        if sta_if.status() == network.STAT_GOT_IP:
            curr_bssid = bssid
    return sta_if.status()


def wifi_signal():
    sta_if = network.WLAN(network.STA_IF)
    try:
        signal = sta_if.status("rssi")
    except OSError as e:
        signal = -100
    return signal


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
            # log_message("NTP TIME")
            ntptime.host = config["ntp_server"]
            ntptime.settime()
        except OSError as err:
            log_exception(err, 2)
            pass


def clear():
    os.remove('main.py')


def czas(date=True, time=True, sec=False):
    (y, m, d, hh, mm, ss, wd, yd) = dst_time()
    t = ""
    if date:
        t += "%04d-%02d-%02d" % (y, m, d)
    if time:
        if t != "":
            t += " "
        t += "%02d:%02d" % (hh, mm)
        if sec:
            t += ":%02d" % ss
    return t


def dst_time():
    year = utime.localtime()[0]  # get current year
    march = utime.mktime(
        (year, 3, (31 - (int(5 * year / 4 + 1)) % 7), 1, 0, 0, 0, 0, 0))  # Time of March change to DST
    november = utime.mktime(
        (year, 10, (31 - (int(5 * year / 4 + 1)) % 7), 1, 0, 0, 0, 0, 0))  # Time of October change to EST
    now = utime.time()
    delta = 1 * 3600
    if now < march:  # we are before last sunday of march
        delta = 1 * 3600
    elif now < november:  # we are before last sunday of october
        delta = 2 * 3600
    else:  # we are after last sunday of october
        delta = 1 * 3600
    dst = utime.localtime(now + delta)
    return dst


def log_exception(exception, log_level=1, save_to_file=False):
    print(czas(True))
    if log_level < 1:
        return

    sys.print_exception(exception)

    hf = 'log.txt'
    if save_to_file:
        yield from lock_file(hf)
        log_file = open(hf, 'a+')

        print(czas(True), file=log_file)
        sys.print_exception(exception, log_file)

        log_file.close()
        unlock_file(hf)


def log_message(message):
    print(czas(True), message)


async def save_to_hist(val, hist_file):
    (y, m, d, hh, mm, ss, wd, yd) = dst_time()
    if y <= 2020:
        return

    c = czas(True)
    if get_config("remote_hist_url", "") != "":
        try:
            url = "%s/hist?date=%s&val=%s&file=%s" % (
                get_config("remote_hist_url", ""), quote(c), quote(str(val)), quote(hist_file))
            resp = urequests.get(url)
            resp.close()
        except Exception as err:
            sys.print_exception(err)
    if False:
        hf = hist_file
        await lock_file(hist_file)
        try:
            with open(hf, 'a+') as ff:
                ff.write('%s - %s\n' % (c, str(val)))
                ff.close()
        except Exception as jerr:
            print(jerr)

        unlock_file(hist_file)


def file_locked(file_name):
    global file_locks
    if file_name in file_locks.keys():
        return file_locks[file_name].locked()
    else:
        return False


async def lock_file(file_name):
    global file_locks
    try:
        print('lock', file_name)
        if file_name not in file_locks.keys():
            file_locks[file_name] = uasyncio.Lock()
        print('wait for', file_name)
        await file_locks[file_name].acquire()
        print('locked', file_name)
    except Exception as err:
        print(err)


def unlock_file(file_name):
    global file_locks
    try:
        print('unlock', file_name)
        if file_name in file_locks.keys():
            file_locks.pop(file_name, None)
    except Exception as err:
        print(err)


async def remove_hist():
    files = ['piec.hist', 'termometr.hist']
    aliases = get_config("aliases", {})
    for alias in aliases:
        fn = alias.split("=")[0]
        if fn != "":
            files.append(fn)

    for hf in files:
        try:
            if get_config("remote_hist_url", "") != "":
                try:
                    url = "%s/remove_hist?file=%s" % (get_config("remote_hist_url", ""), hf)
                    resp = urequests.get(url)
                    resp.close()
                except Exception as uer:
                    sys.print_exception(uer)

            await lock_file(hf)
            os.remove(hf)
            unlock_file(hf)
        except Exception as err:
            print(err)


def get_data():
    dane = {"czas": czas(), "termometr": 0, "temperatura": int(get_config("piec_temperatura", 40)),
            "ostatnia_zmiana": get_config("piec_ostatnia_aktualizacja", "")}

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
        if tm != "":
            tm += "\n"
        tm += t + " - " + str(times[t])

    dane["harmonogram"] = tm

    return dane


def quote(s):
    res = []
    replacements = {}
    always_safe = ('ABCDEFGHIJKLMNOPQRSTUVWXYZ'
                   'abcdefghijklmnopqrstuvwxyz'
                   '0123456789' '_.-')
    for c in s:
        if c in always_safe:
            res.append(c)
            continue
        res.append('%%%x' % ord(c))
    return ''.join(res)
