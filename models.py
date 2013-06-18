from google.appengine.ext import ndb
from google.appengine.api import memcache
from helpers import *
import json
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
		self.put()

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

	def address(self):
		""" Returns the users rendered address """
		if self.address2:
			return "%s<br>%s<br>%s %s %s" % (self.address1, self.address2, self.city, self.state, self.zip)
		else:
			return "%s<br>%s %s %s" % (self.address1, self.city, self.state, self.zip)

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
		if not self.name in item.watch_list:  # check for inconsistency due to bug
			item.watch_list.append(self.name)
			item.put()
		return True

	def unwatch(self, item):
		""" Remove the item's id from the users watch_list.
		returns False if the item is not it the watch_list."""
		if not item.key.integer_id() in self.watch_list:
			return False
		self.watch_list.remove(item.key.integer_id())
		self.put()
		assert self.name in item.watch_list, "Inconsistency in watch_list"
		item.watch_list.remove(self.name)
		item.put()
		return True

	def notify(self, content):
		n = Notification(receiver=self.name, content=content)
		n.put()

	def json(self, permission=True):
		""" Returns json representation of user.
		   if not permission it won't return confindential info"""
		json_d = {"username":self.name, "first name":self.first_name,\
				"last name":self.last_name, "id":self.key.id()}
		if permission:
			json_d.update( {
				"active":self.active,
				"state":self.state,
				"city":self.city,
				"zip":self.zip,
				"address line 1":self.address1,
				"address line 2":self.address2,
				"id":self.key.id(),
				"email":self.email,
				"items purchased":self.items_purchased,
				"watch list":self.watch_list})
		return json_d

	def get_rating_data(self):
		""" Returns a dictionary of data regarding ratings of user "user" """
		ratings = {}
		ratings.update( {"positive":0,
				"negative": 0,
				"neutral": 0,
				"Bpositive": 0,
				"Bnegative": 0,
				"Bneutral": 0} )
	
		seller_qry = SellerRating.query(SellerRating.seller == self.name)
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

		buyer_qry = BuyerRating.query(BuyerRating.buyer == self.name)
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
	
		return ratings

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
	receiver = ndb.StringProperty(repeated=True)
	sent = ndb.DateTimeProperty(required=True)
	sent_str = ndb.StringProperty()
	# list of users that "own" the message.  This includes the sender and receivers.
	references = ndb.StringProperty(repeated=True)

	def json(self):
		""" returns json representation of Message """
		json_d = {"sender":self.sender,
				"receivers":self.receiver,
				"sent":list(self.sent.timetuple()),
				"image_url":"http://www.shopmondays.com/img_msg?id=%s" % self.key.id(),
				"content":self.content,
				"id":self.key.id()} # don't do references because api call will only get messages from a certain user
		return json_d

	@classmethod
	def get_from_sender(cls, sender):
		return cls.query(cls.sender == sender)

	@classmethod
	def get_from_receiver(cls, receiver):
		q = cls.query(cls.receiver == receiver).order(-cls.sent)
		return q

	@classmethod
	def get_user_messages(cls, name):
		""" Returns all message that include "name" in the references """
		return cls.query(cls.references == name).order(-cls.sent)

	@classmethod
	def send_msg(cls, sender, receivers, content):
		content=markup_text(cgi.escape(content, quote=True))
		td = gen_date2()
		m = cls(sender=sender, receiver=receivers, content=content, sent=td)
		receivers.append(sender)
		m.references = receivers
		m.sent_str = m.sent.strftime("%b %d  %T")
		m.put()

		# add msg to sender history
		user = User.get_by_name(sender)
		hist = user.get_history()
		if hist:
			hist["number of messages sent"] += 1
			user.put_history(hist)

		# add msg to receivers' history
		for receiver in receivers:
			user = User.get_by_name(receiver)
			hist = user.get_history()
			if hist:
				hist["number of messages received"] += 1
				user.put_history(hist)
	
	@classmethod
	def send_mond_msg(cls, receivers, content):
		content = markup_text(content)
		if not receivers:
			logging.error("invalid receiver in send_mond_msg. receiver:%s" % receiver)
			raise ValueError("There must be a valid receiver")
		if not content:
			logging.error("no content in send_mond_msg")
			raise ValueError("Message must have valid content")
		if type(receivers) == unicode:
			receivers = [receivers]
		# receiver copy
		td = gen_date2()
		m = cls(sender="Mondays", receiver=receivers, content=content, sent=td)
		m.references = receivers + ["Mondays"]
		m.sent_str = m.sent.strftime("%b %d  %T")
		m.put()

		# add msg to receivers history
		for receiver in receivers:
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

	def remove_reference(self, name):
		if not name in self.references:
			raise ValueError("%s is not in references.  Cannot delete Message." % name)
		self.references.remove(name)
		if not len(self.references):
			self.key.delete()
		else:
			self.put()

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
	pay_votes = ndb.IntegerProperty()
	expired = ndb.BooleanProperty(default=False)
	paypal_email = ndb.StringProperty()

	initial_price = ndb.FloatProperty()
	
	list_option = ndb.StringProperty(default="auction")
	instant_price = ndb.FloatProperty()
	bought_instantly = ndb.BooleanProperty(default=None)

	flaggers = ndb.StringProperty(repeated=True)
	flags = ndb.ComputedProperty(lambda self: len(self.flaggers))

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

	def json(self, permission=True):
		json_d = {"seller":{"name":self.seller, "id":User.get_by_name(self.seller).key.id()},
				"current buyer":{"name":self.current_buyer, "id":User.get_by_name(self.current_buyer).key.id()} if self.current_buyer else None,
				"title":self.title, "current price":self.current_price,
				"initial price":self.initial_price, "description":self.description,
				"expired":self.expired, "expires":list(self.expires.timetuple()),
				"listed":list(self.listed.timetuple()), "ships": list(self.shipdate.timetuple()),
				"image url":"http://www.shopmondays.com/img/%s" % self.key.id(), "shipping option": self.local_pickup,
				"shipping price":self.shipprice, "bid margin":self.bid_margin, 
				"condition":self.condition, "num bids":self.num_bids, "watchers":self.watch_list, "id":self.key.id(),
				"list option":self.list_option, "instant price":self.instant_price}
		if permission:
			json_d["paypal email"] = self.paypal_email
		return json_d

	def get_price(self, instant=False):
		""" Return the price of the item based on the list_option """
		if self.list_option == "instant":
			return self.instant_price
		elif self.list_option == "auction":
			return self.current_price
		elif instant:
			return self.instant_price
		else:
			return self.current_price

	@classmethod
	def get_new(cls, seller, title, days_listed, shipdays, condition, image=None, current_price=0.01, description="", local_pickup="off", shipprice=0.00,\
			list_option=-1, instant_price=0):
		expires = gen_date2(days_listed)
		shipdate = gen_date2(days_listed + shipdays)
		listed = gen_date2()
		i = cls(condition=condition, seller=seller, title=title, description=description,
					num_bids=0, current_buyer="", current_price=current_price,
					expires = expires, shipdate=shipdate, listed=listed,
					image=image, bid_margin=0.0, local_pickup=local_pickup, shipprice=shipprice,
					initial_price=current_price, list_option=list_option, instant_price=instant_price)
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

