from google.appengine.ext import db
from google.appengine.api import memcache
from helpers import *
import simplejson as json
import pickle
import cgi

memo = lambda f: cache_all_query


class User( db.Model ):
	name = db.StringProperty(required=True)
	password = db.StringProperty(required=True)
	salt = db.StringProperty(required=True)
	pepper = db.StringProperty()

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
	address1 = db.StringProperty()
	address2 = db.StringProperty()


	@log_on_fail
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
				logging.error("Error, in activation method, invalid attribute")

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

	@log_on_fail
	def get_history(self):
		if not self.history:
			return False
		hist = json.loads(self.history)
		hist["registered"] = pickle.loads( str(hist["registered"] ) )
		return hist

	@log_on_fail
	def put_history(self, history_dict):
		history_dict["registered"] = pickle.dumps( history_dict["registered"] )
		hist = json.dumps( history_dict )
		self.history = hist
		self.put()


	@classmethod
	def get_by_name(cls, name):
		try:
			return [usr for usr in cls.all() if usr.name == name][0]
		except IndexError:
			return False
	
	@classmethod
	def register(cls, username, password, email, first_name, last_name, state, city, zip, address1, address2):
		p, salt, pepper = hash_user_info(username, password)
		u = cls(name=username, password=p, salt=salt, pepper=pepper)
		u._init_history()
		u.active = False
		u.email = email
		u.first_name = first_name
		u.last_name = last_name
		u.state = state
		u.city = city
		u.zip = int(zip)
		u.address = "%s<br>%s<br>%s %s %s" % (address1, address2, city, state, zip)
		u.address1 = address1
		u.address2 = address2
		return u

	@classmethod
	def valid_user_cookie(cls, cookie):
		id, password = cookie.split("|")
		id = int(id)
		return users_match(cls.get_by_id(id), password)

	@classmethod
	def all(cls, order="name"):
		result = memcache.get("allusers")
		if not result or memcache.get("updateusers"):
			result = list(super(User, cls).all())
			result.sort(key=lambda x: getattr(x, order))
			logging.info("DB query for Users")
			memcache.set("allusers", result)
			memcache.set("updateusers", False)
		return result

	def put(self):
		memcache.set("updateusers", True)
		super(User, self).put()
	
	@classmethod
	def delete(cls, usr):
		memcache.set("updateusers", True)
		super(User, cls).delete(user)


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
		q = [msg for msg in cls.all() if msg.receiver == receiver]
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
		if hist:
			hist["number of messages sent"] += 1
			user.put_history(hist)

		# add msg to receivers history
		user = User.get_by_name(receiver)
		hist = user.get_history()
		if hist:
			hist["number of messages received"] += 1
			user.put_history(hist)
	
	@classmethod
	def send_mond_msg(cls, receiver, content, image=None):
		if not receiver:
			logging.error("invalid receiver in send_mond_msg. receiver:%s" % receiver)
			raise ValueError("There must be a valid receiver")
		if not content:
			logging.error("no content in send_mond_msg")
			raise ValueError("Message must have valid content")
		td = gen_date2()
		m = cls(sender="Mondays", receiver=receiver, content=content, sent=td)
		if image: m.image = create_image(image, 200, 200)
		m.sent_str = m.sent.strftime("%b %d  %T")
		m.put()

		# add msg to receivers history
		user = User.get_by_name(receiver)
		hist = user.get_history()
		if hist:
			hist["number of messages received"] += 1
			user.put_history(hist)

		# add msg to sender history
		user = User.get_by_name("Mondays")
		if not user:
			return
		hist = user.get_history()
		hist["number of messages sent"] += 1
		user.put_history(hist)

	@classmethod
	def all(cls, order="sent"):
		result = memcache.get("allmessages")
		if not result or memcache.get("updatemessages"):
			result = list(super(Message, cls).all())
			result.sort(key=lambda x: getattr(x, order), reverse=True)
			memcache.set("allmessages", result)
			memcache.set("updatemessages", False)
			logging.info("DB Query for messages")
		return result

	@classmethod
	def delete(cls, message):
		memcache.set("updatemessages", True)
		super(Message, cls).delete(message)

	def put(self):
		memcache.set("updatemessages", True)
		super(Message, self).put()


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
	condition = db.StringProperty()

	@log_on_fail
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
	def get_new(cls, seller, title, days_listed, shipdays, condition, image=None, current_price=0.01, description="", local_pickup="off", shipprice=0.00):
		expires = gen_date2(days_listed)
		shipdate = gen_date2(days_listed + shipdays)
		listed = gen_date2()
		i = cls(condition=condition, seller=seller, title=title, description=description,
					num_bids=0, current_buyer="", current_price=current_price,
					expires = expires, shipdate=shipdate, listed=listed,
					image=image, bid_margin=0.0, local_pickup=local_pickup, shipprice=shipprice)
		return i

	@classmethod
	def get_by_seller(cls, seller):
		i = [item for item in cls.all(order="listed") if item.seller == seller]
		return i

	@classmethod
	def get_by_title(cls, title):
		i = [item for item in cls.all() if item.title == title]
		return i[0]

	@classmethod
	@log_on_fail
	def all(cls, order="current_price"):
		result = memcache.get("allitems")
		if not result or not memcache.get("updateitems"):
			result = list(super(Item, cls).all())
			result.sort(key=lambda x: getattr(x, order))
			memcache.set("allitems", result)
			memcache.set("updateitems", True)
			logging.info("DB Query for items")
		return result

	@classmethod
	@log_on_fail
	def delete(cls, item):
		memcache.set("updateitems", False)
		super(Item, cls).delete(item)

	@log_on_fail
	def put(self):
		memcache.set("updateitems", False)
		super(Item, self).put()
			

		

