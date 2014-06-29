# note: this module only works for python 2.5, unless
# provided with a later version of bcrypt
from configure_path import libraries
import sys
sys.path.extend(libraries)

# time
from pytz.gae import pytz
from pytz import timezone
from datetime import datetime
import time
# crypt
import hashlib
import random
import bcrypt
#formatting
import string
import re
from markdown import markdown
# other
from functools import update_wrapper
import logging
import urllib
import json
import math

# exernal
import paypal_settings as paypal
from client import captcha

# google
from gaesessions import get_current_session

from google.appengine.api import images
from google.appengine.api import urlfetch
from google.appengine.api import memcache
from google.appengine.ext import db

PAYPAL = "https://svcs.sandbox.paypal.com/AdaptivePayments/API_operation"
CAPTCHA_KEY = "6Ld1y-ASAAAAALcEb4SIJhGxS0buBCML3ceiCBfC"

MEMCACHE_LEN = 15

USER_RE = re.compile("^[a-zA-Z0-9_-]{3,20}$")
PASSWORD_RE = re.compile("^.{4,20}$")
EMAIL_RE = re.compile(r"\S+@\S+\.\S+")
def valid_username(username):
	return USER_RE.match(username) and len(username) < 30
def valid_password(password):
	return PASSWORD_RE.match(password) and len(password) < 1000
def valid_email(email):
	return EMAIL_RE.match(email) and len(email) < 254
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
def reset_pw(user, password):
	pw = hash_user_info(user.name, password, user.pepper, user.salt)[0]
	user.password = pw
	user.put()
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
	if tmelist[1] > 12:
		tmelist[1] = 1
		tmelist[0] += 1
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
	logging.info("called")
	ids = memcache.get(type+"allid")
	query_amount = 0
	if ids:
		for id in ids:
			ob = memcache.get(str(id))
			if ob is None:
				ob = Class.get_by_id(int(id))
				if ob is None:
					continue
				memcache.set(str(id), ob)
				query_amount += 1
			all.append(ob)
		if query_amount: logging.info(str(query_amount) + " ob queries")
		return all
	return None

def add_to_all(type, object):
	memcache.set(str(object.key.integer_id()), object)
	all = memcache.get(type+"allid")
	if not all: 
		all = [str(ob.key.integer_id()) for ob in object.__class__.all()]
		logging.info("DB query for %s" % type)
	assert all is not None, "query returned None.  Send this error code to Mondays: 23-193A"
	if not str(object.key.integer_id()) in all:
		all.append(str(object.key.integer_id()))
	memcache.set(type+"allid", all)
	logging.info("called")

@log_on_fail
def set_all(type, objects):
	assert type in ["users", "messages", "items"], "set_all was not passed a valid type.  Send this error code to Mondays: 33-205"
	assert not objects is None, "set_all was passed None as the list of objects.  Send this error code to Mondays: 33-206"
	all = []
	logging.info("called")
	for ob in objects:
		error = not memcache.set(str(ob.key.integer_id()), ob)
		if error:
			logging.warning("keys not setting properly. Object must not be pickleable")
		all.append(str(ob.key.integer_id()))
	memcache.set(type+"allid", all)

@log_on_fail
def del_from(type, object):
	all = memcache.get(type+"allid")
	if not all: 
		all = [str(ob.key.integer_id()) for ob in object.__class__.all()]
		logging.info("DB query %s" % type)
	assert all, "Could not find any objects.  Send this error code to Mondays: 13-219"
	assert str(object.key.integer_id()) in all, "item not found in cache.  Send this error code to Mondays: 33-220"
	del all[ all.index(str(object.key.integer_id())) ]
	memcache.set(type+"allid", all)
	memcache.delete(str(object.key.integer_id()))
	logging.info("called")