class Notification(ndb.Model):
	""" This Model represents notifications Mondays
	   sends out to certain users or all users """

	receiver = ndb.StringProperty(required=True)
	sent = ndb.DateTimeProperty(required=True, auto_now_add=True)
	content = ndb.TextProperty(required=True)
	read = ndb.BooleanProperty(default=False)

	def json(self):
		return {"receiver":self.receiver,
			"sent":list(self.sent.timetuple()),
			"content":self.content,
			"read": self.read}
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

class BuyerRating(ndb.Model):
	""" This Model represents a rating posted on a Buyer """

	payment = ndb.IntegerProperty(required=True)
	communication = ndb.IntegerProperty(required=True)
	overall = ndb.IntegerProperty(required=True)
	item = ndb.IntegerProperty(required=True)
	buyer = ndb.StringProperty(required=True)
	creator = ndb.StringProperty(required=True)
	date_created = ndb.DateTimeProperty(auto_now_add=True, required=True)

	@classmethod
	def get_by_item(cls, item):
		try:
			return cls.query(cls.item == item.key.integer_id()).fetch(1)[0]
		except:
			return False

class SellerRating(ndb.Model):
	""" This Model represents a rating posted on a Seller """

	shipping = ndb.IntegerProperty(required=True)
	honesty = ndb.IntegerProperty(required=True)
	communication = ndb.IntegerProperty(required=True)
	overall = ndb.IntegerProperty(required=True)
	item = ndb.IntegerProperty(required=True)
	seller = ndb.StringProperty(required=True)
	creator = ndb.StringProperty(required=True)
	date_created = ndb.DateTimeProperty(auto_now_add=True, required=True)

	@classmethod
	def get_by_item(cls, item):
		try:
			return cls.query(cls.item == item.key.integer_id()).fetch(1)[0]
		except:
			return False

class Request(ndb.Model):
	""" This Model represents a request posted by buyers """

	title = ndb.StringProperty(required=True) # title of item requested
	category = ndb.StringProperty(required=True) # category of request
	likes = ndb.StringProperty(repeated=True) # Users who have "liked" request
	num_likes = ndb.ComputedProperty(lambda r: len(r.likes) if r.likes else 0) # number of likes request has
	creator = ndb.StringProperty(required=True) # the name of user who posted request
	posted = ndb.DateTimeProperty(auto_now_add=True, required=True) # when the request was posted

	@classmethod
	def get_by_category(cls, category):
		""" return a query of Requests by category """
		return cls.query(cls.category == category).order(cls.num_likes)

	@classmethod
	def get_featured(cls):
		""" return top 15 requests """
		return cls.query().order(cls.num_likes)
