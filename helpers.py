# note: this module only works for python 2.5, unless
# provided with a later version of bcrypt
import sys
sys.path.append("packages")

from pytz.gae import pytz
from pytz import timezone
import time
import hashlib
from datetime import datetime
import random
import string
import re
import py_bcrypt.bcrypt as bcrypt
from functools import update_wrapper
import logging

from google.appengine.api import images
from google.appengine.api import memcache
from google.appengine.ext import db

PAYPAL = "https://svcs.sandbox.paypal.com/AdaptivePayments/API_operation"

MEMCACHE_LEN = 15

USER_RE = re.compile("^[a-zA-Z0-9_-]{3,20}$")
PASSWORD_RE = re.compile("^.{4,20}$")
EMAIL_RE = re.compile(r"\S+@\S+\.\S+")
def valid_username(username):
	return USER_RE.match(username)
def valid_password(password):
	return PASSWORD_RE.match(password)
def valid_email(email):
	return EMAIL_RE.match(email)
def make_salt():
	return "".join([random.choice(string.ascii_letters) for i in xrange(5)])
def hash_str(s):
	""" sha256 hash of s """
	return hashlib.sha256(s).hexdigest()
def encrypt_str(s, salt):
	""" if not salt, returns a tuple containing
	(hash, salt) else returns hash(s) """
	hash = hash_str( bcrypt.hashpw( hash_str( hash_str(s) ), salt) )
	return hash
def hash_user_info(name, password, pepper=None, salt=None):
	if not pepper:
		pepper = bcrypt.gensalt()
	if not salt:
		salt = make_salt()
	return encrypt_str(name+password+salt, pepper), salt, pepper
def users_match(user, hashed_password):
	return user and user.password == hashed_password
def find_month_lim(month, year):
	"""returns the number of days in a particular month"""
	if month == 2:
		if (year - 1900)%4:
			return 28
		else:
			return 29
	return 31 if month < 8 and month%2 \
		or month > 7 and not month%2 \
		else 30

def gen_date2(day_offset=0):
	assert day_offset < 25, "day_offset must be less than 25"
	z = timezone('US/Central')
	tme = datetime.now(z)
	tmelist = list(tme.timetuple())
	tmelist[2] += day_offset
	lim = find_month_lim(tme.month, tme.year)
	if tmelist[2] > lim:
		tmelist[1] += 1
		tmelist[2] -= lim
	return datetime(*tmelist[:-3])

def has_whitespace(s):
	for c in s:
		if c == " ":
			return True
	return False
def create_image(image, width=None, height=None):
	if width and height:
		image = images.resize(image, width, height)
	return db.Blob(str(image))
def send_email_to_user(user, subject, content):
	mail.send_mail(sender="harrison@hunterhayven.com",
			to=user.email,
			subject=subject,
			body=content)
def decorator(f):
	""" return f as a decorator with update_wrapper.

	    thanks to Darius Bacon for the code: 
		    https://github.com/darius/sketchbook/blob/master/misc/decorator.py"""
	return lambda fn: update_wrapper(f(fn), fn)
decorator = decorator(decorator)(decorator)

@decorator
def log_on_fail(f):
	def _f(*args, **kw_args):
		try:
			return f(*args, **kw_args)
		except Exception, e:
			logging.error("error in func: %s, error: %s" % (str(repr(f)), e))
			raise e
	return _f

@log_on_fail
def cache_all_query(cls, sort=None):
	classnme = cls.__name__.lower()
	result = memcache.get("all%s" % classnme)
	if not result or memcache.get("update%s" % classnme):
		result = list(super(type(cls), cls).all())
		result.sort(key=lambda x: getattr(x, sort or str(x)))
		memcache.set("all%s" % classnme, result)
	return result

@decorator
@log_on_fail
def update_cache(f):
	def _f(self_or_cls, *args, **kw_args):
		logging.info("cache update")
		memcache.set("update%ss" % self_or_cls.__name__.lower(), True)
		return f(self_or_cls, *args, **kw_args)
	return _f

def get_all2(type):
	logging.info("get all")
	all = []
	length = memcache.get(type + "length")
	if not length:
		memcache.set(type+"length", 1)
		memcache.set(type+"0", [])
	for i in xrange( memcache.get(type+"length") ):
		assert not memcache.get(type+str(i)) is None, "part is None. Vars: i>%d; length>%d" % (i, length)
		all = all + memcache.get(type+str(i))
	assert len(all) >= length
	return all or []

@log_on_fail
def add_to_all2(type, object):
	length = memcache.get(type+"length")
	part = memcache.get(type + str( length - 1 ))
	if not length:
		memcache.set(type+"length", "1")
		part = [object]
	else:
		part.append(object)
	if len(part) >= MEMCACHE_LEN:
		memcache.set(type+"length", length+1)
		memcache.set(type + str(length), [])
	memcache.set(type + str(length-1), part)
		