def get_sponsers():
	request = urllib.urlopen("http://mondaysstatic.appspot.com/sponsers.json").read()
	if request:
		request = json.loads(request)["list"]
	else:
		request = ["Sorry, this info is currently unavailable"]
	return request

class Struct(object):
	def __init__(self, **kwargs):
		self.__dict__.update(kwargs)

def verify_paypal_email(email, user):
	""" Asks paypal to verify the users email """
	params = ""
	params = params + "?METHOD=AddressVerify"
	params = params + "&USER="+paypal.API_USERID
	params = params + "&PWD=" + paypal.API_PWD
	params = params + "&SIGNATURE="+paypal.API_SIGNATURE
	params = params + "&EMAIL=" + email
	params = params + "&STREET=" + user.address1[:3]
	params = params + "&ZIP=" + str(user.zip)
	response = urlfetch.fetch(paypal.NVP_ADDRESS+ params, method=urlfetch.POST)
	
	return valid_email(email) # None would mean an it's not an account

def render_item_info(item, pageuser, brating, srating):
	user = pageuser
	id = item.key.id()

	shipdate = item.shipdate.strftime("%b  %d")
	# get conditional vars
	# pay_message
	pay_message = "<br>Payment Status: "
	if item.payed:
		pay_message += "<b>Item is payed for</b>"
	elif user.name == item.current_buyer and (item.paypal_email and not item.pay_votes):
		pay_message += '<b>You have not payed for this item, </b><a href="/buy/%s">pay here</a>.' % id
	elif user.name == item.current_buyer and not item.paypal_email and item.pay_votes == 1:
		pay_message += '<b>Awaiting payment confirmation from seller</b>'
	if not item.expired:
		pay_message = ""
	# bid form
	bid_box = "" if item.list_option == "instant" or item.did_expire() or item.expired or pageuser.name == item.seller else """<form id="bid_form" method="post">
							<div id="bid-box">
								<button type="button" onClick="show_bid()">Bid</button> Minimum Price: $%0.2f
							</div>
						</form>
						""" % (item.current_price + item.bid_margin)
	if user.name == "Visitor":
		bid_box = ""
	# watch form
	unwatch_form = """<form action="/unwatch/%s" method="post">
			<button type="submit">Unwatch Item</button>
			</form>""" % id
	watch_form = """<form action="/watch/%s" method="post">
	<button type="submit">Watch Item</button>
	</form>""" % id


	watch_box = ""
	if item.expired:
		if item.key.integer_id() in user.watch_list:
			watch_box = unwatch_form
		else:
			watch_box = ""
	else:
		if item.key.integer_id() in user.watch_list:
			watch_box = unwatch_form
		elif user.name == item.seller:
			watch_box = ""
		else:
			watch_box = watch_form
	if user.name == "Visitor":
		watch_box = ""

	# rate link
	rate = ""
	if user.name == item.current_buyer and item.expired and srating.get_by_item(item) is False:
		rate = '<a href="/sellerrating/%s">Rate Seller</a>' % item.key.id()
	elif user.name == item.seller and item.expired and brating.get_by_item(item) is False and item.current_buyer:
		rate = '<a href="/buyerrating/%s">Rate Buyer</a>' % item.key.id()
	
	# edit link
	edit_link = 'This is your item. - <a href="/edit_item/%s">EDIT</a>' % id if user.name == item.seller and not item.expired else ""
	# ship info
	ship_info = "You must pick this item up before %s<br>" % shipdate
	if not item.local_pickup == "pickup":
		ship_info = "Ships by: %s<br>" % shipdate
		if not item.shipprice:
			ship_info = ship_info + "FREE Shipping!"
		else:
			ship_info = ship_info + "Shipping costs $%0.2f" % item.shipprice
	#shipping option
	ship_option = ""
	if item.local_pickup == "on":
		ship_option = "<b>This item is up for local pickup or shipping, contact seller to get address</b>"
	elif item.local_pickup == "pickup":
		ship_option = "<b>You must pickup this item.  The seller will not ship it.</b>"
	if item.paypal_email:
		paypal_logo = """<!-- PayPal Logo --><a href="#" title="How PayPal Works" onclick="javascript:window.open('https://www.paypal.com/webapps/mpp/paypal-popup','WIPaypal','toolbar=no, location=no, directories=no, status=no, menubar=no, scrollbars=yes, resizable=yes, width=1060, height=700');" style="position: relative; top:7px;"><img src="https://www.paypalobjects.com/webstatic/i/sparta/logo/logo_paypal_106x29.png" border="0" alt="PayPal Logo" width="70px" height="20px"></a><!-- PayPal Logo -->""" 
		paypal_message = "This seller requires " + paypal_logo + " payments"
	else:
		paypal_message = '<span class="warning">Warning: This seller does not accept PayPal.  By bidding or buying<br> \
				you are acknowledging that there is risk involved and<br>\
				that ShopMondays is not responsible for lost payment</span>'
	relist_button = ""
	if item.expired and user.name == item.seller:
		conditions = ["New; Unopen unused", "Used; still in perfect condition", "Used; has some wear", "Old; still good as new"]
		relist_button = '<a href="/relistitem/%s"><button>Relist</button></a>' % item.key.id()
	pay_vote_button = ""
	if not item.payed and item.expired and user.name == item.current_buyer and not item.pay_votes:
		pay_vote_button = """<form method="post" action="/payvote/%s"><button type="submit">Mark as Payed</button></form>""" % item.key.id()
	elif not item.payed and item.expired and user.name == item.seller and item.pay_votes == 1:
		pay_vote_button = """<form method="post" actoin="/payvote/%s"><button type="submit">Confirm reception of payment</button></form>""" % item.key.id()
	
	instantbuy = ""
	if pageuser.name != item.seller and not item.expired:
		if item.list_option == "both":
			instantbuy = 'This item can also be bought instantly for $%0.2f.  <a href="/instantbuy/%s"><button>Buy Now</button></a>' % \
					(item.get_price(True), item.key.id())
		elif item.list_option == "instant":
			instantbuy = 'This item is up for Instant Buy: <a href="/instantbuy/%s"><button>Buy Now</button></a>' % item.key.id()

	template = """
	{ship_option}<br>
	{ship_info}
	<br>
	{edit}
	{watch}
	{bid}&nbsp; {instantbuy}<br>
	<br><span style="font-size: 0.9em">{paypal}</span>
	{pay_message}
	{pay_vote_button}
	{relist}
	<br>
	{rate}
	
	""".format(ship_option=ship_option, ship_info=ship_info, paypal=paypal_message, \
			edit=edit_link, watch=watch_box, bid=bid_box, pay_message=pay_message,\
			pay_vote_button=pay_vote_button, relist=relist_button, rate=rate, instantbuy=instantbuy)
	
	return template
