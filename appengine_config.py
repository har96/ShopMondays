import sys
sys.path.append("lib/packages")
from gaesessions import SessionMiddleware
from google.appengine.ext.appstats import recording

def webapp_add_wsgi_middleware(app):
	# apply session middleware
	key = "'\\x15\\xbb\\x04]\\x87z\\x19\\xe5\\xb6(\\x19\\xc8c:I\\x83t\\xfbw\\ti\\x1c^`\\xa4\\x05\\x16\\x7f\\xce\\xff\\x98\\xac-vDj{x~\\xa9V\\x07\\x1e\\xebG\\x82\\xc4\\xef\\x0f\\xdd\\xc6\\xb0O!\\r\\xcf\\xd4\\xbb\\xb3^\\x16\\n\\x1a@'"
	app = SessionMiddleware(app, cookie_key=key, cookie_only_threshold=0)
	# apply appstats middleware
	app = recording.appstats_wsgi_middleware(app)
	return app
