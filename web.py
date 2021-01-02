import utils


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