def create_references(message):
	""" adds receivers and sender to references.
	Meant for the migration between 3.3 beta and stable release """
	# clear references
	message.references = []
        message.references = message.references + message.receiver
	return True
def repeat_receiver(message):
	""" Turns the receiver property into a repeated property.
	meant for the migration between 3.3 beta and stable release"""
	if type(message.receiver) == list:
		print "done"
		return
	message.receiver = [message.receiver]
	return True
def bold(match):
	""" returns the html markup that replaces
	the match object passed """
	s = match.string[match.start():match.end()]
	text = s[3:-3]
	return "<b>%s</b>" % text
def italic(match):
	""" returns the italic html markup that
	replaces the match object passed"""
	s = match.string[match.start():match.end()]
	text = s[3:-3]
	return "<em>%s</em>" % text
def link(match):
	""" returns the hyperlink html markup that
	replaces the match object passed"""
	s = match.string[match.start():match.end()]
	href = re.search(r"\([\s\S]+\)", s)
	assert not href is None
	text = s[href.end()+1:-3]
	return '<a href=%s target="_blank">%s</a>' % (re.sub(r"\s", "", href.string[href.start()+1:href.end()-1]), text)
def img(match):
	""" returns the image html markup that
	replaces the match object passed """
	s=match.string[match.start():match.end()]
	src = s[5:-5]
	src = re.sub(r"\s", "", src)
	return '<img src="%s" />' % src
