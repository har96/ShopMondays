from google.appengine.api import memcache
from google.appengine.ext import webapp
from google.appengine.ext.webapp import template
import jinja2
from google.appengine.api import mail
from google.appengine.api import images
from google.appengine.api import urlfetch
from gaesessions import get_current_session
from STATE_LIST import STATE_LIST
from models import *
from helpers import *
import logging
import cgi
import os
import paypal_settings as settings
import paypal_adaptivepayment as paypal
import time
import json

VISITOR = Struct(name="Visitor", watch_list=[])
DESCRIPTION_LIMIT = 2000
TITLE_LIMIT = 50
MESSAGE_CHARLIMIT = 5000
CONDITIONS = ["New; Unopen unused", "Used; still in perfect condition", "Used; has some wear", "Old; still good as new", "For parts or not working"]
SHIP_OPTS = ["off", "on", "pickup"]
CATEGORIES = ["Sports/Outdoor", "Houshold Items", "Vehicle/Motor", "Electronics", "Other"]
RESERVED_USERNAMES = ["visitor", "multiple", "shopmondays", "username", "username", "mondays"]
RESERVED_PASSWORDS = ["password", "pass"]

# flagging info
STAR_LIMIT = 2
RATING_LIMIT = 3
FLAG_AMOUNT = 3
DISPLAY_FLAG = 1

class Handler( webapp.RequestHandler ):
	jinja_environment = jinja2.Environment(loader=jinja2.FileSystemLoader(os.path.dirname(__file__)))
	def render(self, temp, **format_args):
		self.jinja_environment.filters["mdtime"] = mdtime
		self.jinja_environment.filters["dollars"] = dollars
		self.jinja_environment.globals["balance"] = balance
		self.jinja_environment.globals["user_link"] = user_link
		self.jinja_environment.globals["render_stars"] = render_stars
		self.jinja_environment.globals["get_item_link"] = get_item_link
		template = self.jinja_environment.get_template(temp)
		self.response.out.write(template.render(format_args))

	def write_json(self, json_d):
		json_s = json.dumps(json_d)
        	self.response.headers['Content-Type'] = 'application/json; charset=UTF-8'
		self.response.out.write(json_s)

	def cookie_error(self):
		self.response.out.write("Sorry, Mondays encountered a problem. Invalid cookie,"
					"please sign in again")

	def get_user_cookie(self):
		return self.request.cookies.get("user_id")

	def get_user(self):
		session = get_current_session()
		cookie = self.get_user_cookie()
		if not cookie:
			return False
		if not User.valid_user_cookie(cookie):
			self.cookie_error()
			return False
		id = int(cookie.split("|")[0])
		user = User.get_by_id(id)
		if not session.has_key("user"+user.name):
			return False
		if not session["user"+user.name]:
			return False
		if id != int(session["user"+user.name]): # validate against session
			return False
		# add user to list of users logged on
#		if not session.has_key("users on") or type(session["users on"]) == type([]):
#			session["users on"] = {}
#		session["users on"][user.name] = time.time()
		return user

	def flash(self, message):
		user = self.get_user()
		if not user:
			user = VISITOR
		self.render("templates/flash.html", user=user, message=message)

	def format(self):
		if self.request.url.endswith(".json"):
			return "json"
		return "html"

class HomePage( Handler ):
	def write(self, **format_args):
		self.render("templates/home_page.html", **format_args)
	def get(self):
		self.write(items=Item.get_active().fetch(2))

class CheckExpiration( Handler ):
	def get(self):
		# Handle item expiration
		items = Item.get_active()
		for i in items:
			if i.did_expire():
				if i.num_bids:
					# item was bought
					# deal with seller
					msg = "You sold your %s to %s for %0.2f! Make sure you ship before %s!" \
							"\nSend to this address:\n%s\nDon't forget, you charged %s extra for shipping" \
							% (get_item_link(i), user_link(i.current_buyer), 
									i.get_price(),
									i.shipdate.strftime("%b %d"), User.get_by_name( i.current_buyer ).address(),
									i.shipprice)
					Message.send_mond_msg(i.seller, msg)
					seller = User.get_by_name(i.seller)
					seller.notify("You sold %s to %s for $%0.2f" % (get_item_link(i), user_link(i.current_buyer), i.get_price()))


					# deal with buyer
					if i.paypal_email:
						User.get_by_name(i.current_buyer).notify('You bought %s for $%0.2f!  Click <a href="/buy/%d">this link</a> to pay for it' % \
								(get_item_link(i), i.get_price(), i.key.integer_id()))
					else:
						form = """<form method="post" action="/payvote/%s"><button>Click here</button></form>""" % i.key.id()
						User.get_by_name(i.current_buyer).notify("You bought %s for $%0.2f!  %s <b>when you have payed seller.</b>  \
							 Don't forget to pay for shipping if necessary!" % (get_item_link(i), i.get_price(), form))
					i.bought_instantly = False
					i.put()
				else:
					# item did not sell
					seller = User.get_by_name(i.seller)
					history = seller.get_history()
					history["number of items not sold"] += 1
					seller.put_history(history)
					seller.notify("%s did not sell" % get_item_link(i))
				for username in i.watch_list:
					if i.current_buyer and username == i.current_buyer:
						continue
					User.get_by_name(username).notify("%s expired" % get_item_link(i))
				i.expired = True
				i.put()


class LoginPage( Handler ):
	def write(self, **format_args):
		self.render("templates/login_page.html", **format_args)
	def get(self):
		self.write(user=VISITOR)
	def post(self):
		# login user
		username = self.request.get("username")
		password = self.request.get("password")

		if not username or not password:
			self.write(error="Must have a username and a password", username=cgi.escape(username), user=VISITOR)

		u = User.get_by_name(username)
		if u is None or u is False:
			if self.format == "json":
				self.write_json({'valid':False})
			else:
				self.write(error="Invalid username and password combination", username=cgi.escape(username),user=VISITOR)
			return

		if users_match(u, hash_user_info(username, password, u.pepper, u.salt)[0]):
			session = get_current_session()
			session["user"+u.name] = u.key.id()
			self.response.headers.add_header("Set-Cookie", "user_id=" + str("%s|%s; Path=/" % (u.key.integer_id(), u.password)))
			self.redirect("/home")
		else:
			if self.format == "json":
				self.write_json({'valid':False})
				return
			self.write(error="Invalid username and password combination", username=cgi.escape(username))

class AboutPage( Handler ):
	def write(self, **format_args):
		self.render("templates/about_page.html", **format_args)
	def get(self):
		self.write(sponsers=get_sponsers())

