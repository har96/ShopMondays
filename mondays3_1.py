import cgi
import logging
import os
import re
import hashlib
import random
import string
import time
from datetime import datetime
from pytz.gae import pytz
from pytz import timezone

from google.appengine.ext import webapp
from google.appengine.ext.webapp import template
from google.appengine.ext.webapp.util import run_wsgi_app
from google.appengine.ext import db
from google.appengine.api import images

USER_RE = re.compile("^[a-zA-Z0-9_-]{3,20}$")
PASSWORD_RE = re.compile("^.{4,20}$")
def valid_username(username):
	return USER_RE.match(username)
def valid_password(password):
	return PASSWORD_RE.match(password)
def make_salt():
	return "".join([random.choice(string.ascii_letters) for i in xrange(5)])
def hash_str(s):
	return hashlib.sha256(s).hexdigest()
def hash_user_info(name, password, salt=None):
	salt = salt or make_salt()
	return (hash_str(name+password+salt), salt)
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

# goal for tomorrow: create gen_date that takes day offset as args instead of timetuple
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

def gen_date(timetuple):
	z = timezone('US/Central')
	tme = datetime.now(z)
	month = tme.month
	logging.info("day %d" % timetuple[2])
	lim = find_month_lim(month, tme.year)
	timetuple[3] = tme.hour
	timetuple[1] = tme.month
	utcday = datetime.now().day
	if (utcday - tme.day) >= 0: daysubtract = utcday - tme.day
	else: daysubtract = 1
	timetuple[2] -= daysubtract
	if timetuple[2] < 1:
		timetuple[2] = tme.day
	if timetuple[2] > lim:
		logging.info("month before %d" % timetuple[1])
		timetuple[1] += 1
		timetuple[2] -= lim
		return gen_date(timetuple)
	else:
		timetuple = timetuple[:-2]
		return datetime(*timetuple)


def gen_date1(timetuple):
	"""returns a datetime object"""
	month = timetuple[1]
	hour = timetuple[3]
	if hour < 6: timetuple[2] -= 1
	logging.info("day %d" % timetuple[2])
	logging.info("hour %d" % hour)
	logging.info("year %d" % timetuple[0])
	hour -= 5
	if hour < 0: hour += 24
	timetuple[3] = hour
	lim = find_month_lim(month, timetuple[0])
	if timetuple[2] == 0:
		m = (month - 1) if month > 1 else 12
		y = timetuple[0] if month > 1 else timetuple[0] - 1
		timetuple[2] = find_month_lim(m, y)
	if timetuple[2] > lim:
		timetuple[1] += 1
		timetuple[2] -= lim
		return gen_date(timetuple)
	else:
		return datetime(*timetuple[:-3])
def has_whitespace(s):
	for c in s:
		if c == " ":
			return True
	return False
def create_image(image, width=None, height=None):
	if width and height:
		image = images.resize(image, width, height)
	return db.Blob(str(image))


class User( db.Model ):
	name = db.StringProperty(required=True)
	password = db.StringProperty(required=True)
	salt = db.StringProperty(required=True)

	@classmethod
	def get_by_name(cls, name):
		return cls.all().filter('name =', name).get()
	
	@classmethod
	def register(cls, username, password):
		p, salt = hash_user_info(username, password)
		return cls(name=username, password=p, salt=salt)

	@classmethod
	def valid_user_cookie(cls, cookie):
		id, password = cookie.split("|")
		id = int(id)
		return users_match(cls.get_by_id(id), password)

class Message( db.Model ):
	sender = db.StringProperty(required=True)
	content = db.TextProperty(required=True)
	receiver = db.StringProperty(required=True)
	sent = db.DateTimeProperty(required=True)
	sent_str = db.StringProperty()
	image = db.BlobProperty()

	@classmethod
	def get_from_sender(cls, sender):
		return [m for m in cls.all() if m.sender == sender]

	@classmethod
	def get_from_receiver(cls, receiver):
		q = cls.all()
		q.filter("receiver =", receiver)
		q.order("-sent")
		return q

	@classmethod
	def send_msg(cls, sender, receiver, content, image=None):
		td = gen_date2()
		m = cls(sender=sender, receiver=receiver, content=cgi.escape(content, quote=True), sent=td)
		if image: m.image = create_image(image, 200, 200)
		m.sent_str = m.sent.strftime("%b %d  %T")
		m.put()
	
	@classmethod
	def send_mond_msg(cls, receiver, content, image=None):
		td = gen_date2()
		m = cls(sender="Mondays", receiver=receiver, content=content, sent=td)
		if image: m.image = create_image(image, 200, 200)
		m.sent_str = m.sent.strftime("%b %d  %T")
		m.put()

