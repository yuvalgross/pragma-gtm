import http.server,json
class H(http.server.BaseHTTPRequestHandler):
    def do_POST(s):
        b=s.rfile.read(int(s.headers.get('content-length',0)))
        open('/tmp/n8ntest/req.json','w').write(json.dumps({'path':s.path,'headers':{k:v for k,v in s.headers.items() if k.lower() in('apikey','authorization','content-profile','prefer','content-type')},'rows':len(json.loads(b)),'sample':json.loads(b)[0]},indent=1))
        s.send_response(201 if s.headers.get('apikey')=='testkey' else 401);s.end_headers()
    def log_message(*a):pass
http.server.HTTPServer(('127.0.0.1',8899),H).serve_forever()