class Register( Handler ):
	def write(self, **format_args):
		self.render("templates/register_page.html", **format_args)
	def get(self):
		self.write(state_list=STATE_LIST, user=Struct(name="Visitor"))
	def post(self):
		username = self.request.get("username")
		password = self.request.get("password")
		verify = self.request.get("verify")
		email = self.request.get("email")
		first_name = self.request.get("name1")
		last_name = self.request.get("name2")
		state = self.request.get("state").upper()
		city = self.request.get("city")
		zip = self.request.get("zip")
		address1 = self.request.get("address1")
		address2 = self.request.get("address2")

		if not state:
			logging.warning("hacker alert, state was not filled in on register")
			self.write(error="Please do not post to this url with a bot.  If you are not using a bot, reload the page.", user=Struct(user="Visitor"))
			return

		u_error = "Invalid Username" if not valid_username(username) else ""
		p_error = "Invalid Password" if not valid_password(password) else ""
		e_error = "Invalid Email" if not valid_email(email) else ""
		v_error = "Passwords Don't Match" if password != verify else ""
		fn_error = "First name required" if not first_name else "Too many characters in first name" if len(first_name) > 200 else ""
		ln_error = "Last name required" if not last_name else "Too many characters in last name" if len(last_name) > 200 else ""
		c_error = "Must specify city" if not city else "Too many characters in city field" if len(city) > 200 else ""
		z_error = "Invalid zip code" if not zip.isdigit() and len(zip) != 5 else ""
		a_error = "Invalid Address (line 1)" if not address1 else "Too many characters in address (line 1)" if len(address1) > 1000 else ""
		if len(address2) > 1000: a_error = "Too many characters in address (line 2)"
		if username.lower() in RESERVED_USERNAMES: u_error = "Sorry, this username is reserved."
		if password.lower() in RESERVED_PASSWORDS: p_error = "Sorry, the password you chose is not secure."
		if password == username: p_error = "Your password may not be the same as your username"
		
		if u_error or p_error or v_error or e_error or fn_error or ln_error or c_error or z_error or a_error:
			username = cgi.escape(username)
			email = cgi.escape(email)
			first_name = cgi.escape(first_name)
			last_name = cgi.escape(last_name)
			state = cgi.escape(state)
			city = cgi.escape(city)
			zip = cgi.escape(zip)
			address1 = cgi.escape(address1)
			address2 = cgi.escape(address2)
			self.write(e_error=e_error, fn_error=fn_error, ln_error=ln_error, c_error=c_error, \
					z_error=z_error, u_error=u_error, p_error=p_error, v_error=v_error, a_error=a_error, \
					username=username, name1=first_name, name2=last_name, email=email, state=state, \
					zip=zip, city=city, address1=address1, address2=address2, state_list=STATE_LIST, user=Struct(name="Visitor"))

			return
		elif User.get_by_name(username):
			self.write(u_exists_error="Username already exists", username=username, name1=first_name, name2=last_name, email=email,\
					state=state, zip=zip, city=city, address1=address1, address2=address2, state_list=STATE_LIST, user=Struct(name="Visitor"))
			return
		else:
			# Create and store user
			u = User.register(username, password, email, first_name, last_name, state, city, zip, address1, address2)
			u.put()
			# Set the user cookie
			self.response.headers.add_header("Set-Cookie", 'user_id='+str('%s|%s; Path=/' % (u.key.integer_id(), u.password)))
			# Set the user session
			session = get_current_session()
			session["user"+u.name] = u.key.id()

			# Send a message welcoming the user
			time.sleep(0.5) # Give db time to store
			Message.send_mond_msg(username, "Welcome to Mondays <b>%s</b>!" % u.first_name)
			logging.info("user: %s just registered" % u.name)
			u.notify("You created a Monday$ account")
			self.redirect("/home")

class UserHome( Handler ):
	def write(self, **format_args):
		self.render("templates/user_page.html", **format_args)
	def get(self):
		user = self.get_user()
		if not user:
			self.flash("You are not logged in")
			return
		if not user.active:
			self.response.out.write("""<div style="color: blue">You account is not currently active,
				please activate your account by verifying your email <a href="/activate">here</a></div>""")
			return
		else:
			useritems = [item for item in Item.get_by_seller(user.name) if not item.payed and not item.expired]
			watched = [Item.get_by_id(id) for id in user.watch_list if not Item.get_by_id(id) is None]
			notifications = Notification.get_by_receiver(user.name).fetch(3)

			if self.format() == "html":
				self.write(user=user, useritems=useritems, watch_list=watched, notifs=notifications)
				for n in notifications:
					if not n.read:
						n.read = True
						n.put()
			elif self.format() == "json":
				self.write_json({"items":[item.json(permission=False) for item in useritems], "watch list":[item.json(permission=False) for item in watched],
					"user":user.json()})


class CreateMessage( Handler ):
	def write(self, **format_args):
		self.render("templates/message_page.html", **format_args)
	def get(self):
		user = self.get_user()
		if not user:
			self.flash("You are not logged in")
			return

		if self.format() == "html":
			receiver = self.request.get("receiver")
			self.write(user=user, receiver=cgi.escape(receiver), usermessages=list(Message.get_user_messages(user.name)))
		elif self.format() == "json":
			self.write_json([msg.json() for msg in Message.get_user_messages(user.name)])
	def post(self):
		user = self.get_user()
		if not user:
			self.flash("You are not logged in")
			return

		del_id = self.request.get("delete_mes")
		if del_id:
			# remove user from message(s)' references
			try:
				del_id = int(del_id)
			except ValueError:
				msgs = Message.get_user_messages(user.name)
				for m in msgs: m.remove_reference(user.name)
				self.redirect("/message")
				return

			m = Message.get_by_id(int(del_id))
			if m: 
				m.remove_reference(user.name)
			self.redirect("/message")
			return

		# otherwise, send a message
		content = self.request.get("body")
		receiver = self.request.get("receiver")
		all = self.request.get("all")
				
		# ensure that the user entered content
		if not content:
			if self.format() == "html":
				self.write(user=user, error="Must have a content", body=cgi.escape(content), 
					 receiver=cgi.escape(receiver), usermessages=list(Message.get_user_messages(user.name)))
			else:
				self.write_json({"error":1})
			return
		# ensure that the user entered a valid receiver
		if (not receiver and user.name != "Mondays") or (not receiver and all != "on"):
			if self.format() == "html":
				self.write(user=user, error="You must have a receiver.", body=cgi.escape(content),
					usermessages=list(Message.get_user_messages(user.name)))
			else:
				self.write_json({"error":1, "error_msg":"You must specify a receiver."})
			return
		if len(receiver) > 1000 and user.name != "Mondays":
			if self.format() == "html":
				self.write(user=user, error="Too many characters in receiver field.", body=cgi.escape(content),
				usermessages=list(Message.get_user_messages(user.name)))
			else:
				self.write_json({"error":1, "error_msg":"Too many characters in receiver field."})
		if len(content) > MESSAGE_CHARLIMIT and user.name != "Mondays":
			if self.format() == "html":
				self.write(user=user, error="Too many characters in message.  %d max" % MESSAGE_CHARLIMIT, body=cgi.escape(content),
				usermessages=list(Message.get_user_messages(user.name)))
			else:
				self.write_json({"error":1, "error_msg":"Too many characters in message.  %d max" % MESSAGE_CHARLIMIT})

		receivers = receiver.split()
		if (not receivers and user.name != "Mondays") or (not receivers and all != "on"):
			if self.format() == "html":
				self.write(user=user, error="Invalid receivers.  You must enter names", body=cgi.escape(content),
						usermessages=list(Message.get_user_messages(user.name)))
			else:
				self.write_json({"error":1})
			return
		for name in receivers:
			if user.name == name:
				if self.format() == "html":
					self.write(user=user, error="You cannot send a message to yourself", body=cgi.escape(content),
							receiver=cgi.escape(receiver), usermessages=list(Message.get_user_messages(user.name)))
				else:
					self.write_json({"error":2})
				return
			if not name:
				if self.format() == "html":
					self.write(user=user, error="Invalid receiver, check the <em>To</em> box for leading or trailing spaces",
							body=cgi.escape(content), receiver=cgi.escape(receiver), usermessages=list(Message.get_user_messages(user.name)))
				else:
					self.write_json({"error":1})
				return
		all_users = User.query()
		found = 0
		for u in all_users:
			if u.name in receivers:
				found += 1
		if not found == len(receivers) and not all == "on":
			if self.format() == "html":
				self.write(user=user, error="One of the receivers does not exist", body=cgi.escape(content),
						receiver=cgi.escape(receiver), usermessages=list(Message.get_user_messages(user.name)))
			else:
				self.write_json({"error":3})
			return

		# send message
		id = user.key.integer_id()
		if all == "on":
			all_names = list(map(lambda u:u.name, User.query()))
			all_names.remove("Mondays")
			try:
				sender = User.get_by_id(id).name
				if sender == "Mondays":
					Message.send_mond_msg(all_names, content)
				else:
					self.write(user=sender, error="Please don't post to this uri with a bot")
					return
			except Exception, e:
				
				if self.format() == "html":
					self.write(user=user, error="Sorry, message did not send, an error occured.  Please tell Mondays: %s" % e,
						body=cgi.escape(content), receiver=cgi.escape(receiver), usermessages=list(Message.get_user_messages(user.name)))
				else:
					self.write_json({"error":4})
				logging.error("Message error:" + str(e))
				return
		else:
			sender = User.get_by_id(id).name
			if sender == "Mondays":
				Message.send_mond_msg(receivers, content)
			else: 
				Message.send_msg(sender, receivers, content)

		time.sleep(1)  # Make sure the data base writes the sent message before querying for user messages
		if self.format() == "html":
			self.write(user=user, usermessages=list(Message.get_user_messages(user.name)), success="Message was sent")
		else:
			self.write_json({"error":0})
	

