import threading
from types import SimpleNamespace
from http.server import ThreadingHTTPServer
from urllib.request import urlopen
from k1_ecowalk_game.app import Handler

def test_mjpeg_latest_frame_delivery():
    g=SimpleNamespace(running=True,frame_condition=threading.Condition(),frame_seq=1,lock=threading.RLock(),frame_bytes=b'jpeg-frame')
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler);server.game=g
    thread=threading.Thread(target=server.serve_forever);thread.start()
    try:
        with urlopen(f'http://127.0.0.1:{server.server_port}/stream.mjpg') as response:
            assert response.headers['Content-Type'].startswith('multipart/x-mixed-replace')
            assert response.readline()==b'--k1frame\r\n'
            assert response.readline()==b'Content-Type: image/jpeg\r\n'
            assert response.readline()==b'Content-Length: 10\r\n'
            assert response.readline()==b'\r\n'
            assert response.read(10)==b'jpeg-frame'
    finally:
        g.running=False
        with g.frame_condition:g.frame_condition.notify_all()
        server.shutdown();thread.join();server.server_close()
