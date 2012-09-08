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
			logging.error("error in func: %s, error: %s" % (str(f), e))
			raise e
	return _f