class AddItem( Handler ):
	def write(self, **format_args):
		self.render("templates/additem_page.html", **format_args)
	def get(self):
		user = self.get_user()
		if not user:
			self.flash("You are not logged in")
			return
		self.write(user=user, list_option="auction")

	def post(self):
		seller = self.get_user()
		if not seller:
			self.flash("You are not logged in")
			return
		title = self.request.get("title")
		start_price = self.request.get("startprice")
		description = self.request.get("description")
		days_listed = self.request.get("days_listed")
		shipdays = self.request.get("shipdays")
		shipprice = self.request.get("shipprice")
		local_pickup = self.request.get("localpickup")
		condition = self.request.get("condition")
		paypal = self.request.get("paypal")
		list_option = self.request.get("list_option")
		instantprice = self.request.get("instantbuy_price")

		c_challenge = self.request.get("recaptcha_challenge_field")
		c_response = self.request.get("recaptcha_response_field")

		c_error_msg = ""
		valid = validate_captcha(c_challenge, c_response, self.request.remote_addr)
		logging.info(valid.error_code)
		if not valid.is_valid:
			c_error_msg = "Invalid Captcha Code.  Try again"

		v_error_msg = ""
		if not days_listed: v_error_msg = "You must fill in the field for days listed"
		if not list_option == "instant":
			if len(start_price) > 100:
				v_error_msg = "Too many chars in start price field"
			else:
				try:
					start_price = float(start_price)
				except ValueError:
					v_error_msg = "Invalid input for start price"
		else: start_price = 0.0
	        if not shipprice: shipprice = 0.0
		if shipprice and len(shipprice) > 100:
			v_error_msg = "Too many chars in start price field"
		else:
			try:
				shipprice = float(shipprice)
			except ValueError:
				v_error_msg = "Invalid input for shipping price"
		if not list_option in ("auction", "both", "instant"):
			v_error_msg = "Please do not post to this form"
		if not days_listed.isdigit(): v_error_msg = "Invalid input for days listed" 
		if local_pickup != "pickup"  and not shipdays or not shipdays.isdigit(): v_error_msg = "Invalid input for shipping time" 
		error_msg = "" if title else "Must have a title"
		if not v_error_msg and int(days_listed) > 10: v_error_msg = "An item can't be listed for more that 10 days"
		if not v_error_msg and int(shipdays) > 14: v_error_msg = "You must ship sooner than 15 days"
		if paypal and not verify_paypal_email(paypal, seller): v_error_msg = "Could not find a paypal account with this email"
		if len(description) > DESCRIPTION_LIMIT: v_error_msg = "You cannot have more than %d characters in description." % DESCRIPTION_LIMIT
		if len(title) > TITLE_LIMIT: v_error_msg = "You cannot have more than %d characters in title" % TITLE_LIMIT
		if list_option != "instant" and not start_price: error_msg = "Must have start price"

		if not condition in CONDITIONS:
			v_error_msg = "Condition does not exist.  Please do not post to this site with a bot"
		if not local_pickup in SHIP_OPTS:
			v_error_msg = "Shipping option does not exist.  Please do not post to this site with a bot"

		if not title: error_msg = "Must have title"
		if not description: error_msg = "Must have description"

		if list_option != "auction":
			if len(instantprice) > 100:
				v_error_msg = "Too many chars for instant price."
			else:
				try:
					instantprice = float(instantprice)
				except ValueError:
					v_error_msg = "Instant Buy price must be a valid decimal number"
		else:
			instantprice = 0.0
		if len(days_listed) > 30:
			v_error_msg = "Too many chars in days listed field"
		if len(shipdays) > 30:
			v_error_msg = "Too many chars in shipping days field"
	
		if self.request.get("img"): img = create_image(self.request.get("img"), 400, 400)
		# if it is an item that is being relisted and the user did not upload an image,
		# reuse old one.
		elif self.request.get("relist_image"): 
			try:
				img = Item.get_by_id(int(self.request.get("relist_image"))).image
			except ValueError:
				v_error_msg = "Must have an image"
		else:
			v_error_msg = "Must have an image"
		if v_error_msg or error_msg or c_error_msg:

			self.write(user=seller, error=error_msg, value_error=v_error_msg, title=cgi.escape(title), \
					price=cgi.escape(str(start_price)), desc=cgi.escape(description), \
					days_listed=cgi.escape(days_listed), shipdays=cgi.escape(str(shipdays)), local_pickup=cgi.escape(local_pickup),\
					shipprice=cgi.escape(str(shipprice)), condition=CONDITIONS.index(condition), list_option=list_option,\
					instantbuy_price=instantprice, cap_err=c_error_msg, image_id=self.request.get("relist_image"))
			return

		days_listed = int(days_listed)
		shipdays = int(shipdays) if shipdays else ""
		item = Item.get_new(seller.name, title, days_listed, shipdays, condition, current_price=start_price,
				description=description, shipprice=shipprice, local_pickup=local_pickup, list_option=list_option, instant_price=instantprice)

		item.image = img
		item.paypal_email = paypal
		item.put()
		seller.notify("You listed %s" % item.title)
		self.redirect("/item/%s" % item.key.id())

class ItemView( Handler ):
	def write(self, **format_args):
		self.render("templates/item_page.html", **format_args)
	def get(self, id):
		user = self.get_user()
		if not user:
			user = VISITOR
		item = Item.get_by_id(int(id))
		if not item:
			self.flash("Item does not exist")
			return

		comments = list(Message.get_user_messages(str(item.key.id())))
		comments.reverse()
		if self.format() == "html":
			# set up template vars
			shipdate = item.shipdate.strftime("%b  %d")
			expdate = item.expires.strftime("%b  %d  %T")
	
			template = render_item_info(item, user, BuyerRating, SellerRating)

			self.write(user=user, comments=comments, expdate=expdate, item=item, other_info=template, num_watchers=len(item.watch_list))
		elif self.format() == "json":
			permission = item.seller == user.name
			d = item.json(permission=permission)
			d.update({"comments":[c.json() for c in comments]})
			self.write_json(d)
	def post(self, id):
		buyer = self.get_user()
		if not buyer:
			self.response.out.write("you are not logged in")

		i = Item.get_by_id(int(id))
		shipdate = i.shipdate.strftime("%b  %d")
		expdate = i.expires.strftime("%b  %d  %T")

		price = self.request.get("price")
		comments=Message.get_user_messages(str(i.key.id()))
		comments = list(comments)
		comments.reverse()

		if buyer.name == i.seller:
			self.write(user=buyer, comments=comments, item=i, shipdate=shipdate, expdate=expdate,
					error="You cannot bid on items you sell", expire=i.expired, watchable=not i.key.integer_id() in buyer.watch_list,
					num_watchers=len(i.watch_list))
			return

		try:
			price = float(price)
		except ValueError:
			self.write(user=buyer, comments=comments, item=i, shipdate=shipdate,
					expdate=expdate, error = "Invalid price", expire=i.expired, 
					watchable=not i.key.integer_id() in buyer.watch_list, num_watchers=len(i.watch_list))

			return
		if not price >= (i.get_price() + i.bid_margin):
			self.write(user=buyer, item=i, comments=comments, shipdate=shipdate,
					expdate=expdate,
					error="Bid must be at least $%0.2f over price" % i.bid_margin,
					expire=i.expired, watchable=not i.key.integer_id() in watch_list,
					num_watchers=len(i.watch_list))

			return
		i.bid(buyer.name, price)
		buyer.notify("You just bid $%0.2f on %s" % (price, get_item_link(i)))
		User.get_by_name(i.seller).notify("%s just bid $%0.2f on %s" % (buyer.name, price, get_item_link(i)))
		for u in i.watch_list:
			User.get_by_name(u).notify("%s just bid $%0.2f on %s. Bid now!" % (buyer.name, price, get_item_link(i)))
		buyer.watch(i)
		self.redirect("/item/%s" % i.key.id())

