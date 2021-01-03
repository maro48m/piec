import utils
import json
import sensors

def send_file(socket, file_name, mode='r'):
    try:
        with open(file_name, mode) as fi:
            while True:
                buf = fi.read(1024)
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

_hextobyte_cache = None

def unquote(string):
    """unquote('abc%20def') -> b'abc def'."""
    global _hextobyte_cache

    # Note: strings are encoded as UTF-8. This is only an issue if it contains
    # unescaped non-ASCII characters, which URIs should not.
    if not string:
        return b''

    if isinstance(string, str):
        string = string.encode('utf-8')

    bits = string.split(b'%')
    if len(bits) == 1:
        return string

    res = [bits[0]]
    append = res.append

    # Build cache for hex to char mapping on-the-fly only for codes
    # that are actually used
    if _hextobyte_cache is None:
        _hextobyte_cache = {}

    for item in bits[1:]:
        try:
            code = item[:2]
            char = _hextobyte_cache.get(code)
            if char is None:
                char = _hextobyte_cache[code] = bytes([int(code, 16)])
            append(char)
            append(item[2:])
        except KeyError:
            append(b'%')
            append(item)

    return b''.join(res)


def parse_request(request):
    if request == b'':
        return ''
    lines = request.split(b'\r\n')
    urls = lines[0].split(b' ')
    url = unquote(urls[1])
    return url.decode('ascii')
