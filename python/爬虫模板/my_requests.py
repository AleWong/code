import ssl
from urllib import parse
import socks
import socket
import gzip


# 解析url
def parse_urls(url):
    proto = 'http'
    up = parse.urlparse(url)
    if up.scheme != "":
        proto = up.scheme
    dst = up.netloc.split(":")
    if len(dst) == 2:
        port = int(dst[1])
    else:
        if proto == "http":
            port = 80
        elif proto == "https":
            port = 443
    host = dst[0]
    path = up.path
    query = up.query
    if path is None or path == '':
        path = '/'
    return proto, host, port, path, query


# 发送接收
def send(url, data=None, method='GET', allow_redirects=True, headers=None, timeout=None, proxies=None, encode='utf-8'):
    # 解析url
    proto, host, port, path, query = parse_urls(url)

    # 设置代理
    if proxies:
        proxy_address = proxies.split(':')[0]
        proxy_port = proxies.split(':')[1]
        socks.set_default_proxy(socks.SOCKS5, proxy_address, int(proxy_port))
        socket.socket = socks.socksocket

    # 创建套接字
    if proto == "http":
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    elif proto == "https":
        s = ssl.wrap_socket(socket.socket())

    if timeout:
        s.settimeout(timeout)

    try:
        s.connect((host, port))
    except Exception as e:
        print("error %s" % e)

    # 设置默认请求头
    if not headers:
        headers = {
            'Host': host,
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'User-Agent': 'Mozilla/5.0 (Windows NT 6.1; Win64; x64) AppleWebKit/114.86 (KHTML, like Gecko) Chrome/63.0.4341.21 Safari/352.10',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9',
            'Accept-Encoding': 'gzip, deflate',
        }

    # 构造http请求
    post_data = ""
    if method.upper() == 'POST':
        for key, value in data.items():
            post_data += "%s=%s&" % (key, value)
        if post_data.endswith('&'):
            post_data = post_data[:len(post_data) - 1]

        send_data = "POST %s" % path

        if not headers.get('Content-Type'):
            headers['Content-Type'] = 'application/x-www-form-urlencoded'

        if not headers.get('Content-Length'):
            if len(data) > 0:
                data_length = len(post_data)
            else:
                data_length = 0
            headers['Content-Length'] = str(data_length)
    else:
        send_data = "GET %s" % path

    send_data += " HTTP/1.1"
    send_data += "\r\n"
    for key, value in headers.items():
        send_data += "%s: %s" % (key, value)
        send_data += "\r\n"
    send_data += "\r\n"
    if method.upper() == 'POST':
        send_data += post_data

    s.send(send_data.encode(encode))
    read_bytes = bytes()

    # 定义响应信息容器
    response = Response()

    # 开始接收响应数据
    while True:
        receive_data = s.recv(1024)
        if not receive_data:
            break
        else:
            read_bytes += receive_data
            # 封装响应头
            if not response.headers:
                if read_bytes.find(b'\r\n\r\n') != -1:
                    response.headers = read_bytes[:read_bytes.find(b'\r\n\r\n')].decode(encode)
                    attr_lines = response.headers.split("\r\n")
                    response.headers = {}
                    for attr_lien in attr_lines:
                        attrs = attr_lien.split(":")
                        if len(attrs) == 2:
                            key = attrs[0]
                            val = attrs[1]
                            if val.startswith(" "):
                                val = val[1:]
                            response.headers[key] = val

            # 接收到尾端跳出
            if response.headers and response.headers.get('Content-Length'):
                content_length = int(response.headers.get('Content-Length'))
                if len(read_bytes[read_bytes.find(b'\r\n\r\n') + 4:]) >= content_length:
                    break
            elif read_bytes.endswith(b'\r\n0\r\n\r\n') or read_bytes.endswith(b'\r\n0\r\n\r\n\r\n'):
                break
            elif len(receive_data) == 0:
                break

    try:
        # 状态码
        response.status_code = read_bytes[:read_bytes.find(b'\r\n\r\n')].decode(encode)
        response.status_code = response.status_code[response.status_code.find(' ') + 1:response.status_code.find(' ') + 4]

        # 响应内容
        response.content = read_bytes[read_bytes.find(b'\r\n\r\n') + 4:]
        # 是否需要解压缩
        if response.headers.get('Content-Encoding') and response.headers.get('Content-Encoding').find('gzip') != -1:
            print('接收：', response.content)
            response.content = response.content[response.content.find(b'\x1f'):]
            response.content = response.content[:response.content.find(b'\x02\x00\r\n0\r\n\r\n')]

            print('开始解压缩...', response.content)
            response.content = gzip.decompress(response.content)

            print('解压缩后...', response.content)

        if len(response.content) > 16 and response.content[: 16].upper().find(b'\r\n<!DOCTYPE') != -1:
            response.content = response.content[response.content.find(b'\r\n') + 2:]
        if response.content.endswith(b'\r\n0\r\n\r\n'):
            response.content = response.content[:len(response.content) - 7]
        elif response.content.endswith(b'\r\n0\r\n\r\n\r\n'):
            response.content = response.content[:len(response.content) - 9]

        # 响应set-cookie
        response.cookies = response.headers.get('Set-Cookie')

        # 响应内容编码后
        if response.headers.get('Content-Type') and response.headers.get('Content-Type').find('html') != -1:
            response.text = response.content.decode(encode)

        # 设置重定向自动跟随
        if allow_redirects:
            count_n = 0

            while response.status_code == '302' and response.headers.get('location'):
                count_n += 1
                if count_n > 5:
                    print('重定向循环超过5次！已退出')
                    break
                location = response.headers.get('location')

                if location.startswith('http'):
                    http_url = location
                else:
                    proto, host, port, path, query = parse_urls(url)
                    while True:
                        if location.startswith("../"):
                            if path.endswith("/"):
                                path = path[:len(path) - 1]
                            path = path[:path.rfind("/")]
                            location = location[3:]
                        else:
                            break
                    if location.startswith("/"):
                        path = "/"
                    if not path.startswith("/"):
                        path = "/%s" % path
                    if not location.startswith("/"):
                        location = "/%s" % location
                    if location.startswith("/") and path.endswith("/"):
                        location = location[1:]

                    http_url = "%s://%s:%s%s%s" % (proto, host, port, path, location)
                proto, host, port, path, query = parse_urls(http_url)
                if headers:
                    headers['Host'] = host
                response = send(http_url, data=data, method=method, allow_redirects=allow_redirects, headers=headers, timeout=timeout, proxies=proxies, encode=encode)

    except Exception as e:
        raise RuntimeError(e)

    return response