class EditItem( Handler ):
	def write(self, **format_args):
		self.render("templates/edit_list_page.html", **format_args)

	def get(self, id):
		user = self.get_user()
		if not user:
			self.flash("You are not logged in")
			return

		id = int(id)
		item = Item.get_by_id(id)
		if item.seller != user.name:
			self.write(user=user, error="This is not your item.  You do not have permission to edit this item.")
			return

		if item.num_bids:
			self.write(error = "There are bids on this item, you may only edit the image.", user=user, item=item)
			return
		self.write( user=user, title=item.title, description=item.description, price=item.current_price, shipprice=item.shipprice,\
				cond=CONDITIONS.index(item.condition), ship=SHIP_OPTS.index(item.local_pickup), item=item, instantprice=item.instant_price)

	def post(self, id):
		user = self.get_user()
		if not user:
			self.response.out.write("You are not logged in")
			return

		id = int(id)
		item = Item.get_by_id(id)
		if item.seller != user.name:
			self.flash("This is not your item.  You do not have permission to edit this item.")
			return
		if item.expired:
			self.flash("This item has expired.  You may not edit it.")
			return

		# if the user clicked the delete button
		should_delete = self.request.get("delete")
		if should_delete:
			item.expired = True
			item.put()
			if item.current_buyer:
				Message.send_mond_msg(item.current_buyer, "Sorry, %s just deleted %s.  You cannot buy the item." % (item.seller, item.title))  
				User.get_by_name(item.current_buyer).notify("%s removed %s from the shop" % (item.seller, item.title))
				item.current_buyer = ""
				item.put()
			user.notify("You just removed %s from the shop" % item.title)
			self.redirect("/home")
			return
		# otherwise he/she clicked the update button
		title = self.request.get("title")
		description = self.request.get("description")
		price = self.request.get("price")
		shipprice = self.request.get("shipprice")
		localpickup = self.request.get("localpickup")
		image = self.request.get("image")
		condition = self.request.get("condition")
		instantprice = self.request.get("instantprice")

		t_error = p_error = s_error = error = ""
		try:
			price = float(price)
		except ValueError:
			p_error = "Price must be a valid amount"
		try:
			shipprice = float(shipprice)
		except ValueError:
			if localpickup != "pickup":
				s_error = "Shipping price must be a valid amount"

		i_error = ""
		if not title: t_error = "Must have a title"
		if not description: error = "Must have a description"
		if len(title) > TITLE_LIMIT: t_error = "Title can not be more than %d characters" % TITLE_LIMIT
		if len(description) > DESCRIPTION_LIMIT: error = "Description can not have more than %d characters" % DESCRIPTION_LIMIT
		if not price: p_error = "Must have price"
		if not condition in CONDITIONS: error = "Please do not post to this with a bot"
		if not localpickup in SHIP_OPTS: error = "Please do not post to this with a bot"
		if item.list_option != "auction":
			try:
				instantprice = float(instantprice)
			except ValueError:
				i_error = "Instant Buy price must be a valid decimal number"
			if not instantprice:
				i_error = "Must fill in Instant Buy price field with a number greater than 0"
		elif not instantprice:
			instantprice = 0.0

		if i_error or t_error or p_error or s_error or error:
			self.write(user=user, title=cgi.escape(title), description=cgi.escape(description), price=cgi.escape(str(price)), t_error=t_error, p_error=p_error, \
					s_error=s_error, shipprice=shipprice, localpickup='checked="checked"' if localpickup=="on" else "", item=item, error=error, \
					instantprice=instantprice, i_error=i_error, condition=CONDITIONS.index(condition)) 
			return
		if item.num_bids == 0:
			item.title = title
			item.description = description
			item.current_price = price
			item.instant_price = instantprice
			if localpickup != "pickup":
				item.shipprice = shipprice
			item.local_pickup = localpickup
			item.condition = condition
		if image: item.image = create_image(image, 400, 400)

		item.put()
		User.get_by_name(item.seller).notify("You successfully edited %s" % item.title)
		self.redirect("/item/%d" % id)

class Archive( Handler ):
	def write(self, **format_args):
		self.render("templates/archive_page.html", **format_args)
	def get(self):
		user = self.get_user()
		if not user:
			self.write(user=Struct(name="Visitor"), items=Item.get_active())
			return
		if self.format() == "html":
			self.write(user=user, items=Item.get_active(), show_limit=DISPLAY_FLAG)
		elif self.format() == "json":
			self.write_json([item.json(permission=False) for item in Item.get_active()])

class RequestMsg( Handler ):
	def write(self, **format_args):
		self.render("templates/request_page.html", **format_args)
	def get(self):
		user = self.get_user()
		if not user:
			self.flash("You are not logged in")
			return
		self.write(user=user, categories=CATEGORIES)
	def post(self):
		sender = self.get_user()
		if not sender:
			self.flash("You are not logged in.")
		item = self.request.get("item")
		category = self.request.get("category")
		if not item:
			self.write(user=sender, categories=CATEGORIES, error="Must specify an item")
			return
		if not category in CATEGORIES:
			self.flash("Please do not post with bot");
			return
		if len(item) > TITLE_LIMIT:
			self.write(user=sender, categories=CATEGORIES, error="Request must be less than %d chars" % TITLE_LIMIT)
			return
		if item in map(lambda r: r.title, Request.query().fetch(projection=["title"])):
			self.write(user=sender, categories=CATEGORIES, error="Item already exists on the <a href=\"/requests\">requests page</a>")
			return
		request = Request(title=item, category=category, creator=sender.name)
		request.put()
		self.redirect("/requests")

class ItemImage( Handler ):
	def get(self, id):
		item = Item.get_by_id( int(id) )
		if item.image:
			self.response.headers['Content-Type'] = "image/jpg"
			self.response.out.write(item.image)
		else:
			self.error(404)

class Activate(Handler):
	def write(self, **format_args):
		self.render("templates/activation_page.html", **format_args)
	def get(self):
		user = self.get_user()
		if not user:
			self.flash("You are not logged in")
			return
		self.write(user=user)
	def post(self):

		user = self.get_user()
		if not user:
			self.flash("You are not logged in")
			return
		input_dict = {}
		input_dict["email"] = self.request.get("email")
		if hasattr(user, "email") and user.email and user.email != input_dict["email"]:
			self.write(user=user, email=input_dict["email"], email_e="Email does not match your registration email")
			return
		if not user.first_name:
			input_dict["first_name"] = self.request.get("name1")
		if not user.last_name:
			input_dict["last_name"]= self.request.get('name2') 
		if not user.state:
			input_dict["state"] = self.request.get('state')
		if not user.city:
			input_dict["city"] = self.request.get('city')
		if not user.zip:
			input_dict["zip"] = int(self.request.get('zip'))
