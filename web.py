import utils
import json
import sensors

def send_file(socket, file_name, mode='r'):
    try:
        with open(file_name, mode) as fi:
            while True:
                buf = fi.read(512)
                if str(buf) == '':
                    break
                else:
                    socket.sendall(buf)
            fi.close()
    except Exception as eee:
        utils.log_message('WWW FILE ERROR %s' % file_name)


def get_header(mime_type):
    return "HTTP/1.1 200OK\n" + "Content-Type: %s\n" % mime_type + "Connection: close\n\n"


def handle_api(socket, request):
    if request.find("/api/dane.json") > -1:
        termometr = sensors.sensory()
        dane = {}
        dane["czas"] = utils.czas()
        dane["termometr"] = termometr.pomiar_temperatury()
        dane["temperatura"] = int(utils.get_config('piec_temperatura', 40))
        dane["ostatnia_zmiana"] = utils.get_config('piec_ostatnia_aktualizacja', '')
        times = utils.get_config('piec_czasy', {})
        tm = ''
        for t in sorted(times):
            tm += t + ' - ' + str(times[t]) + '\n'

        dane["harmonogram"] = tm
        socket.sendall(get_header('application/json'))
        socket.sendall(json.dumps(dane))
    elif request.find("/api/clear/logs") > -1:
        socket.sendall(get_header('text/plain'))
        utils.remove_hist(4)
        socket.sendall('OK')
    elif request.find("/api/clear/hist_piec") > -1:
        socket.sendall(get_header('text/plain'))
        utils.remove_hist(1)
        socket.sendall('OK')
    elif request.find("/api/clear/hist_termo") > -1:
        socket.sendall(get_header('text/plain'))
        utils.remove_hist(2)
        socket.sendall('OK')
    elif request.find("/api/clear/all") > -1:
        socket.sendall(get_header('text/plain'))
        utils.remove_hist(7)
        socket.sendall('OK')
    elif request.find("/api/config") > -1:
        socket.sendall(get_header('application/json'))
        socket.sendall(json.dumps(utils.config))
    elif request.find("/api/logs") > -1:
        socket.sendall(get_header('text/plain'))
        send_file(socket, 'log.txt', 'r')
    elif request.find("/api/hist_piec") > -1:
        socket.sendall(get_header('text/plain'))
        send_file(socket, 'piec.hist', 'r')
    elif request.find("/api/hist_termo") > -1:
        socket.sendall(get_header('text/plain'))
        send_file(socket, 'termometr.hist', 'r')
    return True