# GET请求
def get(url, headers=None, allow_redirects=True, timeout=None, proxies=None, encode='utf-8'):
    return send(url, headers=headers, method='GET', allow_redirects=allow_redirects, timeout=timeout, encode=encode, proxies=proxies)


# POST请求
def post(url, data=None, headers=None, allow_redirects=True, timeout=None, proxies=None, encode='utf-8'):
    return send(url, data=data, headers=headers, method='POST', allow_redirects=allow_redirects, timeout=timeout, encode=encode, proxies=proxies)


class Response:
    headers = None
    status_code = None
    content = None
    text = None
    cookies = None


if __name__ == '__main__':
    # url = "http://47.244.17.247/"
    # url = 'http://msydqstlz2kzerdg.onion/search/'

    # proxies = '192.168.1.131:9050'
    # proxies = '192.168.1.131:1080'
    proxies = None

    data = {
        'p1': 'abc',
        'p2': '123',
    }

    # url = 'http://5u56fjmxu63xcmbk.onion/'
    url = 'https://www.baidu.com/'
    res = get(url, timeout=60, proxies=proxies)
    # res = post(url, data=data, timeout=10, proxies=proxies)
    print(res.headers)
    print(res.status_code)
    print(res.content)
    print(res.text)
    print(res.cookies)
