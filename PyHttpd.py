# -*- coding: UTF-8 -*-
__author__ = 'lijie'
import socket
import select
import time
import traceback


class PyHttpRespons:
    def __init__(self):
        pass


class PyHttpRequest:
    def __init__(self):
        self.rx = []

    def on_recv(self, data):
        pass

    def is_request_ok(self):
        return False


class PyHttpClient:
    def __init__(self, fds, addr):
        self.fds = fds
        self.addr = addr
        self.born = time.time()
        self.request = None
        self.respons = None

    def is_need_read(self):
        # always need read to detect connection close.
        return True

    def is_need_write(self):
        if self.request is None:
            return False

        if self.request.is_request_ok() is False:
            return False

        if self.respons is None:
            return False

        return self.respons.is_need_write()

    def on_read(self):
        try:
            data = self.fds.recv(1024)
        except Exception, e:
            print e
            traceback.format_exc()
            return False

        if self.request is None:
            self.request = PyHttpRequest()
        else:
            self.request.on_recv(data)

        return True

    def on_write(self):
        pass

    def on_close(self):
        pass

    def on_rolling(self):
        # connection will timeout if no data recieved in 30s.
        if self.request is None and time.time() - self.born > 30.0:
            return False


'''
    @brief PyHttpd class defination

    @param server_address server bind address information, default '127.0.0.0'
    @param server_port server bind port information, default 9999
'''
class PyHttpd:
    def __init__(self, server_address=None, server_port=None):
        if server_address is None:
            server_address = '127.0.0.1'
        if server_port is None:
            server_port = 9999

        self.server_address = server_address
        self.server_port = server_port

    '''
        @brief start the http server
    '''
    def start(self):
        self.fds = socket.socket()
        try:
            self.fds.bind((self.server_address, self.server_port))
        except Exception, e:
            print e
            traceback.format_exc()

        self.fds.listen(64)
        self.clients = []
        self.route = []

    '''
    '''
    def run_server_step(self, time_to_wait=None):
        if time_to_wait is None:
            time_to_wait = 0.5
        rlist, wlist = [self.fds], []

        for client in self.clients:
            if client.is_need_read() is True:
                rlist.append(client.fds)
            if client.is_need_write() is True:
                wlist.append(client.fds)

        try:
            r, w, _ = select.select(rlist, wlist, [], time_to_wait)
        except Exception, e:
            print e
            traceback.format_exc()
            return False

        client_closed = []
        for client in self.clients:
            connection_closed = False

            # do client I/O
            if client.fds in r:
                connection_closed = client.on_read()
            if client.fds in w and connection_closed is False:
                connection_closed = client.on_write()

            # do client process
            if connection_closed is False:
                connection_closed = client.on_rolling()

            # client will be closed
            if connection_closed is True:
                client_closed.append(client)

        # remove client from clients list.
        for client in client_closed:
            self.clients.remove(client)
            client.on_close()
            if client.fds is not None:
                client.fds.close()

        # process new connection
        if self.fds in r:
            try:
                conn, addr = self.fds.accept()
            except Exception, e:
                print e
                traceback.format_exc()
                return False

            client = PyHttpClient(conn, addr)
            self.clients.append(client)

        return True