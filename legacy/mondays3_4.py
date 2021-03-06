from google.appengine.ext import webapp
from google.appengine.ext.webapp import template
from google.appengine.ext.webapp.util import run_wsgi_app
from handlers import *

app = webapp.WSGIApplication([("/", HomePage),
				("/about", AboutPage),
				("/login(?:.json)?", LoginPage),
				("/register", Register),
				("/home(?:.json)?", UserHome),
				("/message(?:.json)?", CreateMessage),
				("/newitem", AddItem),
				("/item/([0-9]+)(?:.json)?", ItemView),
				("/edit_item/([0-9]+)", EditItem),
				("/shop(?:.json)?", Archive),
				("/request", RequestMsg),
				("/img/([0-9]+)", ItemImage),
				("/logout", Logout),
				("/activate", Activate),
				("/activate/([0-9]+)", ActivateUser),
				("/user/([a-zA-Z0-9_\-]+)(?:.json)?", UserProfile),
				("/edit_user/([0-9]+)", EditUserProfile),
				("/users(?:.json)?", AllUsers),
				("/paysuccess/([a-z0-9]+)", PaySuccess),
				("/buy/([0-9]+)", Buy),
				("/notifications(?:.json)?", AllNotifications),
				("/watch/([0-9]+)", Watch),
				("/unwatch/([0-9]+)", Unwatch),
				("/relistitem/([0-9]+)", RelistItem),
				("/payvote/([0-9]+)", MarkPayed),
				("/buyerrating/([0-9]+)", RateBuyer),
				("/sellerrating/([0-9]+)", RateSeller),
				("/resetpw/([0-9]+)", ResetPassword),
				("/commentitem/([0-9]+)", ItemComment),
				("/expire", CheckExpiration),
				("/instantbuy/([0-9]+)", InstantBuy),
				("/delcomment", DeleteComment),
				("/([0-9]+)/editcomment/([0-9]+)", EditComment),
				("/requests", ViewRequests),
				("/likerequest/([0-9]+)", Like),
				("/flag/([0-9]+)", Flag),
				("/setpassword/([0-9]+)", SetPassword),
				("/app_support", AppSupport)], debug=True)