#		if not user.address:
#			if not self.request.get("address1"):
#				input_dict["address_e"] = "Must have an address"
#			input_dict["address"] = "%s\n%s\n%s %s %s" % (self.request.get("address1"), 
#					self.request.get("address2"), input_dict.get("city", None) or user.city, input_dict.get("state", None) or user.state,
#					input_dict.get("zip", None) or user.zip )

		error_dict = {}
		for attribute in input_dict:
			if getattr(user, attribute):
				continue
			elif not input_dict[attribute]:
				error_dict[attribute + "_e"] = "Invalid input for %s" % attribute
		if len(error_dict):
			self.write(user=user, **error_dict)
			return


		html_content = """ Please click this link to activate your Mondays user: \n<a href="http://www.shopmondays.com/activate/%d?c=%s">Activate</a>"""
		html_content = html_content % (user.key.integer_id(), hash_str(user.name + "1j2h3@$#klasd"))

		content = """ Please visit this page to activate your Mondays user: \nhttp://www.shopmondays.com/activate/%d?c=%s"""
		content = content % (user.key.integer_id(), hash_str(user.name + "1j2h3@$#klasd"))
		
#		send_email_to_user(user, "Mondays user activation", content)
		mail.send_mail(sender="shopmondays.com Support <harrison@shopmondays.com>",
			to="%s %s <%s>" % (user.first_name, user.last_name, input_dict["email"]),
			subject="Mondays user activation",
			body=content,
			html=html_content)

		self.response.out.write("You have been sent an email from ShopMondays. Please follow the email's instructions to activate your account. Thank you.")
		
		for attr in input_dict:
			if attr == "email":
				continue
			setattr(user, attr, input_dict[attr])
		user.put()
		return

class ActivateUser(Handler):
	def write(self, **format_args):
		self.render("templates/activate_page.html", **format_args)
	def get(self, id):
		user = self.get_user()
		user_from_id = User.get_by_id(int(id))
		if not user:
			self.write(user=user_from_id, c=self.request.get("c"))
			return
		else:
			if user.name != user_from_id.name:
				self.flash("Invalid User")
				return
			if user.active:
				self.flash("Already activated")
				return
			pw = self.request.get('c')
			if pw == hash_str(user.name + "1j2h3@$#klasd"):
				user.activate()
				logging.info("%s activated his/her account" % user.name)
				self.redirect("/home")
			else:
				self.flash("Invalid activation code.")
	def post(self, id):
		c = self.request.get("c")
		user = self.get_user()
		if user:
			# Post is not needed.  post is only if user is not logged in and needs to enter
			# his/her password
			self.redirect("/activate/%s?c=%s" % (id, c))
			return
		user = User.get_by_id(int(id))
		if user.active:
			self.flash("You are already active")
			return
		password = self.request.get("password")
		if hash_user_info(user.name, password, user.pepper, user.salt)[0] != user.password:
			self.write(error="Invalid password")
		else:
			if c == hash_str(user.name + "1j2h3@$#klasd"):
				user.activate()
				logging.info("%s activated his/her account with post" % user.name)
				self.response.headers.add_header("Set-Cookie", "user_id=" + str("%s|%s; Path=/" % (u.key.integer_id(), u.password)))
				self.redirect("/home")
			else:
				self.flash("Invalid activation code")
		
class ResetPassword(Handler):
	def write(self, **format_args):
		self.render("templates/reset_pw_page.html", **format_args)
	def get(self):
		cookie = self.get_user_cookie()
		if not User.valid_user_cookie(cookie):
			self.cookie_error()
			return
		user = User.get_by_id(int(cookie.split("|")[0]))
		self.write(user=user)
	def post(self):
		cookie = self.get_user_cookie()
		if not User.valid_user_cookie(cookie):
			self.cookie_error()
			return
		user = User.get_by_id(int(cookie.split("|")[0]))

		password = self.request.get("password")
		verify = self.request.get("verify")

		pw_error = v_error = ""

		if not valid_password(password):
			pw_error = "Invalid Password"
		if not verify == password:
			v_error = "Passwords do not match"

		if pw_error or v_error:
			self.write(user=user, pw_error=pw_error, v_error=v_error)
			return
		user.password = hash_user_info( user.name, user.password, user.salt, user.salt2)[0]
		user.put()

		self.response.headers.add_header("Set-Cookie", "user_id=%d|%s; Path=/;" % (user.key.integer_id(), user.password))
		self.redirect("/home")


class UserProfile(Handler):
	def write(self, **format_args):
		self.render("templates/user_profile_page.html", **format_args)
	def get(self, name):
		user = self.get_user()
		if not user:
			self.flash("You are not logged in")
			return

		pageuser = User.get_by_name(name)
		if not pageuser:
			if self.format() == "html":
				self.flash("No such user, go back and try again")
			elif self.format() == "json":
				self.write_json({"error":"No such user"})
			return
		listed = Item.get_by_seller(pageuser.name)
		bought = map(Item.get_by_id, pageuser.items_purchased)
		ratings = get_rating_data(pageuser, SellerRating, BuyerRating)

		permission = user.name == pageuser.name 
		if self.format() == "html":
			if permission:
				self.write(user=user, pageuser=pageuser, history=user.get_history(), bought=bought, listed=listed, ratings=ratings)
			else:
				self.write(user=user, pageuser=pageuser, bought=bought, listed=listed, ratings=ratings)
		elif self.format() == "json":
			j = user.json(permission=permission)
			j.update({"items listed":map(lambda item: {item.title:item.key.id()}, listed), "ratings":ratings})
			self.write_json(j)

class EditUserProfile(Handler):
	def write(self, **format_args):
		self.render("templates/user_profile_editpage.html", **format_args)
	def get(self, id):
		user = self.get_user()
		if not user:
			self.flash("you are not logged in")
			return

		pageuser = User.get_by_id(int(id))
		if not pageuser:
			self.flash("No such user, go back and try again")
			return
		if user.name != pageuser.name:
			self.flash("You cannot edit this user")
			return
		val_dict = {}
		val_dict["address1"] = user.address1
		val_dict["address2"] = user.address2
		val_dict["first_name"] = user.first_name
		val_dict["last_name"] = user.last_name
		val_dict["state"] = user.state
		val_dict["city"] = user.city
		val_dict["zip"] = user.zip
		val_dict["user"] = user
		val_dict["state_list"] = STATE_LIST
		
		self.write(**val_dict)
	
	def post(self, id):
		u = self.get_user()
		if not u:
			self.flash("You are not logged in")
			return
		pageuser = User.get_by_id(int(id))
		if pageuser.name != u.name:
			self.flash("You may not edit this user")
			return

		first_name = self.request.get("name1")
		last_name = self.request.get("name2")
		state = self.request.get("state")
		city = self.request.get("city")
		zip = self.request.get("zip")
		address1 = self.request.get("address1")
		address2 = self.request.get("address2")

		fn_error = "First name required" if not first_name else "Too many characters in first name" if len(first_name) > 200 else ""
		ln_error = "Last name required" if not last_name else "Too many characters in last name" if len(last_name) > 200 else ""
		s_error = "State does not exist in USA" if not state in STATE_LIST else ""
		c_error = "Must specify city" if not city else "Too many characters in city field" if len(city) > 200 else ""
		z_error = "Invalid zip code" if not zip.isdigit() or len(zip) != 5 else ""
		a_error = "Invalid Address (line 1)" if not address1 else "Too many characters in address (line 1)" if len(address1) > 1000 else ""
		if len(address2) > 1000: a_error = "Too many characters in address (line 2)" 
		
		if fn_error or ln_error or s_error or c_error or z_error or a_error:
			first_name = cgi.escape(first_name)
			last_name = cgi.escape(last_name)
			state = cgi.escape(state)
			city = cgi.escape(city)
			zip = cgi.escape(zip)
			address1 = cgi.escape(address1)
			address2 = cgi.escape(address2)
			update_user = object()
			
			self.write(user=u, fn_error=fn_error, ln_error=ln_error, s_error=s_error, c_error=c_error, \
					z_error=z_error, a_error=a_error, \
					first_name=first_name, last_name=last_name, state=state, \
					zip=zip, city=city, address1=address1, address2=address2,
					state_list=STATE_LIST)

			return
		else:
			# edit and store user
			u.first_name = first_name
			u.last_name = last_name
			u.state = state
			u.city = city
			u.zip = int(zip)
			u.address1 = address1
			u.address2 = address2
			u.put()

			logging.info("user: %s just edited his or her profile" % u.name)

			self.redirect("/user/%s" % u.name)

