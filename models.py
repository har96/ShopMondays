from google.appengine.ext import db
from helpers import *
import simplejson as json
import pickle
import cgi


class User( db.Model ):
	name = db.StringProperty(required=True)
	password = db.StringProperty(required=True)
	salt = db.StringProperty(required=True)

	# A Dictionary containing the user's important events
	# "registered", "number of items sold", "number of items not sold"
	# "number of messages sent", "number of messages received", "ratings"
	# "money earned", "money spent"
	history = db.StringProperty()

	email = db.EmailProperty()
	active = db.BooleanProperty()

	last_name = db.StringProperty()
	first_name = db.StringProperty()
	state = db.StringProperty()
	city = db.StringProperty()
	zip = db.IntegerProperty()
	address = db.TextProperty()


	def activate(self, **attributes):
		""" Activates a user, insures that
		    the user has all of the required properties
		    and sets user.active to True.
		    returns True if user is already active
		    and None if user was activated.
		    """
		for attr in attributes:
			try:
				setattr(self, attr, attributes[attr])
			except AttributeError:
				logging.info("Error, in activation method, invalid attribute")

		if hasattr(self, 'active') and self.active:
			return True
		else:
			if not hasattr(self, 'history') or not self.history:
				self._init_history()
		self.active = True

	def _init_history(self):
		history = {}
		history["registered"] = pickle.dumps(gen_date2())
		history["number of items sold"] = 0
		history["number of items not sold"] = 0
		history["number of messages sent"] = 0
		history["number of messages received"] = 0
		history["ratings"] = [0, 0]  # upvotes and downvotes
		history["money earned"] = 0.0
		history["money spent"] = 0.0
		self.history = json.dumps(history)

	def get_history(self):
		hist = json.loads(self.history)
		hist["registered"] = pickle.loads( str(hist["registered"]) )
		return hist

	def put_history(self, history_dict):
		history_dict["registered"] = pickle.dumps( history_dict["registered"] )
		hist = json.dumps( history_dict )
		self.history = hist
		self.put()

	@classmethod
	def get_by_name(cls, name):
		return cls.all().filter('name =', name).get()
	
	@classmethod
	def register(cls, username, password, email, first_name, last_name, state, city, zip, address1):
		p, salt = hash_user_info(username, password)
		u = cls(name=username, password=p, salt=salt)
		u._init_history()
		u.active = False
		u.email = email
		u.first_name = first_name
		u.last_name = last_name
		u.state = state
		u.city = city
		u.zip = int(zip)
		u.address = "%s\n%s %s %s" % (address1, city, state, zip)
		return u

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

		# add msg to sender history
		user = User.get_by_name(sender)
		hist = user.get_history()
		hist["number of messages sent"] += 1
		user.put_history(hist)

		# add msg to receivers history
		user = User.get_by_name(receiver)
		hist = user.get_history()
		hist["number of messages received"] += 1
		user.put_history(hist)
	
	@classmethod
	def send_mond_msg(cls, receiver, content, image=None):
		td = gen_date2()
		m = cls(sender="Mondays", receiver=receiver, content=content, sent=td)
		if image: m.image = create_image(image, 200, 200)
		m.sent_str = m.sent.strftime("%b %d  %T")
		m.put()

		# add msg to receivers history
		user = User.get_by_name(receiver)
		hist = user.get_history()
		hist["number of messages received"] += 1
		user.put_history(hist)

		# add msg to sender history
		user = User.get_by_name("Mondays")
		if not user:
			return
		hist = user.get_history()
		hist["number of messages sent"] += 1
		user.put_history(hist)


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
	shipprice = db.FloatProperty()
	local_pickup = db.StringProperty()
	bid_margin = db.FloatProperty()

	def bid(self, buyer, price):
		""" places a bid on an item,
		assumes that buyer is a valid user
		and price is a valid price"""

		self.num_bids += 1
		self.current_buyer = buyer
		self.bid_margin = price - self.current_price
		if not self.bid_margin:
			self.bid_margin = 0.01
		self.current_price = price
		self.put()
	
	def did_expire(self):
		""" Returns True if the item has expired. """
		return gen_date2() >= self.expires
	@classmethod
	def get_new(cls, seller, title, days_listed, shipdays, image=None, current_price=0.01, description="", local_pickup="off", shipprice=0.00):
		expires = gen_date2(days_listed)
		shipdate = gen_date2(days_listed + shipdays)
		listed = gen_date2()
		i = cls(seller=seller, title=title, description=description,
					num_bids=0, current_buyer="", current_price=current_price,
					expires = expires, shipdate=shipdate, listed=listed,
					image=image, bid_margin=0.0, local_pickup=local_pickup, shipprice=shipprice)
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

