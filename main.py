import utils
import devices
import gc
import web_helper
from web import handle_api, send_file
import uasyncio
import sys
import utime


class Piec:
    def __init__(self):
        self.devices = devices.Devices()

        self.lh = -1
        self.lm = -1
        self.ltm = -1
        self.lum = -1
        self.time_update = 0
        self.btn_val = 1
        self.joy_val = 500
        self.edit_temp = 0
        self.state = 1  # 0-sleep, 1 - display, 2 - edit
        self.disp_state = 0
        self.lcd_state = 0
        self.edit_state = 0
        self.curr_temp = 0

        self.btn_task = None
        self.joy_task = None
        self.display_task = None
        self.web_task = None
        self.timer_task = None
        self.wifi_task = None
        self.lcd_task = None
        self.thermo_task = None

    async def set_temperature(self, new_temp, zapisz=True):
        czas = utils.czas()
        if zapisz is True and utils.get_config("piec_historia_temperatury", True) is True:
            if utils.dst_time()[0] > 2000:
                utils.set_config("piec_ostatnia_aktualizacja", czas, False)
        curr_temp = int(utils.get_config("piec_temperatura"))

        if curr_temp < new_temp <= (
                int(utils.get_config("piec_temperatura_max", 90)) - int(utils.get_config("piec_temperatura_wg", 5))):
            set_temp = new_temp + int(utils.get_config("piec_temperatura_wg", 5))
            await self.devices.move_servo(utils.map_temp_to_servo(set_temp))

            await uasyncio.sleep_ms(1000)

        elif curr_temp > new_temp >= (
                int(utils.get_config("piec_temperatura_min", 30)) + int(utils.get_config("piec_temperatura_wd", 2))):
            set_temp = new_temp - int(utils.get_config("piec_temperatura_wd", 2))
            await self.devices.move_servo(utils.map_temp_to_servo(set_temp))

            await uasyncio.sleep_ms(1000)

        await self.devices.move_servo(utils.map_temp_to_servo(new_temp))
        utils.set_config("piec_temperatura", int(new_temp))
        if zapisz is True and utils.get_config("piec_historia_temperatury", True) is True:
            if utils.dst_time()[0] > 2000:
                await utils.save_to_hist(new_temp, 'piec.hist')

        await uasyncio.sleep_ms(150)

        # if self.state > 0:
        #     self.devices.led_write_number(new_temp)

    def save_times(self, times):
        tms = {}
        while times != '':
            r = times[0:10]
            if r != '':
                key = r.split(' - ')[0]
                val = r.split(' - ')[1]
                tms[key] = int(val)
            times = times[10:]
        utils.set_config("piec_czasy", tms)
        del tms

    async def web_save(self, temp, times):
        tmp = int(temp)
        curr_tmp = int(utils.get_config("piec_temperatura", tmp))
        if tmp != curr_tmp:
            await self.set_temperature(int(tmp))
        self.save_times(times)

    async def handle_timer(self):
        while True:
            times = utils.get_config("piec_czasy", {})
            if self.time_update == 0 and utils.wifi_connected():
                utils.settime()
                self.time_update = 1

            (y, m, d, hh, mm, ss, wd, yd) = utils.dst_time()

            if y > 2000:
                if not (self.lh == hh and self.lm == mm):
                    self.lh = hh
                    self.lm = mm

                    for t in times:
                        th = t.split(':')[0]
                        tm = int(t.split(':')[1])
                        if th == '**':
                            th = str(hh)
                        if int(th) == hh and tm == mm:
                            tmp = times[t]
                            curr_tmp = int(utils.get_config("piec_temperatura", tmp))
                            if int(tmp) != curr_tmp:
                                await self.set_temperature(int(tmp))
                    del times

                    if utils.get_config('piec_historia_termometru', True):
                        if mm % int(utils.get_config("piec_historia_termometru_czas", 5)) == 0 and self.ltm != mm:
                            await self.devices.thermometer_value(utils.get_config('piec_historia_termometru', True))
                            self.ltm = mm

                    if mm % 20 == 0 and self.lum != mm and utils.wifi_connected():
                        utils.settime()
                        self.lum = mm
            await uasyncio.sleep(30)

    async def handle_web(self, reader, writer):
        # utils.log_message('HANDLE WEB')

        gc.collect()
        request = b''
        bufsize = 10
        if sys.platform == 'esp32':
            bufsize = -1
        while True:
            buf = b''
            try:
                buf = await uasyncio.wait_for(reader.read(bufsize), 0.5)
            except uasyncio.TimeoutError:
                break

            if buf == b'':
                break

            request += buf
            del buf
            gc.collect()

        # print(request)
        rq = web_helper.parse_request(request)

        # utils.log_message(rq)
        del request
        handled = False
        url = rq["url"]
        if url.find("/api/") > -1:
            handled = await handle_api(writer, rq)
        elif url.find("/save") > -1:
            temp = int(url[url.find("temp=") + len("temp="):url.find("&tempEnd")])
            times = url[url.find("times=") + len("times="):url.find("&timesEnd")]
            await self.web_save(temp, times)
            writer.write(web_helper.get_header('application/json'))
            writer.write('{"result":"Dane zapisane"}'.encode('utf-8'))
            await writer.drain()
            handled = True
        elif url.find("/hist/termo") > -1:
            handled = await send_file(writer, 'hist_termo.html', 'text/html')
        elif url.find("/hist/piec") > -1:
            handled = await send_file(writer, 'hist_piec.html', 'text/html')
        elif url.find("/params") > -1:
            handled = await send_file(writer, 'params.html', 'text/html')
        elif url.find("/logs") > -1:
            handled = await send_file(writer, 'logs.html', 'text/html')
        elif url.find("/logs") > -1:
            handled = await send_file(writer, 'logs.html', 'text/html')
        elif url.find("/fileup") > -1:
            handled = await send_file(writer, 'fileup.html', 'text/html')
        if not handled:
            await send_file(writer, 'index.html', 'text/html')
        del rq
        # utils.log_message('WEB REQUEST DONE')

        writer.close()
        await writer.wait_closed()

    async def handle_joystick(self):
        while True:
            # utils.log_message('HANDLE JOYSTICK')
            if self.edit_temp == 0:
                self.edit_temp = int(utils.get_config("piec_temperatura", 0))
            if self.state in (2, 3, 4, 5):
                val = self.devices.joy_val()
                if val <= 200:
                    if self.edit_temp < int(utils.get_config("piec_temperatura_max", 90)):
                        self.edit_temp += 1
                        self.devices.led_write_number(self.edit_temp)
                    await uasyncio.sleep_ms(150)
                if val >= 900:
                    if self.edit_temp > int(utils.get_config("piec_temperatura_min", 30)):
                        self.edit_temp -= 1
                        self.devices.led_write_number(self.edit_temp)
                    await uasyncio.sleep_ms(150)
                self.joy_val = val
                await uasyncio.sleep_ms(10)
            else:
                await uasyncio.sleep_ms(500)

    async def handle_button(self):
        while True:
            val = self.devices.button_value()
            # utils.log_message('HANDLE BUTTON %d %d' % (val, self.btn_val))
            if self.btn_val == 1 and val == 0:
                self.state += 1
                if self.state == 1:
                    curr_temp = int(utils.get_config("piec_temperatura", 0))
                    self.devices.led_write_number(curr_temp)
                    self.devices.led_write_number(None, 2)
                    self.devices.led_write_number(None, 3)
                if self.state == 2:
                    self.lcd_state = 0
                    self.edit_temp = int(utils.get_config("piec_temperatura", 0))
                    self.devices.led_write_number(self.edit_temp)
                    self.devices.led_write_number(None, 2)
                    self.devices.led_write_number(None, 3)
                if self.state == 3:
                    curr_temp = int(utils.get_config("piec_temperatura", 0))
                    if self.edit_temp != curr_temp:
                        await self.set_temperature(int(self.edit_temp))
                        self.devices.led_write_number(self.edit_temp)
                    self.edit_temp = 0
                    self.devices.write_display(5, 0)

                    self.lcd_state = 0
                    self.disp_state = 0

                    self.state = 1

            self.btn_val = val
            await uasyncio.sleep_ms(150)

    async def handle_wifi(self):
        while True:
            # utils.log_message('HANDLE WIFI')
            if utils.wifi_connected() is False:
                utils.wifi_connect()
            await uasyncio.sleep(30)

    async def handle_display(self):
        while True:
            if self.devices.display is None:
                return
            try:
                if self.state < 2:
                    self.devices.led_write_number(int(round(self.curr_temp * 10)), 5, [2])
                    dd = [1] if self.disp_state % 2 else []
                    if self.disp_state <= 40:
                        curr_temp = int(utils.get_config("piec_temperatura", 0))
                        self.devices.led_write_number(curr_temp, 0, dd)
                        self.devices.led_write_number(None, 2)
                        self.devices.led_write_number(None, 3)
                    elif 40 < self.disp_state <= 80:
                        val = utils.wifi_signal()
                        self.devices.led_write_number(val, 0, dd)
                    elif 80 < self.disp_state <= 120:
                        (y, m, d, hh, mm, ss, wd, yd) = utils.dst_time()
                        if hh < 10:
                            self.devices.led_write_number(0, 0, [])
                            if len(dd) == 1:
                                dd = [0]
                            self.devices.led_write_number(hh, 1, dd)
                        else:
                            self.devices.led_write_number(hh, 0, dd)
                        if mm < 10:
                            self.devices.led_write_number(0, 2, [])
                            self.devices.led_write_number(mm, 3, [])
                        else:
                            self.devices.led_write_number(mm, 2, [])

                    await self.devices.move_servo(
                        utils.map_temp_to_servo(int(utils.get_config("piec_temperatura", 40))))
                    self.disp_state += 1
                    if self.disp_state > 120:
                        self.disp_state = 0
                else:
                    if self.edit_state % 2 == 0:
                        self.devices.write_display(5, 79)
                    else:
                        self.devices.write_display(5, 0)
                    self.edit_state += 1
                    if self.edit_state > 100:
                        self.edit_state = 0
            except Exception as err:
                pass
            await uasyncio.sleep_ms(250)

    async def handle_lcd(self):
        while True:
            wait = 500
            if self.devices.lcd is None:
                return
            try:
                text = utils.czas(False, True, False)
                self.devices.write_lcd_at_pos(text, 0, 0)

                self.devices.write_lcd_at_pos("T:%2.1f" % self.curr_temp, 6, 0)
                self.devices.write_lcd_at_pos("%03d" % utils.wifi_signal(), 13, 0)

                if self.state < 2:
                    if self.lcd_state < 20:
                        if self.lcd_state == 0:
                            self.devices.write_lcd_at_pos("Piec:           ", 0, 1)
                            self.devices.write_lcd_at_pos("o", 9, 1)
                            ctemp = int(utils.get_config("piec_temperatura", 0))
                            self.devices.write_lcd_at_pos("%02d" % ctemp, 6, 1)
                            ctime = utils.get_config('piec_ostatnia_aktualizacja', '')
                            self.devices.write_lcd_at_pos(ctime[11:16], 11, 1)
                    elif self.lcd_state < 40:
                        if self.lcd_state == 20:
                            self.devices.write_lcd_at_pos("Nast.:          ", 0, 1)
                            self.devices.write_lcd_at_pos("o", 9, 1)
                            (ntime, ntemp) = self.find_next_temp()
                            if ntemp <= -1:
                                self.lcd_state = 40
                            else:
                                self.devices.write_lcd_at_pos("%02d" % ntemp, 6, 1)
                                self.devices.write_lcd_at_pos(ntime, 11, 1)

                    self.lcd_state += 1
                    if self.lcd_state >= 40:
                        self.lcd_state = 0
                else:
                    if self.lcd_state == 0:
                        self.devices.write_lcd_at_pos("Zmiana na:      ", 0, 1)
                        self.lcd_state = -1
                    elif self.lcd_state > 0:
                        self.lcd_state = 0
                    self.devices.write_lcd_at_pos("%02d" % self.edit_temp, 11, 1)
                    wait = 250
            except Exception as err:
                print(err)
            await uasyncio.sleep_ms(wait)

    async def handle_thermometer(self):
        while True:
            self.curr_temp = await self.devices.thermometer_value()
            await uasyncio.sleep_ms(500)


    def find_next_temp(self):
        times = utils.get_config("piec_czasy", {})
        if len(times) == 0:
            return "", -1
        tdt = []
        ttt = {}
        (curr_y, curr_m, curr_d, curr_hh, curr_mm, curr_ss, curr_wd, curr_yd) = utils.dst_time()
        rp = -1
        rt = ""
        if curr_y > 2000:
            cdt = utime.mktime((curr_y, curr_m, curr_d, curr_hh, curr_mm, 0, 0, 0))
            for t in times:
                th = t.split(':')[0]
                tm = int(t.split(':')[1])
                tmp = times[t]
                if th == '**':
                    dt = utime.mktime((curr_y, curr_m, curr_d, curr_hh+1, tm, 0, 0, 0))
                    tdt.append(dt)
                    ttt[dt] = tmp
                    th = curr_hh
                else:
                    th = int(th)

                if th < curr_hh or (th == curr_hh and tm < curr_mm):
                    dt = utime.mktime((curr_y, curr_m, curr_d+1, th, tm, 0, 0, 0))
                elif th == curr_hh and tm == curr_mm:
                    ctime = utils.get_config('piec_ostatnia_aktualizacja', '')
                    ctime = ctime[11:16]
                    rt = "%02d:%02d" % (curr_hh, curr_mm)
                    if ctime != rt:
                        dt = utime.mktime((curr_y, curr_m, curr_d, th, tm, 0, 0, 0))
                else:
                    dt = utime.mktime((curr_y, curr_m, curr_d, th, tm, 0, 0, 0))
                tdt.append(dt)
                ttt[dt] = tmp
            ntdt = [item for item in tdt if item >= cdt]
            closest = sorted(ntdt, key=lambda d: (d - cdt))[0]
            (curr_y, curr_m, curr_d, curr_hh, curr_mm, curr_ss, curr_wd, curr_yd) = utime.localtime(closest)
            rt = "%02d:%02d" % (curr_hh, curr_mm)
            rp = ttt[closest]
        return rt, rp

    def run(self):
        loop = uasyncio.get_event_loop()
        loop.create_task(self.set_temperature(int(utils.get_config("piec_temperatura", 40)), False))
        self.wifi_task = loop.create_task(self.handle_wifi())
        self.timer_task = loop.create_task(self.handle_timer())
        self.btn_task = loop.create_task(self.handle_button())
        self.joy_task = loop.create_task(self.handle_joystick())
        self.thermo_task = loop.create_task(self.handle_thermometer())
        self.lcd_task = loop.create_task(self.handle_lcd())
        self.display_task = loop.create_task(self.handle_display())

        self.web_task = loop.create_task(uasyncio.start_server(self.handle_web, '0.0.0.0', 80))
        loop.run_forever()


utils.load_config()
utils.wifi_disconnect()

p = Piec()
p.run()