class AllUsers( Handler ):
	def write(self, **format_args):
		self.render("templates/user_all_page.html", **format_args)
	def get(self):
		user = self.get_user()
		if self.format() == "html":
			if not user:
				self.write(user=VISITOR, users=User.query())
			else:
				self.write(user=user, users=User.query())
		elif self.format() == "json":
			self.write_json([usr.json(permission=False) for usr in User.query()])

		
class Logout( Handler ):
	def get(self):
		user = self.get_user()
		if not user:
			self.redirect("/")
			return
		session = get_current_session()
		session["user"+user.name] = ""
		self.response.headers.add_header("Set-Cookie", "user-id=; Path=/")

		msg = self.request.get("msg")
		if msg:
			self.flash(msg)
		else:
			self.redirect("/")

class Buy( Handler ):
	""" Hands the user over to PayPal """
	def write(self, **format_args):
		self.render("templates/buy_item.html", **format_args)
	def get(self, item_id):
		user = self.get_user()
		if not user:
			self.flash("You are not logged in")
			return
		id = int(item_id)
		item = Item.get_by_id(id)
		if not item:
			self.flash("This item does not exist")
			return
		
		if user.name != item.current_buyer:
			self.flash("You did not purchase this item please leave the page.")
			return
		if not item.expired:
			self.flash("This item has not expired yet.")
			return
		if item.payed:
			self.flash("You have already payed for this item.")
			return

		if not item.paypal_email:
			self.flash("The seller does not accept paypal.<br>You must send the money another way")
			return

		self.write(item=item, user=user)

	def post(self, item_id):
		user = self.get_user()
		if not user:
			self.flash("You are not logged in")
			return
		paypal_email = self.request.get("email")
		if not paypal_email:
			self.write(user=user, error="You must enter the same email your paypal account uses")

		id = int(item_id)
		item = Item.get_by_id(id)
		
		if user.name != item.current_buyer:
			self.flash("You did not purchase this item please leave the page")
			return
		if not item.did_expire():
			self.flash("This item has not expired yet.")
			return
		if item.payed:
			self.flash("this item has been payed for")
			return

		if item.pay_votes or not item.paypal_email:
			self.flash("this item is being payed without paypal")
			return
		
		price = item.get_price(item.bought_instantly)
		if item.local_pickup == "off":
			price += item.shipprice
		elif item.local_pickup == "on":
			option = self.request.get("ship")
			if option == "ship":
				price += item.shipprice
			elif option != "pickup":
				self.error(501) # invalid value.  Must be a bot
		
		### send user to paypal
		(ok, pay) = self.start_purchase(item, paypal_email, price)
    		if ok:
      			self.redirect( pay.next_url().encode('ascii') ) # go to paypal
    		else:
      			data = {
        			'item': item,
        			'message': 'An error occurred during the purchase process',
				'user': user
      			}
			self.write(**data)

	def start_purchase(self, item, buyer_email, price):
    		purchase = Purchase( item=item.key.integer_id(), owner=item.seller, purchaser=item.current_buyer, status='NEW', secret=hash_str(make_salt()) )
  		purchase.put()
    		if settings.USE_IPN:
     			ipn_url = "%s/ipn/%s/%s/" % ( self.request.host_url, purchase.key(), purchase.secret )
    		else:
      			ipn_url = None
   		pay = paypal.Pay( 
     			 price, 
			 "http://www.shopmondays.com/paysuccess/%s?id=%d" % (purchase.secret, purchase.key.integer_id()), 
			 "http://www.shopmondays.com/item/%d" % (item.key.integer_id()),
			 self.request.remote_addr,
			 item.paypal_email,
  			 ipn_url,
			 shipping=settings.SHIPPING)

		purchase.debug_request = pay.raw_request
		purchase.debug_response = pay.raw_response
		purchase.paykey = pay.paykey()
    		purchase.put()
    
    		if pay.status() == 'CREATED':
      			purchase.status = 'CREATED'
	     		purchase.put()
      			return (True, pay)
    		else:
      			purchase.status = 'ERROR'
     		 	purchase.put()
      			return (False, pay)



class PaySuccess( Handler ):
	""" The user comes to this page after succesfully paying for
	    an item """
	def write(self, **format_args):
		self.render("templates/pay_success.html", **format_args)
	def get(self, purchase_secret):
		user = self.get_user()
		if not user:
			self.response.out.write("You are not logged in")
			return
		purchase = Purchase.get_by_id(int(self.request.get("id")))
		id = int(purchase.item)
		item = Item.get_by_id(id)
		
		
		if user.name != item.current_buyer:
			self.flash("You did not purchase this item please leave the page")
		if item.payed:
			self.flash("item has already been payed for")
		if purchase.secret != purchase_secret:
			self.error(501)
			return
		if purchase.status == "ERROR":
			self.flash("An error occured in the payment process")
			return
		if purchase.status == "COMPLETED":
			self.flash("This purchase has already been completed.")
			return
			
		item.payed = True
		item.put()

		# Deal with buyer
		buyer = User.get_by_name(item.current_buyer)
		history = buyer.get_history()
		history["money spent"] += item.get_price(item.bought_instantly)
		buyer.put_history(history)
		buyer.items_purchased.append(item.key.integer_id())
		buyer.put()
		buyer.notify("You payed %s for %s." % (item.seller, item.title))

		# deal with Seller
		seller = User.get_by_name(item.seller)
		history = seller.get_history()
		history["money earned"] += item.get_price(item.bought_instantly)
		history["number of items sold"] += 1
		seller.put_history(history)
		seller.notify("%s has payed for %s" % (user.name, item.title))

		purchase.status = "COMPLETED"
		purchase.put()


		self.write(item=item, user=user)

class AllNotifications( Handler ):
	""" Shows the user all his/her notifications """
	def write(self, **format_args):
		self.render("templates/notifications.html", **format_args)
	def get(self):
		user = self.get_user()
		if not user:
			self.flash("You are not logged in")
			return
		notifications = Notification.get_by_receiver(user.name)
		if self.format() == "html":
			self.write(user=user, notifications=notifications)
			for n in notifications:
				if not n.read:
					n.read = True
					n.put()
		elif self.format() == "json":
			self.write_json([n.json() for n in notifications])

class Watch( Handler ):
	def post(self, item_id):
		user = self.get_user()
		if not user:
			self.flash("You are not logged in.")
			return
		item = Item.get_by_id(int(item_id))
		if item.seller == user.name:
			self.flash("You cannot <em>watch</em> items you sell.")
			return
		# watch
		if not user.watch(item):
			self.flash("You are already watching this item")
		user.notify("You added %s to your watch list" % item.title)
		self.redirect("/item/%s" % item_id)