class Item( db.Model):
	seller = db.StringProperty(required=True)
	title = db.StringProperty(required=True)
	description = db.TextProperty()
	num_bids = db.IntegerProperty()
	current_buyer = db.StringProperty()
	current_price = db.FloatProperty()
	image = db.BlobProperty()
	listed = db.DateTimeProperty(required=True)
	expires = db.DateTimeProperty(required=True)
	shipdate = db.DateTimeProperty(required=True)

	def bid(self, buyer, price):
		""" places a bid on an item,
		assumes that buyer is a valid user
		and price is a valid price"""

		self.num_bids += 1
		self.current_buyer = buyer
		self.current_price = price
		self.put()
	
	def did_expire(self):
		""" Returns True if the item has expired. """
		return gen_date2() >= self.expires
	@classmethod
	def get_new(cls, seller, title, days_listed, shipdays, image=None, current_price=0.01, description=""):
		expires = gen_date2(days_listed)
		shipdate = gen_date2(days_listed + shipdays)
		listed = gen_date2()
		i = cls(seller=seller, title=title, description=description,
					num_bids=0, current_buyer="", current_price=current_price,
					expires = expires, shipdate=shipdate, listed=listed,
					image=image)
		return i

	@classmethod
	def get_by_seller(cls, seller):
		i = cls.all().filter('seller =', seller)
		i.order("-listed")
		return i

	@classmethod
	def get_by_title(cls, title):
		i = cls.all().filter('title =', title)
		return i[0]

class Handler( webapp.RequestHandler ):
	def render(self, temp, **format_args):
		path = os.path.join(os.path.dirname(__file__), temp)
		self.response.out.write(template.render(path, format_args))

	def cookie_error(self):
		self.response.out.write("Sorry, Mondays encountered a problem. Invalid cookie,"
					"please sign in again")

	def get_user_cookie(self):
		return self.request.cookies.get("user_id")

class HomePage( Handler ):
	def write(self, **format_args):
		self.render("home_page.html", **format_args)
	def get(self):
		items = Item.all()
		for i in items:
			if i.did_expire():
				msg = "You sold your %s to %s for %0.2f! Make sure you ship before %s!" \
						% (i.title, i.current_buyer, 
								i.current_price,
								i.shipdate.strftime("%b %d")) \
						if i.num_bids else "Sorry %s did not sell" % (i.title)
				Message.send_mond_msg(i.seller, msg)
				i.delete()

		self.write()
	def post(self):
		username = self.request.get("username")
		password = self.request.get("password")

		if not username or not password:
			self.write(error="Invalid Input", username=cgi.escape(username))

		u = User.get_by_name(username)
		if u and users_match(u, hash_user_info(username, password, u.salt)[0]):
			self.response.headers.add_header("Set-Cookie", "user_id=%s|%s; Path=/" % (u.key().id(), u.password))
			self.redirect("/home")
		else:
			self.write(error="Invalid Login", username=cgi.escape(username))

class AboutPage( Handler ):
	def write(self):
		self.render("about_page.html")
	def get(self):
		self.write()

class Register( Handler ):
	def write(self, **format_args):
		self.render("register_page.html", **format_args)
	def get(self):
		self.write()
	def post(self):
		username = self.request.get("username")
		password = self.request.get("password")
		verify = self.request.get("verify")

		u_error = "Invalid Username" if not valid_username(username) else ""
		p_error = "Invalid Password" if not valid_password(password) else ""
		v_error = "Passwords Don't Match" if password != verify else ""
		if u_error or p_error or v_error:
			self.write(u_error=u_error, p_error=p_error, v_error=v_error, username=username)
			return
		elif User.get_by_name(username):
			self.write(u_exists_error="Username already exists")
			return
		else:
			u = User.register(username, password)
			u.put()
			self.response.headers.add_header("Set-Cookie", 'user_id=%s|%s; Path=/' % (u.key().id(), u.password))
			Message.send_mond_msg(username, "Welcome to Mondays <b>%s</b>!" % username)
			self.redirect("/home")