@log_on_fail
def set_all2(type, objects):
	assert type in ["users", "messages", "items"], "set_all was not passed a valid type"
	assert not objects is None, "set_all was passed None as the list of objects"
	logging.info("in set all")
	length = len(objects)/MEMCACHE_LEN
	if len(objects)%MEMCACHE_LEN > 0:
		length += 1
	length += 1
	memcache.set(type+"length", length)
	for i in xrange(len(objects)):
		part_num = i/MEMCACHE_LEN
		part = memcache.get(type+str(part_num))
		if not part: part = []
		part.append(objects[i])
		memcache.set(type+str(part_num), part)
		logging.info("i>%d; part_num>>%d" % (i, part_num))
		assert len(part) == i%MEMCACHE_LEN, "length of part is not equal to i%LEN"

@log_on_fail
def get_all(type, Class):
	all = []
	ids = memcache.get(type+"allid")
	query_amount = 0
	if ids:
		for id in ids:
			ob = memcache.get(str(id))
			if ob is None:
				ob = Class.get_by_id(int(id))
				memcache.set(str(id), ob)
				query_amount += 1
			all.append(ob)
		if query_amount: logging.info(str(query_amount) + " ob queries")
		return all
	return None

def add_to_all(type, object):
	memcache.set(str(object.key().id()), object)
	all = memcache.get(type+"allid")
	if not all: 
		all = [str(ob.key().id()) for ob in object.__class__.all()]
		logging.info("DB query for %s" % type)
	assert all is not None, "query returned None.  Send this error code to Mondays: 23-193A"
	if not str(object.key().id()) in all:
		all.append(str(object.key().id()))
	memcache.set(type+"allid", all)
	if type == "messages":
		r = object.receiver
		msgs = memcache.get("msgs%s" % r)
		if msgs is None:
			msgs = []
			logging.warning("user may have lost cached messages: %s" % object.receiver)
		msgs.append(object)
		msgs.sort(reverse=True, key=lambda m: m.sent)
		memcache.set("msgs%s" % r, msgs)

@log_on_fail
def set_all(type, objects):
	assert type in ["users", "messages", "items"], "set_all was not passed a valid type.  Send this error code to Mondays: 33-205"
	assert not objects is None, "set_all was passed None as the list of objects.  Send this error code to Mondays: 33-206"
	all = []
	for ob in objects:
		error = not memcache.set(str(ob.key().id()), ob)
		if error:
			logging.warning("keys not setting properly. Object must not be pickleable")
		all.append(str(ob.key().id()))
	memcache.set(type+"allid", all)

@log_on_fail
def del_from(type, object):
	all = memcache.get(type+"allid")
	if not all: 
		all = object.__class__.all()
		logging.info("DB query %s" % type)
	assert all, "Could not find any messages.  Send this error code to Mondays: 13-219"
	assert str(object.key().id()) in all, "item not found in cache.  Send this error code to Mondays: 33-220"
	del all[ all.index(str(object.key().id())) ]
	memcache.set(type+"allid", all)
	memcache.delete(str(object.key().id()))


class PaypalAdaptivePayment:

	def __init__(self, paypal_sandbox_enabled):
		self.paypal_sandbox_enabled = paypal_sandbox_enabled
		self.response_data_format = "JSON"
		self.request_data_format = "JSON"
		if paypal_sandox_enabled:
			self.paypal_secure_user_id = "harris_1351215974_biz_api1.hunterhayven.com"
			self.paypal_secure_password = "1351215996"
			self.paypal_secure_signature = "An5ns1Kso7MWUdW4ErQKJJJ4qi4-A99zn7jYO8xZRhbeljNMwIkd1mMD"
			self.receiver_email = "harris_1351215974_biz@hunterhayven.com"
			self.request_url = "https://svcs.sandbox.paypal.com/AdaptivePayments/Pay"
		else:
			self.paypal_secure_user_id = "pass"
			self.paypal_secure_password = "pass"
			self.paypal_secure_signature = "pass"
			self.receiver_email = "receiver"
			self.request_url = "pass"

	def initialize_payment(self, amount, cancel_url, return_url):
		try:
			headers = {}
			headers["X-PAYPAL-SECURITY-USERID"] = self.paypal_secure_user_id
			headers["X-PAYPAL-SECURITY-PASSWORD"] = self.paypal_secure_password
			headers["X-PAYPAL-SECURITY-SIGNATURE"] = self.paypal_secure_signature
			headers["X-PAYPAL-REQUEST-DATA-FORMAT"] = self.request_data_format
			headers["X-PAYPAL-RESPONSE-DATA-FORMAT"] = self.response_data_format
			if self.paypal_sandbox_enabled:
				headers["X-PAYPAL-APPLICATION-ID"] = "APP-80W284485P519543T"
			else:
				headers["X-PAYPAL-APPLICATION-ID"] = "PASS"
#			params = {'actionType':'PAY', 'receiverList':{'receiver':[{'email':self.receiver_email,'amount':amount}]}, 'cancelUrl':cancel_url,\
#					'requestEnvelope':\ 'errorLanguage':'en_US'}, 'currencyCode':'USD', 'returnUrl':return_url}
			request_data = json.dumps(params)
#			response = send request with headers and request_data
			response_data =  json.loads(response.read())
			assert response_data, "No response data"
		except Exception, e:
			logging.error("unable to initialize payment flow.  ERROR:\n%s" % e)