class Unwatch( Handler ):
	def post(self, item_id):
		user = self.get_user()
		if not user:
			self.flash("You are not logged in.")
			return
		item = Item.get_by_id(int(item_id))
		if not user.unwatch(item):
			self.flash("You are not watching this item")
			return
		user.notify("You just removed %s from your watch list" % item.title)
		self.redirect("/item/%s" % item_id)

class RelistItem( Handler ):
	def write(self, **format_args):
		self.render("templates/additem_page.html", **format_args)
	def get(self, item_id):
		user = self.get_user()
		if not user:
			self.response.out.write("You are not logged in")
			return
		item = Item.get_by_id(int(item_id))
		if not item:
			self.flash("item does not exist")
			return
		error = "If you want to change the image upload a new one."
		self.write(user=user, title=item.title, desc=item.description, price=item.initial_price or item.current_price, shipprice=item.shipprice,\
				local_pickup=item.local_pickup, condition=CONDITIONS.index(item.condition), paypal=item.paypal_email, error=error, image_id=item.key.id(),\
				list_option=item.list_option, instantbuy_price=item.instant_price)
	

class MarkPayed( Handler ):
	def post(self, id):
		user = self.get_user()
		if not user:
			self.flash("You are not logged in.")
			return
		item = Item.get_by_id(int(id))
		if not item:
			self.flash("Invalid id.  Item does not exist")
		elif user.name != item.current_buyer and user.name != item.seller:
			self.flash("You are not the buyer or seller of this item.")
		elif item.pay_votes >= 2:
			self.flash("This payment has already been confirmed")
		elif not item.pay_votes and user.name == item.seller: # buyer must make first vote
			self.flash("Buyer has not confirmed sending of money yet")
		elif item.pay_votes == 1 and user.name == item.current_buyer:
			self.flash("You have already marked this item as payed")
		else:
			if item.pay_votes is None:
				item.pay_votes = 0
			item.pay_votes += 1
			item.put()
			if item.pay_votes == 2:  # both buyer and seller have marked the item as payed
				item.payed = True
				item.put()

				# Deal with buyer
				buyer = User.get_by_name(item.current_buyer)
				history = buyer.get_history()
				history["money spent"] += item.get_price(item.bought_instantly)
				buyer.put_history(history)
				buyer.items_purchased.append(item.key.integer_id())
				buyer.put()
				buyer.notify("Your payment for %s had been confirmed by seller.  <a href=\"/sellerrating/%s\">Rate %s</a>" % (item.title, item.key.id(), item.seller))

				# deal with Seller
				seller = User.get_by_name(item.seller)
				history = seller.get_history()
				history["money earned"] += item.get_price(item.bought_instantly)
				history["number of items sold"] += 1
				seller.put_history(history)
				seller.notify("%s's purchase of %s has been confirmed. <a href=\"/buyerrating/%s\">Rate %s</a>" % (item.current_buyer, item.title, item.key.id(),
																item.current_buyer))
			else:
				seller = User.get_by_name(item.seller)
				seller.notify("""<form method="post" action="/payvote/%s">
							%s just sent payment for %s to you.  <button type="submit">Click here</button>
							<b>when you have received payment</b>""" % (item.key.id(), item.current_buyer, item.title))


			self.redirect("/item/%s" % id)

class RateBuyer( Handler ):
	def write(self, **format_args):
		self.render("templates/buyer_rating.html", **format_args)
	def get(self, item_id):
		user = self.get_user()
		if not user:
			self.flash("You are not logged in")
			return
		try:
			item_id = int(item_id)
		except ValueError:
			self.flash("Invalid id")

		item = Item.get_by_id(item_id)
		if not item:
			self.flash("Item does not exist")
		elif user.name != item.seller:
			self.flash("You are not the seller of the item")
		elif not item.expired:
			self.flash("You cannot rate buyer yet")
		elif not BuyerRating.get_by_item(item) is False:
			self.flash("You have already submitted feedback on this item")
		else:
			self.write(user=user, item=item)
	def post(self, item_id):
		user = self.get_user()
		if not user:
			self.flash("You are not logged in")
			return
		try:
			item_id = int(item_id)
		except ValueError:
			self.flash("Invalid id")

		item = Item.get_by_id(item_id)
		if not item:
			self.flash("Item does not exist")
		elif user.name != item.seller:
			self.flash("You are not the seller of the item")
		elif not item.expired:
			self.flash("You cannot rate buyer yet")
		elif not BuyerRating.get_by_item(item) is False:
			self.flash("You have already submitted feedback on this item")
		else:
			payment_speed = self.request.get("payment")
			com = self.request.get("communication")
			overall = self.request.get("overall")

			try:
				payment_speed = int(payment_speed)
				com = int(com)
				overall = int(overall)
			except ValueError:
				logging.warning("Hacker alert.  Buyer rating not int")
				self.flash("Please do not post with a bot.  Thanks!")
				return

			rating = BuyerRating(item=item.key.integer_id(), buyer=item.current_buyer, creator=item.seller, payment=payment_speed, communication=com, overall=overall)
			rating.put()
			User.get_by_name(item.current_buyer).notify("%s submitted feedback" % user.name)
			self.redirect("/item/%s" % item_id)

class RateSeller( Handler ):
	def write(self, **format_args):
		self.render("templates/seller_rating.html", **format_args)
	def get(self, item_id):
		user = self.get_user()
		if not user:
			self.flash("You are not logged in")
			return
		try:
			item_id = int(item_id)
		except ValueError:
			self.flash("Invalid id")

		item = Item.get_by_id(item_id)
		if not item:
			self.flash("Item does not exist")
		elif not item.expired:
			self.flash("You cannot rate seller yet")
		elif user.name != item.current_buyer:
			self.flash("You are not the buyer of the item")
		elif not SellerRating.get_by_item(item) is False:
			self.flash("You have already submitted feedback on this item")
		else:
			self.write(user=user, item=item)
	def post(self, item_id):
		user = self.get_user()
		if not user:
			self.flash("You are not logged in")
			return
		try:
			item_id = int(item_id)
		except ValueError:
			self.flash("Invalid id")

		item = Item.get_by_id(item_id)
		if not item:
			self.flash("Item does not exist")
		elif user.name != item.current_buyer:
			self.flash("You are not the buyer of the item")
		elif not item.expired:
			self.flash("You cannot rate seller yet")
		elif not SellerRating.get_by_item(item) is False:
			self.flash("You have already submitted feedback on this item")
		else:
			shipping = self.request.get('shipping')
			honesty = self.request.get('item')
			com = self.request.get('communication')
			overall = self.request.get('overall')

			try:
				shipping = int(shipping)
				honesty = int(honesty)
				com = int(com)
				overall = int(overall)
			except ValueError:
				logging.warning("Hacker alert.  Seller rating not int")
				self.flash("Please do not post with a bot.  Thanks!")
				return

			rating = SellerRating(item=item.key.integer_id(), seller=item.seller, creator=item.current_buyer, honesty=honesty, communication=com, overall=overall,
					shipping=shipping)
			rating.put()
			User.get_by_name(item.seller).notify("%s submitted feedback" % user.name)
			self.redirect("/item/%s" % item_id)

class ResetPassword( Handler ):
	def write(self, **format_args):
		self.render("templates/reset_pw_page.html", **format_args)
	def get(self, user_id):
		user = self.get_user()
		if not user:
			self.flash("You are not logged in")
		elif str(user.key.id()) != user_id:
			self.flash("You are not this user.")
		else:
			self.write(user=user)
	def post(self, user_id):
		user = self.get_user()
		if not user:
			self.flash("You are not logged in")
		elif str(user.key.id()) != user_id:
			self.flash("You are not this user")
		else:
			zip = self.request.get("zip")
			password = self.request.get("password")
			new_password = self.request.get("password_new")
			verify = self.request.get("verify")

			p_error = v_error = info_error = ""

			if not zip == str(user.zip):
				info_error = "Invalid zip-password combination"
			if not users_match(user, hash_user_info(user.name, password, user.pepper, user.salt)[0]):
				info_error = "Invalid zip-password combination"

			if len(new_password) < 5:
				p_error="Password must be more than 5 characters"
			if new_password != verify:
				v_error="Passwords do not match"
				
			if info_error or p_error or v_error:
				self.write(user=user, zip=zip, info_error=info_error, pw_error=p_error, v_error=v_error)
				return
			
			user.password, user.salt, user.pepper = hash_user_info(user.name, new_password)
			user.put()
			user.notify("You succesfully reset your password")
			self.redirect("/logout?msg=You+successfully+reset+your+password")

