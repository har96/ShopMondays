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

CONDITIONS = ["New; Unopen unused", "Used; still in perfect condition", "Used; has some wear", "Old; still good as new"]
SHIP_OPTS = ["on", "off", "pickup"]

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
				logging.info("FAILURE")
       	                        return super(MyFailureException, self_).__init__(*args, **kwargs)
	        MyFailureException.__name__ = AssertionError.__name__
	        return MyFailureException	

class TestApp( AppCase ):
	def setUp(self):
		self.users = [("Harrison", "rand345"), ("NewUser", "pwd4ls")]
		self.response = None
		super(TestApp, self).setUp()
	def list_item(self, login_cookie):
		response = self.testapp.post("/newitem", {"title":"tester", "description":"...",
							"startprice":"12", "days_listed":"1",
							"shipdays":"1", "shipprice":"1.25",
							"localpickup":"on", "condition":"New; Unopen unused"},
							headers={"Cookie":login_cookie})
		try:
			item_page = response.follow()
		except Exception, e:
			raise AssertionError("newitem page did not redirect: %s\n%s" % (e, response))
		url = item_page.request.url + ".json" # get json format of item page
		return "4"
	def login(self, username):
		response = self.testapp.post("/login", {"username":username, "password": "pass"})
		# return cookie
		return response.headers.get("Set-Cookie", False)
	def register(self, username):
		params = {}
		params["username"] = username
		params["password"] = params["verify"] = "pass"
		params["address1"] = params["city"] = params["name1"] = params["name2"] = "tester"
		params["state"] = "MS"
		params["zip"] = "39086"
		params["email"] = "foo@bar.com"
		self.response = self.testapp.post("/register", params)
	def testLogin(self):
		for i in xrange(1000):
			params = {"username": getRandomS(10), "password":getRandomS(7) }
			self.response = self.testapp.post("/login", params)
			if not (params["username"], params["password"]) in self.users:
				self.assertEqual(self.response.status, "200 OK")
				try:
					self.response.mustcontain("Invalid")
				except:
					raise AssertionError("Did not refuse correctly")
			else:
				self.assertEqual(self.response.status, "302 OK")
				self.response = self.response.follow()
				try:
					self.response.mustcontain("Welcome")
				except:
					raise AssertionError("Did not redirect correctly")

	def testRegistration(self):
		params = {}
		params["address1"] = params["city"] = params["username"] = params["name1"] = params["name2"] = "tester"
		params["password"] = params["verify"] = "password"
		params["zip"] = "12345"
		params["email"] = "foo@bar.com"
		params["state"] = "MS"
		for i in xrange(500):
			key = random.choice(params.keys())
			oldval = params[key]
			params[key] = ""
			self.response = self.testapp.post("/register", params)
			self.assertEqual(self.response.status, "200 OK")
			params[key] = oldval

