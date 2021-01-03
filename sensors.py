import machine
import onewire
import ds18x20
import utime
import utils
import dht


class sensory:
    def pomiar_temperatury(self, log_to_hist=False):

        termo_pin = int(utils.get_config('termometr_pin'))
        termo_res = int(utils.get_config('termometr_rozdzielczosc'))
        termo_cnt = int(utils.get_config('termometr_powtorzen'))

        temperatura = 0
        cnt = 0
        dat = machine.Pin(termo_pin)
        ds = ds18x20.DS18X20(onewire.OneWire(dat))
        roms = ds.scan()
        config = b'\x00\x00\x1f'

        for rom in roms:
            # bajty 2 3 i 4 konfiguracji
            # 2 i 3 - dane uzytkownika
            # 4 - rozdzielczosc
            if termo_res == 9:
                config = b'\x00\x00\x1f'
            if termo_res == 10:
                config = b'\x00\x00\x3f'
            if termo_res == 11:
                config = b'\x00\x00\x5f'
            if termo_res == 12:
                config = b'\x00\x00\x7f'

            ds.write_scratch(rom, config)
            cnt += 1
        for x in range(termo_cnt):
            ds.convert_temp()

            utime.sleep_ms(int(750 / (2 ** (12 - termo_res))))
            for rom in roms:
                t = ds.read_temp(rom)
                temperatura += t

        temperatura = temperatura / (termo_cnt * cnt * 1.0)
        utils.log_message('TERMOMETR: %s' % (str(temperatura)))
        if log_to_hist:
            utils.save_to_hist(temperatura, 'termometr.hist')
        return temperatura
