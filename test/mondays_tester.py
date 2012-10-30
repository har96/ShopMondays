from google.appengine.ext import webapp
import webtest
import unittest
from google.appengine.api import memcache
from google.appengine.ext import db
from google.appengine.ext import testbed

from handlers import *
from models import *

import random
import string
import logging

def getRandomS(length):
	return "".join( [string.ascii_letters[random.randrange(52)] for i in range(length)] )

class AppCase( unittest.TestCase ):
	def setUp(self):
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
		self.testapp = webtest.TestApp(app)
		self.testbed = testbed.Testbed()
		self.testbed.activate()
		self.testbed.init_datastore_v3_stub()
		self.testbed.init_memcache_stub()
	def tearDown(self):
		self.testbed.deactivate()

	@property
	def failureException(self):
	        class MyFailureException(AssertionError):
	                def __init__(self_, *args, **kwargs):
				# put failure code here
				logging.info(self.params)
				logging.info("FAILURE")
       	                        return super(MyFailureException, self_).__init__(*args, **kwargs)
	        MyFailureException.__name__ = AssertionError.__name__
	        return MyFailureException	

class TestApp( AppCase ):
	def setUp(self):
		self.users = [("Harrison", "rand345"), ("NewUser", "pwd4ls")]
		self.response = None
		super(TestApp, self).setUp()
	def testLogin(self):
		for i in xrange(1000):
			params = {"username": getRandomS(10), "password":getRandomS(7) }
			self.response = self.testapp.post("/login", params)
			if not (params["username"], params["password"]) in self.users:
				self.assertEqual(self.response.status, "200 OK")
				self.response.mustcontain("Invalid")
			else:
				self.assertEqual(self.response.status, "302 OK")
				self.response = self.response.follow()
				self.response.mustcontain("Welcome")

	def testRegistration(self):
		params = {}
		params["address1"] = params["city"] = params["username"] = params["name1"] = params["name2"] = "tester"
		params["password"] = params["verify"] = "password"
		params["zip"] = "12345"
		params["email"] = "foo@bar.com"
		params["state"] = "MS"
		for i in xrange(1000):
			key = random.choice(params.keys())
			oldval = params[key]
			params[key] = ""
			self.params = params
			self.response = self.testapp.post("/register", params)
			self.assertEqual(self.response.status, "200 OK")
			params[key] = oldval
		self.response = self.testapp.post("/register", params)
		self.assertEqual(self.response.status, "302 Moved Temporarily")


	def testSendMsg(self):
		params = {"sender":"Mondays", "receiver":"testuser", "content":"recognizable content."}
		self.login("Mondays")
		self.register("testuser")
		self.response = self.testapp.post("/message", params)

if __name__ == '__main__':
	unittest.main()