def markup_text(s):
	""" Goes through the text-must be html escaped-and
	substitutes html for certain symbols:
	#b#text#b#: <b>text</b>
	#i#text#i#: <em>text</em>
	#l(website)#text#l#: <a href="website" type="_blank">text</a>
	#img#src#img#
	"""
	s, n = re.subn(r"#b#[\s\S]+?#b#", bold, s)
	s, n = re.subn(r"#l\([\s\S]+\)#[\s\S]+?#l#", link, s)
	s, n = re.subn(r"#i#[\s\S]+?#i#", italic, s)
#	s, n = re.subn(r"#img#[\s\S]+?#img#", img, s)
	return s
months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul',
		'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

def getkey(value, arg):
	""" returns value[arg] """
	return str(value.get(arg, ""))

def balance( history ):
	""" returns credit-debit """
	return str( float(history["money earned"]) - float(history["money spent"]) )

def dollars( amount ):
	""" converts a float to dollars """
	if type(amount) == str:
		return amount
	return "%0.2f" % float(amount)

def br_newlines( string ):
	""" replaces newlines with <br> """
	return string

def mdtime( date ):
	""" Returns the datetime property date as 
	string of the format: "mon dd hh:mm"  """
	s = months[ date.month - 1 ]
	s = s + " %d" % date.day
	s = s + " %d:%02d" % (date.hour, date.minute)
	return s

#def user_link( username ):
#	""" Returns a string containing a link to the
#	user's profile page.  Link will be green if the user
#       was on recently"""
#	session = get_current_session()
#	users = session.get("users on")
#	if not users:
#		return '<a href="/user/%s">%s</a>' % (username, username)
#	last_on = users.get(username, 0.0)
#	diff = time.time() - last_on
#	logging.info(diff)
#	if diff < 180:
#		return '<a style="color: green;" href="/user/%s">%s</a>' % (username, username)
#	return '<a href="/user/%s">%s</a>' % (username, username)
	
def average( ratings ):
        try:
                ave =  float(sum(ratings))/len(ratings)
        except: #Division by zero
                return 0

        # round the float to in int
        fraction = ave - int(ave)
        if fraction >= .5:
                ave = math.ceil(ave)
        return int(ave)