class UserHome( Handler ):
	def write(self, **format_args):
		self.render("user_page.html", **format_args)
	def get(self):
		cookie = self.get_user_cookie()
		if not User.valid_user_cookie(cookie):
			self.cookie_error()
		else:
			id = int(cookie.split("|")[0])
			msgs = Message.get_from_receiver(User.get_by_id(id).name)
			useritems = Item.get_by_seller(User.get_by_id(id).name)
	
			self.write(user=User.get_by_id(id), usermessages=msgs, useritems=useritems)
	def post(self):
		del_id = self.request.get("delete_mes")
		m = Message.get_by_id(int(del_id))
		if m: m.delete()
		self.redirect("/home")


class CreateMessage( Handler ):
	def write(self, **format_args):
		self.render("message_page.html", **format_args)
	def get(self):
		cookie = self.request.cookies.get("user_id")
		if User.valid_user_cookie(cookie):
			id = int(cookie.split("|")[0])
			user = User.get_by_id(int(cookie.split("|")[0]))
			self.write(user=user, users=User.all().order("-name"))
		else:
			self.cookie_error()
	def post(self):
		content = self.request.get("body")
		receiver = self.request.get("receiver")
		image = self.request.get("img")
		all = self.request.get("all")
		mon = hash_str(self.request.get("special")) == "d22b19ed9f9162ff68246af24614a83ab12fafe116a7554afededf8beb6c3e5c"
		if not content:
			self.write(user=user, error="Must have a content", body=cgi.escape(content), 
					users=User.all().order("-name"), receiver=cgi.escape(receiver))
			return
#		if not User.get_by_name(receiver):
#			self.write(user=user, users=User.all().order("-name"), error="To: User does not exists", 
#					body=cgi.escape(content), receiver=cgi.escape(receiver))
#			return
		cookie = self.request.cookies.get("user_id")
		if User.valid_user_cookie(cookie):
			id = int(cookie.split("|")[0])
		else:
			self.cookie_error()
			return
		if all == "on":
			try:
				sender = User.get_by_id(id).name if not mon else "Mondays"
				for u in User.all():
					Message.send_msg(sender, u.name, content, image or None)
			except Exception, e:
				
				self.write(user=sender, error="Sorry, message did not send, an error occured: %s" % e,
					body=cgi.escape(content), receiver=cgi.escape(receiver))
				return
		else:
#			try:
			sender = User.get_by_id(id).name if not mon else "Mondays"
			Message.send_msg(sender, receiver, content, image or None)
#			except Exception, e:
#				self.write(user=sender, error="Sorry, message did not send, an error occured: %s" % e,
#						body=cgi.escape(content), receiver=cgi.escape(receiver))
#				return
		self.redirect("/home")

class AddItem( Handler ):
	def write(self, **format_args):
		self.render("additem_page.html", **format_args)
	def get(self):
		cookie = self.get_user_cookie()
		if User.valid_user_cookie(cookie):
			self.write(user=User.get_by_id(int(cookie.split("|")[0])))
		else:
			self.cookie_error()
	def post(self):
		cookie = self.get_user_cookie()
		if not User.valid_user_cookie(cookie):
			self.cookie_error()
			return
		seller = User.get_by_id(int(cookie.split("|")[0]))
		title = self.request.get("title")
		start_price = self.request.get("startprice")
		description = self.request.get("description")
		days_listed = self.request.get("days_listed")
		shipdays = self.request.get("shipdays")

		if not days_listed: days_listed = "7"
		v_error_msg = ""
		try:
			start_price = float(start_price)
		except ValueError:
			v_error_msg = "Invalid input for start price"
		if not days_listed.isdigit(): v_error_msg = "Invalid input for days listed" 
		if not shipdays or not shipdays.isdigit(): v_error_msg = "Invalid input for shipping time" 
		error_msg = "" if title and start_price else "Must have a title and start price"
		if has_whitespace(title): error_msg = "Title cannot have spaces,  can use underscores '_'"
		if not v_error_msg and int(days_listed) > 10: "An item can't be listed for more that 10 days"
		if not v_error_msg and int(shipdays) > 14: "You must ship sooner than 15 days"

		if v_error_msg or error_msg:
			self.write(user=seller, error=error_msg, value_error=v_error_msg, title=cgi.escape(title), \
					price=cgi.escape(str(start_price)), desc=cgi.escape(description), \
					days_listed=cgi.escape(days_listed), shipdays=cgi.escape(str(shipdays)))
			return
		days_listed = int(days_listed)
		shipdays = int(shipdays)
		item = Item.get_new(seller.name, title, days_listed, shipdays, current_price=start_price,
				description=description)
		if self.request.get("img"): item.image = create_image(self.request.get("img"), 400, 400)
		item.put()
		self.redirect("/home")

