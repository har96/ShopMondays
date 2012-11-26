from google.appengine.ext import ndb
from google.appengine.api import memcache
from helpers import *
import simplejson as json
import pickle
import cgi

memo = lambda f: cache_all_query


class User( ndb.Model ):
	name = ndb.StringProperty(required=True)
	password = ndb.StringProperty(required=True)
	salt = ndb.StringProperty(required=True)
	pepper = ndb.StringProperty()

	# A Dictionary containing the user's important events
	# "registered", "number of items sold", "number of items not sold"
	# "number of messages sent", "number of messages received", "ratings"
	# "money earned", "money spent"
	history = ndb.StringProperty()

	email = ndb.StringProperty()
	active = ndb.BooleanProperty()

	last_name = ndb.StringProperty()
	first_name = ndb.StringProperty()
	state = ndb.StringProperty()
	city = ndb.StringProperty()
	zip = ndb.IntegerProperty()
	address = ndb.TextProperty()
	address1 = ndb.StringProperty()
	address2 = ndb.StringProperty()

	items_purchased = ndb.IntegerProperty(repeated=True) # ids of all the items the user has purchased
	watch_list = ndb.IntegerProperty(repeated=True) # ids of all the items the user is currently watching


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

	def watch(self, item):
		""" Adds the item's id to the users watch_list.
		returns False if item is already in watch_list else True.
		"""
		if item.key.integer_id() in self.watch_list:
			return False
		self.watch_list.append(item.key.integer_id())
		self.put()
		return True

	@classmethod
	def get_by_name(cls, name):
		try:
			return cls.query(User.name == name).fetch(1)[0]
		except:
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

#	@classmethod
#	def all(cls, order=""):
#		return super(User, cls).all()

	@classmethod
	def all(cls, order="name"):
		result = get_all("users", User)
		if not result or memcache.get("updateusers"):
			result = list(super(User, cls).all())
			set_all("users", result)
			memcache.set("updateusers", False)
			logging.info("DB query for Users")
		result.sort(key=lambda x: getattr(x, order))
		return result

	@classmethod
	def delete(cls, usr):
		del_from("users", usr)
		super(User, cls).delete(user)

class Message( ndb.Model ):
	sender = ndb.StringProperty(required=True)
	content = ndb.TextProperty(required=True)
	receiver = ndb.StringProperty(required=True)
	sent = ndb.DateTimeProperty(required=True)
	sent_str = ndb.StringProperty()
	image = ndb.BlobProperty()

	@classmethod
	def get_from_sender(cls, sender):
		return cls.query(cls.sender == sender)

	@classmethod
	def get_from_receiver(cls, receiver):
		q = cls.query(cls.receiver == receiver).order(-cls.sent)
		return q

	@classmethod
	def send_msg(cls, sender, receiver, content, image=None):
		""" When someone sends a message two copys of the message are created, one for the sender one for the
		receiver"""
		# Create copy for receiver
		td = gen_date2()
		m = cls(sender=sender, receiver=receiver, content=cgi.escape(content, quote=True), sent=td)
		if image: m.image = create_image(image, 200, 200)
		m.sent_str = m.sent.strftime("%b %d  %T")
		m.put()

		# create copy for sender
#		msg = cls(sender=sender, receiver=receiver, content=cgi.escape(content, quote=True), sent=td)
#		msg.image = m.image
#		msg.type = "sender"
#		msg.sent_str = m.sent_str
#		msg.put()


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
		# receiver copy
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

#	@classmethod
#	def all(cls, order="sent"):
#		# a stub method
#		all = list(super(Message, cls).all())
#		all.sort(key=lambda x: getattr(x, order), reverse=True)
#		return all


	@classmethod
	def all(cls, order="sent"):
		result = get_all("messages", Message)
		if not result or memcache.get("updatemessages"):
			result = list(super(Message, cls).all())
			set_all("messages", result)
			memcache.set("updatemessages", False)
			logging.info("DB Query for messages")

		result.sort(key=lambda x: getattr(x, order), reverse=True)
		return result

	@classmethod
	def delete(cls, message):
		del_from("messages", message)
		super(Message, cls).delete(message)


class Item( ndb.Model):
	seller = ndb.StringProperty(required=True)
	title = ndb.StringProperty(required=True)
	description = ndb.TextProperty()
	num_bids = ndb.IntegerProperty()
	current_buyer = ndb.StringProperty()
	current_price = ndb.FloatProperty()
	image = ndb.BlobProperty()
	listed = ndb.DateTimeProperty(required=True)
	expires = ndb.DateTimeProperty(required=True)
	shipdate = ndb.DateTimeProperty(required=True)
	shipprice = ndb.FloatProperty()
	local_pickup = ndb.StringProperty()
	bid_margin = ndb.FloatProperty()
	condition = ndb.StringProperty()

	watch_list = ndb.StringProperty(repeated=True) # List of names of users watching
	bid_hist = ndb.JsonProperty() # json of format: {"hist":[ [bidder, price], [bidder2, price],...] 
	payed = ndb.BooleanProperty(default=False) # True if the item has been payed for
	expired = ndb.BooleanProperty(default=False)
	paypal_email = ndb.StringProperty()

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
		return cls.query(cls.seller == seller)

	@classmethod
	def get_by_title(cls, title):
#		i = [item for item in cls.query() if item.title == title]
#		return i[0]
		return cls.query(cls.title == title).get()

	@classmethod
	def get_active(cls):
		return cls.query(Item.expired != True)

#	@classmethod
#	def all(cls, order=""):
#		return super(Item, cls).all()

	@classmethod
	@log_on_fail
	def all(cls, order="current_price"):
		result = get_all("items", Item)
		if result is None or memcache.get("updateitems"):
			result = list(super(Item, cls).all())
			set_all("items", result)
			memcache.set("allitems", result)
			memcache.set("updateitems", False)
			logging.info("DB Query for items")
		result.sort(key=lambda x: getattr(x, order))
		return result

	@classmethod
	@log_on_fail
	def delete(cls, item):
		del_from("items", item)
		super(Item, cls).delete(item)

class Notification(ndb.Model):
	""" This Model represents notifications Mondays
	   sends out to certain users or all users """

	receiver = ndb.StringProperty(required=True)
	sent = ndb.DateTimeProperty(required=True)
	content = ndb.TextProperty(required=True)

	@classmethod
	def new(cls, receiver, content):
		return cls(receiver=receiver, content=content, sent=gen_date2())

	@classmethod
	def get_by_receiver(cls, receiver):
		return cls.query(Notification.receiver == receiver).order(-cls.sent)

class Purchase(ndb.Model):
	'''a completed transaction'''
	item = ndb.IntegerProperty()
	owner = ndb.StringProperty()
	purchaser = ndb.StringProperty()
	created = db.DateTimeProperty(auto_now_add=True)
	status = ndb.StringProperty( choices=( 'NEW', 'CREATED', 'ERROR', 'CANCELLED', 'RETURNED', 'COMPLETED' ) )
	status_detail = ndb.StringProperty()
	secret = ndb.StringProperty() # to verify return_url
	debug_request = ndb.TextProperty()
	debug_response = ndb.TextProperty()
	paykey = ndb.StringProperty()
	shipping = ndb.TextProperty()
