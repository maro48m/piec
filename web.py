import utils
import json
import sensors
import sys
from web_helper import get_header, send_chart_data2


async def send_file(writer, file_name, header):
    writer.write(get_header(header))
    bufsize = 128
    buf = None

    if sys.platform == 'esp32':
        bufsize = 4096
    try:
        #print('SEND FILE', file_name)

        await utils.lock_file(file_name)
        #print('SEND FILE - locked')
        with open(file_name, 'r') as fi:
            while 1:
                buf = fi.read(bufsize)
                if buf == '':
                    break
                else:
                    writer.write(buf.encode('utf8'))
                    await writer.drain()
                del buf
                buf = None
            fi.close()

    except Exception as eee:
        # utils.log_message('BLAD ODCZYTU PLIKU %s' % file_name, 2)
        utils.log_exception(eee, 2)

    utils.unlock_file(file_name)
    #print('SEND FILE - unlocked')
    if buf is not None:
        del buf
    return True


async def handle_api(writer, request):
    if request["url"].find("/api/dane.json") > -1:

        termometr = sensors.Sensory()
        dane = utils.get_data()
        dane["termometr"] = await termometr.pomiar_temperatury()
        del termometr

        writer.write(get_header('application/json'))
        writer.write(json.dumps(dane).encode('utf-8'))
        await writer.drain()
    elif request["url"].find("/api/clear/logs") > -1:
        await utils.remove_hist(4)
        writer.write(get_header('application/json'))
        writer.write('{"result":"Historia wyczyszczona"}'.encode('utf-8'))
        await writer.drain()
    elif request["url"].find("/api/clear/hist_piec") > -1:
        await utils.remove_hist(1)
        writer.write(get_header('application/json'))
        writer.write('{"result":"Historia wyczyszczona"}'.encode('utf-8'))
        await writer.drain()
    elif request["url"].find("/api/clear/hist_termo") > -1:
        await utils.remove_hist(2)
        writer.write(get_header('application/json'))
        writer.write('{"result":"Historia wyczyszczona"}'.encode('utf-8'))
        await writer.drain()
    elif request["url"].find("/api/clear/all") > -1:
        await utils.remove_hist(7)
        writer.write(get_header('application/json'))
        writer.write('{"result":"Historia wyczyszczona"}'.encode('utf-8'))
        await writer.drain()
    elif request["url"].find("/api/params_get.json") > -1:
        writer.write(get_header('application/json'))
        writer.write(json.dumps(utils.config).encode('utf-8'))
        await writer.drain()
    elif request["url"].find("/api/params_save") > -1:
        utils.update_config(request["body"].decode('utf-8'))
        writer.write(get_header('application/json'))
        writer.write('{"result":"Parametry zapisane"}'.encode('utf-8'))
        await writer.drain()
    elif request["url"].find("/api/logs") > -1:
        await send_file(writer, 'log.txt', 'text/plain')
    elif request["url"].find("/api/hist_piec") > -1:
        await send_file(writer, 'piec.hist', 'text/plain')
    elif request["url"].find("/api/hist_termo") > -1:
        await send_file(writer, 'termometr.hist', 'text/plain')
    elif request["url"].find("/api/chart.json") > -1:
        writer.write(get_header('application/json'))
        await send_chart_data2(writer)
    elif request["url"].find("/api/reboot") > -1:
        writer.write('{"response":"Urządzenie się restartuje. Konieczne przeładowanie strony"}'.encode('utf-8'))
        await writer.drain()
        writer.close()
        await writer.wait_closed()
        import uasyncio
        await uasyncio.sleep_ms(500)
        import machine
        machine.reset()
    elif request["url"].find("/api/file") > -1:
        writer.write(get_header('application/json'))
        if upload_file(request):
            writer.write('{"response":"Aktualizacja pomyślna"}'.encode('utf-8'))
        else:
            writer.write('{"response":"Błąd aktualizacji"}'.encode('utf-8'))
        await writer.drain()
        if request["body"]["reboot"] == "on" and int(request["body"]["chunk"]) == int(request["body"]["chunks"]):
            import machine
            machine.reset()
    return True


def upload_file(request):
    print(request)
    if "file_name" in request["body"].keys():
        f = open(request["body"]["file_name"], "ab+")
        f.write(request["body"]["file"])
        f.close()
        return True
    else:
        return False
