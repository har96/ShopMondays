from google.appengine.ext import webapp
from google.appengine.ext.webapp import template
from google.appengine.ext.webapp.util import run_wsgi_app
from handlers import *

webapp.template.register_template_library("templatetags.custom")
			
app = webapp.WSGIApplication([("/", HomePage),
				("/about", AboutPage),
				("/login", LoginPage),
				("/register", Register),
				("/home", UserHome),
				("/message", CreateMessage),
				("/newitem", AddItem),
				("/item/([0-9]+)", ItemView),
				("/edit_item/([0-9]+)", EditItem),
				("/shop", Archive),
				("/request", RequestMsg),
				("/img/([0-9]+)", ItemImage),
				("/img_msg", MsgImage),
				("/logout", Logout),
				("/activate", Activate),
				("/activate/([0-9]+)", ActivateUser),
				("/user/([0-9]+)", UserProfile),
				("/edit_user/([0-9]+)", EditUserProfile),
				("/users", AllUsers)], debug=True)

def main():
	run_wsgi_app(app)

if __name__ == "__main__":
	main()