def get_rating_data(user, SellerRating, BuyerRating):
	""" Returns a dictionary of data regarding ratings of user "user" """
	ratings = {}
	ratings.update( {"positive":0,
			"negative": 0,
			"neutral": 0,
			"Bpositive": 0,
			"Bnegative": 0,
			"Bneutral": 0} )

	seller_qry = SellerRating.query(SellerRating.seller == user.name)
	overall = []
	shipping = []
	honesty = []
	com = []
	def get_ratings(rating):
		overall.append(rating.overall)
		if rating.overall == -1:
			ratings["negative"] += 1
		elif rating.overall == 1:
			ratings["positive"] += 1
		elif rating.overall == 0:
			ratings["neutral"] += 1
		shipping.append(rating.shipping)
		honesty.append(rating.honesty)
		com.append(rating.communication)
	seller_qry.map(get_ratings)
	
	ratings["pos percentage"] = float(ratings["positive"])/float(len(overall) or 1)*100
	ratings["neg percentage"] = float(ratings["negative"])/float(len(overall) or 1)*100
	ratings["neut percentage"] = float(ratings["neutral"])/float(len(overall) or 1)*100

	ratings["shipping"] = average(shipping)
	ratings["honesty"] = average(honesty)
	ratings["communication"] = average(com)

	buyer_qry = BuyerRating.query(BuyerRating.buyer == user.name)
	B_overall = []
	payment = []
	B_com = []
	def get_Bratings(rating):
		B_overall.append(rating.overall)
		if rating.overall == -1:
			ratings["Bnegative"] += 1
		elif rating.overall == 1:
			ratings["Bpositive"] += 1
		elif rating.overall == 0:
			ratings["Bneutral"] += 1
		payment.append(rating.payment)
		B_com.append(rating.communication)
	buyer_qry.map(get_Bratings)

	ratings["Bpos percentage"] = float(ratings["Bpositive"])/float(len(B_overall)or 1)*100
	ratings["Bneg percentage"] = float(ratings["Bnegative"])/float(len(B_overall)or 1)*100
	ratings["Bneut percentage"] = float(ratings["Bneutral"])/float(len(B_overall) or 1)*100

	ratings["Bpayment"] = average(payment)
	ratings["Bcommunication"] = average(B_com)

	ratings["user"] = average(payment + B_com + shipping + honesty + com)
	ratings["amount"] = len(B_overall) + len(overall)
	ratings["buy_amount"] = len(B_overall)
	ratings["sell_amount"] = len(overall)
	
	return ratings
def validate_captcha(challenge, response, addr):
	return captcha.submit(challenge, response, CAPTCHA_KEY, addr)
def render_stars(stars):
	""" return html for "stars" out of 5 stars"""
	mondaysAssert(stars <= 5, "Too many stars", __name__, __file__)
	mondaysAssert(stars >= 0, "Cannot have negative stars", __name__, __file__)

	html = ""
	star = '<img src="/static/images/StarWhole.png" alt="*" />'
	empty = '<img src="/static/images/StarEmpty.png" alt="-" />'

	for s in xrange(stars):
		html = html + star
	for s in xrange(5 - stars):
		html = html + empty
	return html
def get_item_link(item):
	return '<a href="/item/%s">%s</a>' % (item.key.id(), item.title)
def remove_duplicate_items(ls):
	new_ls = []
	titles = []
	for item in ls:
		if not item.title in titles:
			titles.append(item.title)
			new_ls.append(item)
	return new_ls
def mondaysAssert(expression, msg, funct, filename, handler=None):
	if not expression:
		raise Exception("%s:%d:%s MondaysAssertionError: %s" % (filename, linenumber, funct, msg))

def delete_user(user):
	pass

def verifyAddress(street, street2, city, state, zip):
	""" Use SmartyStreet's address verification
	to verify an address """
	url = "https://api.smartystreets.com/street-address?auth-id=ef54b0f3-6274-4cc9-a635-be50087abdd6&auth-token=YIfm9YCh4AwKp0iICkOU8fjEcsGyiVte60NM%2B%2B7RFH0xehwiO5SVpsJjk4tHUuei2B3nIBis2uGc6Zx0uwxuDw%3D%3D&street={street}&street2={street2}&city={city}&state={state}&zipcode={zip}&candidates=1".format(**{"street": urllib.quote_plus(street), "street2":urllib.quote_plus(street2), "city":urllib.quote_plus(city), "state":state, "zip":zip})
	response = urlfetch.fetch(url, method=urlfetch.GET)
        if response.content:
    	        response_json = json.loads(response.content)
        else: response_json = None
	if not response_json:
		return False
	else:
		response_json = response_json[0]
		address = {
				"street":response_json["delivery_line_1"],
				"street2":response_json.get("delivery_line_2", ""),
				"city":response_json["components"]["city_name"],
				"state":response_json["components"]["state_abbreviation"],
				"zip":response_json["components"]["zipcode"]
			}
		return address

def format_msg(content):
    """
    Run the content through markdown
    and then through sanitizer
    """
    html = markdown(content, safe_mode="replace")
    return html