class TestLogin( AppCase ):
	def list_item(self, login_cookie):
		response = self.testapp.post("/newitem", {"title":"tester", "description":"...",
							"startprice":"12", "days_listed":"1",
							"shipdays":"1", "shipprice":"1.25",
							"localpickup":"on", "condition":"New; Unopen unused"},
							headers={"Cookie":login_cookie})
		try:
			item_page = response.follow()
		except Exception, e:
			raise AssertionError("newitem page did not redirect: %s\n%s" % (e, response))
		url = item_page.request.url + ".json" # get json format of item page
		return "4"
	def login(self, username):
		response = self.testapp.post("/login", {"username":username, "password": "passing"})
		# return cookie
		logging.info(response.body)
		return response.headers.get("Set-Cookie", False)
	def register(self, username):
		params = {}
		params["username"] = username
		params["password"] = params["verify"] = "passing"
		params["address1"] = params["city"] = params["name1"] = params["name2"] = "tester"
		params["state"] = "ms"
		params["zip"] = "39086"
		params["email"] = "foo@bar.com"
		self.response = self.testapp.post("/register", params)

	def testSendMsg(self):
		# register needed users
		self.register("testuser")
		self.register("testuser2")
		self.register("Mondays")
		cookie = self.login("Mondays")
		self.assertTrue(cookie)

		# test sending to one receipient
		params = {"sender":"Mondays", "receiver":"testuser", "body":"recognizable content."}
		self.response = self.testapp.post("/message", params, headers={"Cookie":cookie})
		try:
			self.response.mustcontain("recognizable content.", "To:", "testuser")
		except:
			raise AssertionError("Sent message not viewable")
		cookie = self.login("testuser")
		self.assertTrue(cookie)
		self.response = self.testapp.get("/message", headers={"Cookie":cookie})
		try:
			self.response.mustcontain("recognizable content.", "Mondays")
		except:
			raise AssertionError("Did not receive message")

	def testMsg(self):
		def didSend(message_body):
			try:
				self.response.mustcontain("Message sent", "<td><pre>%s</pre></td>" % message_body)
			except:
				return False
			return True
		def didDelete(message_body):
			try:
				self.response.mustcontain(message_body)
			except:
				return True
			return False
		#register needed users
		self.register("testsender")
		self.register("testuser")
		self.register("testreceiver")
		cookie = self.login("testsender")
		self.assertTrue(cookie)

		params = {}
		params["receiver"] = "testuser testreceiver"
		params["body"] = "Content ###"
		self.response = self.testapp.post("/message", params, headers={"Cookie":cookie})
		self.assertTrue(params["body"], msg="simple message did not send")
		
		# make sure it refuses without receiver
		params["receiver"] = ""
		self.response = self.testapp.post("/message", params, headers={"Cookie":cookie})
		self.assertFalse(didSend(params["body"]), msg="Did not refuse message without receiver")
		params["receiver"] = "testuser"
		# make sure if refuses without content
		params["body"] = ""
		self.response = self.testapp.post("/message", params, headers={'Cookie':cookie})
		self.assertFalse(didSend(""), msg="Did not refuse message without content")
		params["body"] = ""

		# test deleting
		 #single message
		self.response = self.testapp.post("/message", {"delete_mes":"10"}, {"Cookie":cookie})
		self.assertTrue(didDelete("Content ###"), msg="Failed to delete")
		 #invalid message
		  #set up
		self.response = self.testapp.post("/message", {"receiver":"testuser", "body":"recognize"}, {"Cookie":cookie})
		self.assertTrue(didSend("recognize"), msg="message to single receiver did not send. reason: %s" % self.response.body)
		  #test
		self.response = self.testapp.post("/message",{"delete_msg":"4"})
		self.assertFalse(didDelete("recognize"), msg="Invalid ID")



	def testEditItem(self):
		self.register("testuser")
		cookie = self.login("testuser")
		self.assertTrue(cookie)
		conditions = ["New; Unopen unused", "Used; still in perfect condition", "Used; has some wear", "Old; still good as new"]
		shipping_opts = ["on", "off", "pickup"]

		id = self.list_item(cookie)
		params = {}
		params["title"] = params["description"] = "tester"
		params["price"] = params["shipprice"] = "42.12"
		params["localpickup"] = "off"
		params["condition"] = conditions[1]
		for i in xrange(100):
			key = random.choice(params.keys())
			oldval = params[key]
			params[key] = ""
			self.response = self.testapp.post("/edit_item/%s" % id, params, headers={"Cookie":cookie})
			self.assertEqual(self.response.status, "200 OK")
			params[key] = oldval
		# make sure ship price can be empty if shipping option is pickup
		params["localpickup"] = "pickup"
		params["shipprice"] = ""
		self.response = self.testapp.post("/edit_item/%s" % id, params, headers={"Cookie":cookie})
		self.assertEqual(self.response.status, "302 Moved Temporarily")
		params["localpickup"] = "off"
		params["shipprice"] = "1.24"
		for i in xrange(300):
			byte_string = os.urandom(16)
			params["condition"] = byte_string
			self.response = self.testapp.post("/edit_item/%s" % id, params, headers={"Cookie":cookie})
			self.assertEqual(self.response.status, "200 OK")
			params["condition"] = conditions[2]
			params["localpickup"] = byte_string
			self.response = self.testapp.post("/edit_item/%s" % id, params, headers={"Cookie":cookie})
			self.assertEqual(self.response.status, "200 OK")
			params["localpickup"] = shipping_opts[1]
			params["condition"] = conditions[2]

	def testAddItem(self):
		self.register("testuser")
		cookie = self.login("testuser")
		self.assertTrue(cookie)

		params = {}
		params["title"] = params["description"] = "tester"
		params["startprice"] = "12.25"
		params["days_listed"] = params["shipdays"] = "1"
		params["localpickup"] = "off"
		params["condition"] = CONDITIONS[1]
		for i in xrange(400):
			key = random.choice(params.keys())
			oldval = params[key]
			params[key] = ""
			self.response = self.testapp.post("/newitem", params, headers={"Cookie":cookie})
			self.assertEqual(self.response.status, "200 OK", msg="Handler accepted an empty %s argument" % key)
			params[key] = oldval

		# make sure ship price can be empty if shipping option is pickup
		params["localpickup"] = "pickup"
		params["shipprice"] = ""
		self.response = self.testapp.post("/newitem", params, headers={"Cookie":cookie})
		self.assertEqual(self.response.status, "302 Moved Temporarily")
		params["localpickup"] = "off"
		params["shipprice"] = "1.24"
		for i in xrange(100):
			byte_string = os.urandom(16)
			params["condition"] = byte_string
			self.response = self.testapp.post("/newitem", params, headers={"Cookie":cookie})
			self.assertEqual(self.response.status, "200 OK", msg="handler accepted %s as condition arg" % byte_string)
			params["condition"] = CONDITIONS[2]
			params["localpickup"] = byte_string
			self.response = self.testapp.post("/newitem", params, headers={"Cookie":cookie})
			self.assertEqual(self.response.status, "200 OK", msg="handler accepted %s as local_pickup arg" % byte_string)
			params["localpickup"] = SHIP_OPTS[1]
			params["condition"] = CONDITIONS[2]

	def testEditUser(self):
		self.register("testuser")
		cookie = self.login("testuser")
		self.assertTrue(cookie)

		params = {}
		params["name1"] = params["name2"] = params["city"] = params["address1"] = "tester"
		params["state"] = "MS"
		params["zip"] = "39086"
		for key in params.keys():
			oldval = params[key]    # save old value
			params[key] = "" 	# replace with empty string
			self.response = self.testapp.post("/edit_user/1", params, headers={"Cookie":cookie})
			self.assertEqual(self.response.status, "200 OK", msg="Handler accepted an empty %s argument" % key)
			params["key"] = oldval

		params["zip"] = "123"
		self.response = self.testapp.post("/edit_user/1", params, headers={"Cookie":cookie})
		self.assertEqual(self.response.status, "200 OK", msg="Accepted invalid length zip")
		
		params["zip"] = "hello world"
		self.response = self.testapp.post("/edit_user/1", params, headers={"Cookie":cookie})
		self.assertEqual(self.response.status, "200 OK", msg="Accepted invalid zip")

		params["zip"] = "39086"

		params["state"] = "ZZ"
		self.response = self.testapp.post("/edit_user/1", params, headers={"Cookie":cookie})
		self.assertEqual(self.response.status, "200 OK", msg="Accepted invalid state")

	def testBid(self):
		self.register("seller")
		cookie = self.login("seller")
		id = self.list_item(cookie)
		self.register("buyer")
		cookie = self.login("buyer")

		url = "/item/%s" % id

		self.response = self.testapp.post(url, {"price":"11"}, headers={"Cookie":cookie})
		self.assertEqual(self.response.status, "200 OK", msg="Allowed bid of lower price")

		self.response = self.testapp.post(url, {'price': '12'}, headers={'Cookie':cookie})
		self.assertEqual(self.response.status, '302 Moved Temporarily', msg="Disallowed first bid of equal price")

		self.response = self.testapp.post(url, {'price': '12'}, headers={'Cookie':cookie})
		self.assertEqual(self.response.status, '202 OK', msg="bid margin not properly updated")

		self.response = self.testapp.post(url, {'price': '13'}, headers={'Cookie':cookie})
		self.assertEqual(self.response.status, '302 Moved Temporarily', msg="Did not allow second bid on item")

		self.response = self.testapp.post(url, {'price': '13.25'}, headers={'Cookie':cookie})
		self.assertEqual(self.response.status, '200 OK', msg="Did not correctly update or apply bid margin")



if __name__ == '__main__':
	unittest.main()
