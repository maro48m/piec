import devices
import utils
import utime
import usocket as socket
import select
import machine

import gc
import web


class Piec:
    def __init__(self, devices):
        self.devices = devices
        self.sock = None

        self.lh = -1
        self.lm = -1
        self.ltm = -1
        self.lum = -1
        self.time_update = 0
        self.btn_val = 1
        self.joy_val = 500
        self.edit_temp = 0
        self.state = 1  # 0-sleep, 1 - display, 2 - edit
        self.edit_state = 0


    def set_temperature(self, new_temp, zapisz=True):
        czas = utils.czas()
        if zapisz is True and utils.get_config("piec_historia_temperatury", True) is True:
            utils.set_config("piec_ostatnia_aktualizacja", czas)
        curr_temp = int(utils.get_config("piec_temperatura"))

        if curr_temp < new_temp <= (int(utils.get_config("piec_temperatura_max", 90)) - 5):
            set_temp = new_temp + 5
            self.devices.move_servo(utils.map_temp_to_servo(set_temp))

            utime.sleep_ms(1000)

        utils.log_message('SET TEMPERATURE: %s' % (str(new_temp)))
        self.devices.move_servo(utils.map_temp_to_servo(new_temp))
        utils.set_config("piec_temperatura", int(new_temp))
        if zapisz is True and utils.get_config("piec_historia_temperatury", True) is True:
            utils.save_to_hist(new_temp, 'piec.hist')

        utime.sleep_ms(150)

        if self.state > 0:
            self.devices.led_write_number(new_temp)

    def save_times(self, times):
        tms = {}
        # times = times.replace("%3A", ":").replace("%20-%20", " - ")
        while times != '':
            r = times[0:10]
            if r != '':
                key = r.split(' - ')[0]
                val = r.split(' - ')[1]
                tms[key] = int(val)
            times = times[10:]
        utils.set_config("piec_czasy", tms)

    def web_save(self, temp, times):
        tmp = int(temp)
        curr_tmp = int(utils.get_config("piec_temperatura", tmp))
        if tmp != curr_tmp:
            self.set_temperature(int(tmp))
        self.save_times(times)

    def handle_timer(self):
        times = utils.get_config("piec_czasy", {})
        if self.time_update == 0 and utils.wifi_connected():
            utils.settime()
            self.time_update = 1

        (y, m, d, hh, mm, ss, wd, yd) = utime.localtime(utime.time() + 1 * 3600)
        if self.lh == hh and self.lm == mm:
            return
        self.lh = hh
        self.lm = mm

        for t in times:
            th = t.split(':')[0]
            tm = int(t.split(':')[1])
            if th == '**':
                th = str(hh)
            if int(th) == hh and tm == mm:
                tmp = times[t]
                utils.log_message('HANDLE TIME %2d:%2d - %s' % (int(th), int(tm), tmp))
                self.set_temperature(int(tmp))
        if mm % 5 == 0 and self.ltm != mm:
            self.devices.thermometer_value(utils.get_config('piec_historia_termometru', True))
            self.ltm = mm

        if mm % 20 == 0 and self.lum != mm and utils.wifi_connected():
            utils.settime()
            self.lum = mm

    def handle_web(self, conn, addr):
        conn.settimeout(0.5)
        gc.collect()
        request = b''
        while True:
            buf = b''
            try:
                buf = conn.recv(128)
            except Exception as erar:
                pass
            request += buf
            if buf == b'':
                break

        conn.settimeout(None)
        rq = web.parse_request(request)
        utils.log_message('WEB REQUEST')
        utils.log_message(rq)
        handled = False
        url = rq["url"]
        if url.find("/api/") > -1:
            handled = web.handle_api(conn, rq)
        elif url.find("/save") > -1:
            temp = int(url[url.find("temp=") + len("temp="):url.find("&tempEnd")])
            times = url[url.find("times=") + len("times="):url.find("&timesEnd")]
            self.web_save(temp, times)
        elif url.find("/hist/termo") > -1:
            conn.sendall(web.get_header('text/html'))
            web.send_file(conn, 'hist_termo.html', 'r')
            handled = True
        elif url.find("/hist/piec") > -1:
            conn.sendall(web.get_header('text/html'))
            web.send_file(conn, 'hist_piec.html', 'r')
            handled = True
        elif url.find("/params") > -1:
            conn.sendall(web.get_header('text/html'))
            web.send_file(conn, 'params.html', 'r')
            handled = True
        elif url.find("/logs") > -1:
            conn.sendall(web.get_header('text/html'))
            web.send_file(conn, 'logs.html', 'r')
            handled = True

        if not handled:
            conn.sendall(web.get_header('text/html'))
            web.send_file(conn, 'index.html')
        utils.log_message('WEB REQUEST DONE')
        utime.sleep(1)
        conn.close()

    def handle_joystick(self):
        if self.edit_temp == 0:
            self.edit_temp = int(utils.get_config("piec_temperatura", 0))
        if self.state in (2, 3, 4, 5):
            val = self.devices.joy_val()
            if val <= 200:
                if self.edit_temp < int(utils.get_config("piec_temperatura_max", 90)):
                    self.edit_temp += 1
                    self.devices.led_write_number(self.edit_temp)
                utime.sleep_ms(150)
            if val >= 900:
                if self.edit_temp > int(utils.get_config("piec_temperatura_min", 30)):
                    self.edit_temp -= 1
                    self.devices.led_write_number(self.edit_temp)
                utime.sleep_ms(150)
            self.joy_val = val

    def handle_button(self, val):
        if self.btn_val == 1 and val == 0:
            self.state += 1
            if self.state == 1:
                curr_temp = int(utils.get_config("piec_temperatura", 0))
                self.devices.led_write_number(curr_temp)
            if self.state == 2:
                self.edit_temp = int(utils.get_config("piec_temperatura", 0))
            if self.state == 3:
                self.state = 1
                curr_temp = int(utils.get_config("piec_temperatura", 0))
                if self.edit_temp != curr_temp:
                    self.set_temperature(int(self.edit_temp))
                    self.devices.led_write_number(self.edit_temp)
                self.edit_temp = 0
                self.devices.write_display(5, 0)
        self.btn_val = val

    def init_wifi(self):
        if utils.wifi_connected() is False:

            utils.wifi_connect()
            if utils.wifi_connected() is True:
                try:
                    if self.sock is not None:
                        self.sock.close()
                    self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                    self.sock.bind(('', 80))
                    self.sock.listen(5)
                except OSError as serr:
                    self.sock.close()
                    utils.log_message('SOCKET ERROR')
                    utils.log_message('FREE MEMORY: %s' % (str(gc.mem_free())))
                    utils.log_exception(serr)
                    utils.wifi_disconnect()

    def run(self):
        wifid = 0
        while True:
            if self.state < 2:
                self.init_wifi()
                if utils.wifi_connected() and self.sock is not None:
                    r, w, cerr = select.select((self.sock,), (), (), 5)
                    if r:
                        for readable in r:
                            try:
                                conn, addr = self.sock.accept()
                                self.handle_web(conn, addr)
                            except OSError as error:
                                utils.log_message('WEB ERROR')
                                utils.log_message('FREE MEMORY: %s' % (str(gc.mem_free())))
                                utils.log_exception(error)
                else:
                    wifid += 1
                    utils.log_message('WIFI DOWN')
                    if wifid > 10:
                        utils.log_message('WIFI RECONNECT')
                        utils.log_message('FREE MEMORY: %s' % (str(gc.mem_free())))
                        utils.wifi_disconnect()
                        machine.soft_reset()
                        wifid = 0

                self.handle_timer()

                self.devices.display_temperature()

            else:

                if self.edit_state % 2 == 0:
                    self.devices.write_display(5, 79)
                else:
                    self.devices.write_display(5, 0)
                self.edit_state += 1
                if self.edit_state > 100:
                    self.edit_state = 0

            self.handle_joystick()
            self.handle_button(self.devices.button_value())


utils.load_config()
utils.wifi_disconnect()

devices = devices.Devices()

while True:
    try:
        utils.log_message('INIT')
        p = Piec(devices)
        p.set_temperature(int(utils.get_config("piec_temperatura", 40)), False)
        utils.log_message('RUN')
        p.run()
    except Exception as err:
        utils.log_message('GENERAL EXCEPTION')
        utils.log_message('FREE MEMORY: %s' % (str(gc.mem_free())))
        utils.log_exception(err)

        gc.collect()
