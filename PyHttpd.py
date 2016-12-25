# -*- coding: UTF-8 -*-
__author__ = 'lijie'
import socket
import select
import time
import traceback


class PyHttpRequest:
    def __init__(self):
        self.head_rx = ''
        self.body_rx = ''
        self.methord = None
        self.query_string = None
        self.http_version = None
        self.request_head_done = False

    def on_read(self, data):
        # put data into head while head not done.
        if self.request_head_done is False:
            self.head_rx = self.head_rx + data
        else:
            self.body_rx = self.body_rx + data

        if self.request_head_done is False:
            delimiter_index = self.head_rx.find('\r\n\r\n')
            if delimiter_index > 0:
                self.head_rx = self.head_rx[:delimiter_index]
                self.body_rx = self.head_rx[delimiter_index+4:]
                self.request_head_done = True

        if self.request_head_done and self.methord is None:
            self.head_rx = self.head_rx.replace('\r', '')
            self.head_rx = self.head_rx.split('\n')
            first_line = self.head_rx[0]
            first_line = first_line.split(' ')
            if len(first_line) != 3:
                return True
            self.methord = first_line[0]
            self.query_string = first_line[1]
            self.http_version = first_line[2]
            print self.methord, self.query_string, self.http_version
            return True

        return False

    '''
        test is request head recieved done
    '''
    def is_request_ok(self):
        if self.methord is None:
            return False
        if self.query_string is None:
            return False
        if self.http_version is None:
            return False
        return self.request_head_done


class PyHttpResponds:
    def __init__(self, request):
        self.request = None

    def on_write(self):
        return None

    def is_need_write(self):
        return False


class PyHttpClient:
    def __init__(self, fds, address):
        self.fds = fds
        self.address = address
        self.born = time.time()
        self.request = None
        self.responds = None

    '''
        @brief test is client need read data in.
        @retval False there is no any need.
        @retval True need read data in.
    '''
    def is_need_read(self):
        # always need read to detect connection close.
        return True

    '''
        @brief test is client need write data out.
        @retval False there is no any need.
        @retval True need write data out.
    '''
    def is_need_write(self):
        if self.request is None:
            return False

        if self.request.is_request_ok() is False:
            return False

        if self.responds is None:
            return False

        return self.responds.is_need_write()

    '''
        @brief read data in through connected socket
        @retval True read procedure complete, need close socket.
        @retval False read procedure not complete
    '''
    def on_read(self):
        try:
            data = self.fds.recv(1024)
        except Exception, e:
            print e
            traceback.format_exc()
            return True

        if self.request is None:
            self.request = PyHttpRequest()

        return self.request.on_read(data)

    '''
        @brief write data out through connected socket
        @retval True write procedure complete, need close socket.
        @retval False write procedure not complete
    '''
    def on_write(self):
        if self.request is None:
            return False

        if self.respons is None:
            # initialize responds object flow request
            self.responds = PyHttpResponds(self.request)

        data = self.responds.on_write()
        if data is None:
            return False

        try:
            self.fds.send(data)
        except Exception, e:
            print e
            traceback.format_exc()
            return True

        return False

    '''
        @brief event of client destroy will come to here.
    '''
    def on_close(self):
        pass

    '''
        @brief you can do client business here
        @retval business complete, need close socket.
        @retval False business not complete
    '''
    def on_rolling(self):
        # connection will timeout if no data recieved in 30s.
        if self.request is None and time.time() - self.born > 5.0:
            return True
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
            self.fds.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
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