class ItemView( Handler ):
	def write(self, **format_args):
		self.render("item_page.html", **format_args)
	def get(self):
		title = self.request.get("title")
		cookie = self.get_user_cookie()
		if User.valid_user_cookie(cookie):
			user = User.get_by_id(int(cookie.split("|")[0]))
			self.response.headers.add_header("Set-Cookie", "item_id=%s" % title)
			item = Item.get_by_id(int(title))
			shipdate = item.shipdate.strftime("%b  %d")
			expdate = item.expires.strftime("%b  %d  %T")
			self.write(user=user, shipdate=shipdate, expdate=expdate, item=item)
		else:
			self.cookie_error()
	def post(self):
		cookie = self.get_user_cookie()
		if User.valid_user_cookie(cookie):
			buyer = User.get_by_id(int(cookie.split("|")[0])).name
		else:
			self.cookie_error()
			return
		id = self.request.cookies.get("item_id")
		price = self.request.get("price")
		i = Item.get_by_id(int(id))
		shipdate = i.shipdate.strftime("%b  %d")
		expdate = i.expires.strftime("%b  %d  %T")
		if buyer == i.seller:
			self.write(user=buyer, item=i, shipdate=shipdate, expdate=expdate,
					error="You cannot bid on items you sell")
			return

		if price:
			try:
				price = float(price)
			except ValueError:
				self.write(user=buyer, item=i, shipdate=shipdate,
						expdate=expdate, error = "Invalid price")
				return
			if price < (i.current_price + 0.10):
				self.write(user=buyer, item=i, shipdate=shipdate,
						expdate=expdate,
						error="Bid must be at least 10c over price")
				return
			i.bid(buyer, price)
			self.redirect("/home")
		else:
			field = """<label>Bid Price <input type="text" name="price"></label>"""
			self.write(user=buyer, item=i, shipdate=shipdate, expdate=expdate, sure_msg=field) 


class Archive( Handler ):
	def write(self, **format_args):
		self.render("archive_page.html", **format_args)
	def get(self):
		cookie = self.get_user_cookie()
		if User.valid_user_cookie(cookie):
			user = User.get_by_id(int(cookie.split("|")[0]))
			self.write(user=user, items=Item.all().order("-listed"))
		else: self.cookie_error()

class RequestMsg( Handler ):
	def write(self, **format_args):
		self.render("request_page.html", **format_args)
	def get(self):
		cookie = self.get_user_cookie()
		if not User.valid_user_cookie(cookie):
			self.cookie_error()
			return
		self.write(user=User.get_by_id(int(cookie.split("|")[0])))
	def post(self):
		cookie = self.get_user_cookie()
		if not User.valid_user_cookie(cookie):
			self.cookie_error()
			return
		sender = User.get_by_id(int(cookie.split("|")[0]))
		item = self.request.get("item")
		image = self.request.get("img")
		if not item:
			self.write(user=sender, error="Must specify an item")
			return
		for u in User.all():
			if u.name == sender.name:
				continue
			Message.send_mond_msg(u.name, "%s is requesting users to sell %s" % (sender.name, item),
					image=image)
		self.redirect("/home")

class Image( Handler ):
	def get(self):
		item = Item.get_by_title(self.request.get("img"))
		if item.image:
			self.response.headers['Content-Type'] = "image/jpg"
			self.response.out.write(item.image)
		else:
			self.error(404)
class ImageMsg(Handler):
	def get(self):
		msg = Message.get_by_id(int(self.request.get("id")))
		logging.info("msg: %s" % msg.sender)
		if msg.image:
			self.response.headers['Content-Type'] = "image/jpg"
			self.response.out.write(msg.image)
		else:
			self.error(404)

class Logout( Handler ):
	def get(self):
		self.response.headers.add_header("Set-Cookie", "user-id=; Path=/")
		self.redirect("/")
			
app = webapp.WSGIApplication([("/", HomePage),
				("/about", AboutPage),
				("/register", Register),
				("/home", UserHome),
				("/message", CreateMessage),
				("/newitem", AddItem),
				("/item", ItemView),
				("/archive", Archive),
				("/request", RequestMsg),
				("/img", Image),
				("/img_msg", ImageMsg),
				("/logout", Logout)], debug=True)

def main():
	run_wsgi_app(app)

if __name__ == "__main__":
	main()
