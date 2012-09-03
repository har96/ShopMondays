import unittest
from google.appengine.api import memcache
from google.appengine.ext import db
from google.appengine.ext import testbed

class TestRegister( unittest.TestCase ):

	def setUp(self):
		self.testbed = testbed.TestBed()
		self.testbed.activate()
		self.testbed.init_datastore_v3_stub()
	def tearDown(self):
		self.testbed.deactivate()

if __name__ == '__main__':
	unittest.main()