class ItemComment( Handler ):
	def post(self, id):
		sender = self.get_user()
		if not sender:
			self.flash("You are not logged in")
			return
		item = Item.get_by_id(int(id))
		if not item:
			self.flash("Item does not exist")
			return
		if item.expired:
			self.flash("Item has expired")
			return
		if not self.request.get("content"):
			self.flash("Comment must have content")
			return

		comment = Message(sender=sender.name, references=[str(item.key.id())], content=markup_text(cgi.escape(self.request.get("content"), quote=True)))
		comment.sent = gen_date2()
		comment.sent_str = comment.sent.strftime("%b %d  %T")
		comment.put()
		time.sleep(0.25)
		self.redirect("/item/%s" % id)

class EditComment( Handler ):
	def post(self, item_id, id):
		user = self.get_user()
		if not user:
			self.flash("You are not logged in")
			return
		comment = Message.get_by_id(int(id))
		if not comment:
			self.flash("Comment does not exist")
			return
		if not user.name == comment.sender:
			self.flash("Permission Denied")
			return
		if not item_id in comment.references:
			self.flash("This is not an item comment")
			return
		content = self.request.get("content")
		if not content:
			self.flash("Comment cannot be empty")
			return
		if len(content) > 1000:
			self.flash("Comments cannot have more than 1000 chars")
			return
		comment.content = content
		comment.put()
		self.redirect("/item/%s" % item_id)

class InstantBuy( Handler ):
	def write(self, **format_args):
		self.render("templates/instantbuy.html", **format_args)

	def get(self, item_id):
		user = self.get_user()
		if not user:
			self.flash("You are not logged in.")
			return
		item = Item.get_by_id(int(item_id))
		if not item:
			self.flash("Item does not exist.")
			return
		if item.list_option == "auction":
			self.flash("This item does not support instant buy.")
			return
		self.write(user=user, item=item)

	def post(self, item_id):
		user = self.get_user()
		if not user:
			self.flash("You are not logged in.")
			return
		item = Item.get_by_id(int(item_id))
		if not item:
			self.flash("Item does not exist.")
			return
		if item.list_option == "auction":
			self.flash("This item does not support instant buy.")
			return
		
		# item was bought
		# deal with seller
		msg = "You sold your %s to %s for %0.2f! Make sure you ship before %s!" \
				"\nSend to this address:\n%s\nDon't forget, you charged %s extra for shipping" \
				% (get_item_link(item), user_link(user.name), 
						item.get_price(True),
						item.shipdate.strftime("%b %d"), user.address,
						item.shipprice)
		Message.send_mond_msg(item.seller, msg)
		seller = User.get_by_name(item.seller)
		seller.notify("You sold %s to %s for $%0.2f" % (get_item_link(item), user_link(user.name), item.get_price(True)))

		item.expired = True
		item.current_buyer = user.name
		item.bought_instantly = True
		item.put()

		#notify watchers
		for u in item.watch_list:
			User.get_by_name(u).notify("%s sold to %s for $%0.2f" % (get_item_link(item), user_link(user.name), item.get_price(True)))

		# deal with buyer
		user.items_purchased.append(item.key.integer_id())
		user.put()
		if item.paypal_email:
			user.notify('You bought %s for $%0.2f!  Click <a href="/buy/%d">this link</a> to pay for it' % \
					(get_item_link(item), item.get_price(True), item.key.integer_id()))
			self.redirect("/buy/%s" % item.key.id())
		else:
			form = """<form method="post" action="/payvote/%s"><button>Click here</button></form>""" % item.key.id()
			User.get_by_name(item.current_buyer).notify("You bought %s for $%0.2f!  %s <b>when you have payed seller.</b>  \
					 Don't forget to pay for shipping if necessary!" % (get_item_link(item), item.get_price(True), form))
			self.redirect("/item/%s" % item.key.id())
class DeleteComment( Handler ):
	def post(self):
		item_id = self.request.get("item_id")
		comment_id = self.request.get("comment_id")
		user = self.get_user()
		if not user:
			self.flash("You are not logged in")
			return
		item = Item.get_by_id(int(item_id))
		if not item:
			self.flash("item does not exist")
			return
		comment = Message.get_by_id(int(comment_id))
		if not comment:
			self.flash("Comment does not exist")
			return
		if user.name != "Mondays" and user.name != comment.sender:
			self.flash("Permission Denied")
			return


		comment.remove_reference(str(item.key.id()))
		self.redirect("/item/%s" % item_id)

class ViewRequests( Handler ):
	def write(self, **format_args):
		self.render("templates/view_requests.html", **format_args)
	def get(self):
		user = self.get_user()
		if not user:
			self.flash("You are not logged in.")
			return
		filter_r = self.request.get("filter")
		order = self.request.get("order")

		if not filter_r: filter_r = "All"
		if not filter_r in (CATEGORIES+["All"]):
			self.flash("Please do not post with a bot")
		else:
			if filter_r == "All":
				if order == "Popularity":
					request_q = Request.query().order(-Request.num_likes)
				else:
					request_q = Request.query().order(-Request.posted)
			else:
				if order == "Popularity":
					request_q = Request.query(Request.category == filter_r).order(-Request.num_likes)
				else:
					request_q = Request.query(Request.category == filter_r).order(-Request.posted)
			self.write(user=user, categories=CATEGORIES, requests=request_q, filter_c=filter_r, order=order)

class Like( Handler ):
	def post(self, id):
		user = self.get_user()
		if not user:
			self.flash("You are not logged in.")
			return
		request = Request.get_by_id(int(id))
		if user.name == request.creator:
			self.flash("Please do not post with bot")
		elif user.name in request.likes:
			self.flash("Please do not post with bot")
		else:
			request.likes.append(user.name)
			request.put()

class Flag( Handler ):
	def post(self, id):
		user = self.get_user()
		if not user:
			self.flash("You are not logged in.")
			return
		item = Item.get_by_id(int(id))
		if not item:
			self.flash("Item does not exist")
			return
		if user.name == item.seller:
			self.flash("You cannot flag items you sell.");
			return
		if user.name in item.flaggers:
			self.flash("You may not flag an item twice.");
			return
		ratings = user.get_rating_data()
		if not (ratings["amount"] > RATING_LIMIT and ratings["user"] > STAR_LIMIT):
			self.flash('<span class="error">You may not flag items unless you have more than %d ratings and<br> \
					and average of over %d stars</span>' % (RATING_LIMIT, STAR_LIMIT))
			return
		
		# flag item
		if not item.flaggers:
			item.flaggers = []
		item.flaggers.append(user.name)
		item.put()
		if item.flags >= FLAG_AMOUNT:
			item.key.delete()
			logging.info("%s deleted from flagging.  flaggers: %s" % (item.title, item.flaggers))
			User.get_by_name(item.seller).notify("%s was deleted by user moderation" % item.title)
			for watcher in item.watch_list:
				User.get_by_name(watcher).notify("%s was deleted by user moderation" % item.title)
			if item.current_buyer:
				User.get_by_name(item.current_buyer).notify("%s was deleted by user moderation" % item.title)
		self.redirect("/item/%s" % id)
