# -*- coding: utf8 -*-
from gevent import monkey
monkey.patch_socket()
import gevent
import socket
import re
import urlparse
import os
import mimetypes
import re


def parser_http_headers(header_text):
    '''
     @:brief 解析http请求头部
     @:return 请求字典
    '''
    reg = re.compile('(?P<method>\S*)\s+(?P<full_query_string>\S*)\s+(?P<version>\S*)')
    header_dict_result = reg.match(header_text)
    if header_dict_result is None:
        return None

    header_dict = header_dict_result.groupdict()
    parser_result = urlparse.urlparse(header_dict['full_query_string'])
    header_dict['path'] = parser_result.path
    header_dict['query_string'] = parser_result.query
    query = dict([(k, v[0]) for k, v in urlparse.parse_qs(parser_result.query).items()])
    header_dict['query'] = query

    reg = re.compile('(?P<key>\S*)\s*:\s*(?P<value>[^\r\n]*)')
    nn_index = header_text.index('\n')
    while True:
        try:
            base = header_text[nn_index+1:].index('\n')
            if nn_index < 0:
                break
        except ValueError:
            break

        key_value_dict_result = reg.match(header_text[nn_index+1:])
        if key_value_dict_result is None:
            break

        nn_index += base + 1

        key_value_dict = key_value_dict_result.groupdict()
        header_dict[key_value_dict['key']] = key_value_dict['value']

    return header_dict


# 协程化的TCP服务器
class PyTcpServer(object):
    def __init__(self, iface, serve_port, peer_callback):
        self.iface = iface
        self.serve_port = serve_port
        self.die = False
        # 服务纤程句柄
        self.green_let = None
        # 连接的句柄
        self.peer_green_let_list = []
        # 连接处理句柄
        self.peer_callback_main = peer_callback

        self.__startup()

    # TCP服务过程
    def tcp_server_main(self, srv):
        print 'server running...'
        while self.die is False:
            try:
                peer_conn, peer_addr = srv.accept()
            except Exception, e:
                break

            peer_green_let = gevent.spawn(self.peer_callback_main, peer_conn, peer_addr)
            self.peer_green_let_list.append(peer_green_let)

        print 'server shutduwn...'
        srv.close()

    # 启动服务器
    def __startup(self):
        s = socket.socket()
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, True)
        s.bind((self.iface, self.serve_port))
        s.listen(15)
        # 获取服务线程的句柄
        self.green_let = gevent.spawn(self.tcp_server_main, s)
        print "server startup done @", (self.iface, self.serve_port)

    def shutdown(self):
        pass

    # 休眠指定的毫秒数
    @staticmethod
    def update_idle(sleep_by_ms=None):
        if sleep_by_ms is None:
            sleep_by_ms = 50
        gevent.sleep(sleep_by_ms / 1000.0)


# 路径路由对象
class PathRoute:
    def __init__(self, path_re, methods):
        self.path_re = re.compile(path_re)
        if isinstance(methods, set):
            self.methods = methods
        elif isinstance(methods, str):
            self.methods = [methods]
        else:
            self.methods = {'GET', 'POST'}

        self.callback = None

    def peer_callback(self, callback):
        self.callback = callback


# 协程化的HTTP服务器
class PyHttpd(PyTcpServer):
    def __init__(self, iface, serve_port):
        super(PyHttpd, self).__init__(iface, serve_port, self.http_peer_main)
        # 注册的路由表
        self.route_map = []

    # HTTP连接处理过程
    def http_peer_main(self, conn, addr):
        print 'new connection from', addr
        http_request_header, http_request_body = '', ''

        try:
            rn_rn_index, nn_index = -1, -1
            while rn_rn_index < 0 and nn_index < 0 and len(http_request_header) < 2000:
                new_coming = conn.recv(1024)
                if new_coming is None or len(new_coming) == 0:
                    break

                http_request_header = http_request_header + new_coming

                try:
                    rn_rn_index = http_request_header.index('\r\n\r\n')
                except ValueError:
                    rn_rn_index = -1

                try:
                    nn_index = http_request_header.index('\n\n')
                except ValueError:
                    nn_index = -1

            # 请求数据中未发现连续的两个换行， 则认为是异常请求
            if rn_rn_index < 0 and nn_index < 0:
                print("invalid http request from", addr)
                conn.close()
                return

            # 计算请求头部分割点的位置
            split_index = rn_rn_index + 2 if rn_rn_index > 0 else nn_index + 2

            # 将可能的请求数据体存储到请求数据结构中
            http_request_body = http_request_header[split_index:]
            http_request_header = http_request_header[:split_index]

            # 解析本次请求的头部
            http_query = parser_http_headers(http_request_header)
            if http_query is None:
                raise TypeError('invalid http request.')

            http_query['method'] = http_query['method'].upper()
            request_method = http_query['method']
            if request_method == 'GET':
                pass
            elif request_method == 'POST':
                print http_query['Content-Type']
                print http_query['Content-Length']
            else:
                print("reqiest method" + request_method + " not supperted")
                conn.close()
                return

            print http_query

            server_profile = None
            www_root = os.getcwd() + '/www'
            request_file_full_path = www_root + http_query['path']

            self.route_url(conn, addr, http_query, www_root)
        except Exception, e:
            print("link losed connection from", addr, e)
            conn.close()
            return

        print('process done, connection from', addr)
        conn.close()

    # 路由处理URL
    def route_url(self, conn, addr, http_query, www_root):
        for r in self.route_map:
            if http_query['method'] not in r.methods:
                continue
            if r.path_re.match(http_query['path']) is None:
                continue

            # 执行回调
            r.callback(conn, addr, http_query)

            return True

        return False

    # 注册路由路径
    def route(self, *arg, **kwargs):
        path = arg[0]
        try:
            methods = kwargs['methods']
        except Exception, e:
            methods = {'GET', 'POST'}

        route = PathRoute(path, methods)
        self.route_map.append(route)
        return route.peer_callback


if __name__ == '__main__':
    import time

    thttpd = PyHttpd('0.0.0.0', 9999)

    @thttpd.route('/.+', methods={'POST'})
    def index_html(conn, addr, query):
        print 'hahaha', addr
        gevent.sleep(5)
        print 'doneeeeee', addr

    @thttpd.route('/.+html', methods={'GET'})
    def index_html(conn, addr, query):
        print 'hahaha11111'

    while True:
        thttpd.update_idle()
