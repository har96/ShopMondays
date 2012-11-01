from google.appengine.api import memcache
from google.appengine.ext import webapp
from google.appengine.ext.webapp import template
from google.appengine.api import mail
from google.appengine.api import images
from STATE_LIST import STATE_LIST
from models import *
from helpers import *
import logging
import cgi
import os


class Handler( webapp.RequestHandler ):
	def render(self, temp, **format_args):
		path = os.path.join(os.path.dirname(__file__), temp)
		self.response.out.write(template.render(path, format_args))

	def cookie_error(self):
		self.response.out.write("Sorry, Mondays encountered a problem. Invalid cookie,"
					"please sign in again")

	def get_user_cookie(self):
		return self.request.cookies.get("user_id")

	def get_user(self):
		cookie = self.get_user_cookie()
		if not cookie:
			return False
		if not User.valid_user_cookie(cookie):
			self.cookie_error()
			return False
		id = int(cookie.split("|")[0])
		user = User.get_by_id(id)
		return user

class HomePage( Handler ):
	def write(self, **format_args):
		self.render("templates/home_page.html", **format_args)
	def get(self):

		# Handle item expiration
		items = Item.all()
		for i in items:
			if i.did_expire():
				if i.num_bids:
					# item was bought
					# deal with seller
					msg = "You sold your %s to %s for %0.2f! Make sure you ship before %s!" \
							"\nSend to this address:\n%s\nDon't forget, you charged %s extra for shipping" \
							% (i.title, i.current_buyer, 
									i.current_price,
									i.shipdate.strftime("%b %d"), User.get_by_name( i.current_buyer ).address,
									i.shipprice)
					Message.send_mond_msg(i.seller, msg)
					seller = User.get_by_name(i.seller)
					history = seller.get_history()
					history["money earned"] += i.current_price
					history["number of items sold"] += 1
					seller.put_history(history)

					# deal with buyer
					msg = "You bought %s from %s for %s!\nThe seller has been given your address" % (i.title, i.seller, \
							i.current_price)
					Message.send_mond_msg(i.current_buyer, msg)
					buyer = User.get_by_name(i.current_buyer)
					history = buyer.get_history()
					history["money spent"] += i.current_price
					buyer.put_history(history)
				else:
					# item did not sell
					msg = "Sorry, %s didn't sell" % i.title
					Message.send_mond_msg(i.seller, msg)
					seller = User.get_by_name(i.seller)
					history = seller.get_history()
					history["number of items not sold"] += 1
					seller.put_history(history)


				Item.delete(i)

		self.write()

class LoginPage( Handler ):
	def write(self, **format_args):
		self.render("templates/login_page.html", **format_args)
	def get(self):
		self.write()
	def post(self):
		# login user
		username = self.request.get("username")
		password = self.request.get("password")

		if not username or not password:
			self.write(error="Must have a username and a password", username=cgi.escape(username))

		u = User.get_by_name(username)
		if u is None or u is False:
			self.write(error="Invalid username and password combination", username=cgi.escape(username))
			return

		if users_match(u, hash_user_info(username, password, u.pepper, u.salt)[0]):
			self.response.headers.add_header("Set-Cookie", "user_id=%s|%s; Path=/" % (u.key().id(), u.password))
			self.redirect("/home")
		else:
			self.write(error="Invalid username and password combination", username=cgi.escape(username))

class AboutPage( Handler ):
	def write(self):
		self.render("templates/about_page.html")
	def get(self):
		self.write()

class Register( Handler ):
	def write(self, **format_args):
		self.render("templates/register_page.html", **format_args)
	def get(self):
		self.write(state_list=STATE_LIST)
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
			self.write(error="Please do not post to this url with a bot.  If you are not using a bot, reload the page.")
			return

		u_error = "Invalid Username" if not valid_username(username) else ""
		p_error = "Invalid Password" if not valid_password(password) else ""
		e_error = "Invalid Email" if not valid_email(email) else ""
		v_error = "Passwords Don't Match" if password != verify else ""
		fn_error = "First name required" if not first_name else ""
		ln_error = "Last name required" if not last_name else ""
		c_error = "Must specify city" if not city else ""
		z_error = "Invalid zip code" if not zip.isdigit() else ""
		a_error = "Invalid Address (line 1)" if not address1 else ""
		
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
					zip=zip, city=city, address1=address1, address2=address2, state_list=STATE_LIST)

			return
		elif User.get_by_name(username):
			self.write(u_exists_error="Username already exists", username=username, name1=first_name, name2=last_name, email=email,\
					state=state, zip=zip, city=city, address1=address1, address2=address2, state_list=STATE_LIST)
			return
		else:
			# Create and store user
			u = User.register(username, password, email, first_name, last_name, state, city, zip, address1, address2)
			u.put()
			# Set the user cookie
			self.response.headers.add_header("Set-Cookie", 'user_id=%s|%s; Path=/' % (u.key().id(), u.password))

			# Send a message welcoming the user
			Message.send_mond_msg(username, "Welcome to Mondays <b>%s</b>!" % u.first_name)
			logging.info("user: %s just registered" % u.name)
			self.redirect("/home")

class UserHome( Handler ):
	def write(self, **format_args):
		self.render("templates/user_page.html", **format_args)
	def get(self):
		user = self.get_user()
		if not user:
			self.response.out.write("You are not logged in")
			return
		if not user.active:
			self.response.out.write("""<div style="color: blue">You account is not currently active,
				please activate your account <a href="/activate">here</a></div>""")
			return
		else:
			msgs = Message.get_from_receiver(user.name)
			useritems = Item.get_by_seller(user.name)
	
			self.write(user=user, usermessages=msgs, useritems=useritems)
	def post(self):
		user = self.get_user()
		if not user:
			self.response.out.write("You are not logged in")
			return

		del_id = self.request.get("delete_mes")
		if del_id == "all":
			msgs = Message.get_from_receiver(user.name)
			for m in msgs: Message.delete(m)
			self.redirect("/home")
			return
		try:
			del_id = int(del_id)
		except ValueError:
			raise AssertionError("Invalid value del_mes: %s.  Send this error code to Mondays: 32-211" % del_id)
		m = Message.get_by_id(int(del_id))
		if m: 
			Message.delete(m)
		self.redirect("/home")


class CreateMessage( Handler ):
	def write(self, **format_args):
		self.render("templates/message_page.html", **format_args)
	def get(self):
		user = self.get_user()
		if not user:
			self.response.out.write("You are not logged in")
			return

		receiver = self.request.get("receiver")
		self.write(user=user, receiver=cgi.escape(receiver))
	def post(self):
		content = self.request.get("body")
		receiver = self.request.get("receiver")
		image = self.request.get("img")
		all = self.request.get("all")
		user = self.get_user()
		if not user:
			self.response.out.write("You are not logged in")
			return
		
		# ensure that the user entered content
		if not content:
			self.write(user=user, error="Must have a content", body=cgi.escape(content), 
				 receiver=cgi.escape(receiver))
			return

		# ensure that the user entered a valid receiver
		all_users = User.all()
		found = False
		for u in all_users:
			if receiver == u.name:
				found = True
				break
		if not found and not all == "on":
			self.write(user=user, error="User does not exist", body=cgi.escape(content),
					receiver=cgi.escape(receiver))
			return

		# send message
		id = user.key().id()
		if all == "on":
			try:
				sender = User.get_by_id(id).name
				if sender == "Mondays":
					for u in all_users:
						memcache.set("%supdate" % u.key().id(), True)
						Message.send_mond_msg(u.name, content, image or None)
				else:
					for u in all_users:
						memcache.set("%supdate" % u.key().id(), True)
						Message.send_msg(sender, u.name, content, image or None)
			except Exception, e:
				
				self.write(user=sender, error="Sorry, message did not send, an error occured: %s" % e,
					body=cgi.escape(content), receiver=cgi.escape(receiver))
				logging.error("Message error:" + str(e))
				return
		else:
			sender = User.get_by_id(id).name
			if sender == "Mondays":
				memcache.set("%supdate" % User.get_by_name(receiver).key().id(), True)
				Message.send_mond_msg(receiver, content, image or None)
			else: 
				memcache.set("%supdate" % User.get_by_name(receiver).key().id(), True)
				Message.send_msg(sender, receiver, content, image or None)

		self.redirect("/home")

class AddItem( Handler ):
	def write(self, **format_args):
		self.render("templates/additem_page.html", **format_args)
	def get(self):
		user = self.get_user()
		if not user:
			self.response.out.write("You are not logged in")
			return
		self.write(user=user)

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
		shipprice = self.request.get("shipprice")
		local_pickup = self.request.get("localpickup")
		condition = self.request.get("condition")

		if not days_listed: days_listed = "7"
		v_error_msg = ""
		try:
			start_price = float(start_price)
		except ValueError:
			v_error_msg = "Invalid input for start price"
	        if not shipprice: shipprice = 0.0
		try:
			shipprice = float(shipprice)
		except ValueError:
			v_error_msg = "Invalid input for shipping price"
		if not days_listed.isdigit(): v_error_msg = "Invalid input for days listed" 
		if local_pickup != "pickup"  and not shipdays or not shipdays.isdigit(): v_error_msg = "Invalid input for shipping time" 
		error_msg = "" if title and start_price else "Must have a title and start price"
#		if has_whitespace(title): error_msg = "Title cannot have spaces,  can use underscores '_'"
		if not v_error_msg and int(days_listed) > 10: v_error_msg = "An item can't be listed for more that 10 days"
		if not v_error_msg and int(shipdays) > 14: v_error_msg = "You must ship sooner than 15 days"
		

		if v_error_msg or error_msg:

			conditions = ["New; Unopen unused", "Used; still in perfect condition", "Used; has some wear", "Old; still good as new"]
			self.write(user=seller, error=error_msg, value_error=v_error_msg, title=cgi.escape(title), \
					price=cgi.escape(str(start_price)), desc=cgi.escape(description), \
					days_listed=cgi.escape(days_listed), shipdays=cgi.escape(str(shipdays)), local_pickup=cgi.escape(local_pickup),\
					shipprice=cgi.escape(str(shipprice)), condition=conditions.index(condition))
			return
		days_listed = int(days_listed)
		shipdays = int(shipdays) if shipdays else ""
		item = Item.get_new(seller.name, title, days_listed, shipdays, condition, current_price=start_price,
				description=description, shipprice=shipprice, local_pickup=local_pickup)
		if self.request.get("img"): item.image = create_image(self.request.get("img"), 400, 400)
		item.put()
		self.redirect("/home")

class ItemView( Handler ):
	def write(self, **format_args):
		self.render("templates/item_page.html", **format_args)
	def get(self, id):
		cookie = self.get_user_cookie()
		if User.valid_user_cookie(cookie):
			user = User.get_by_id(int(cookie.split("|")[0]))
			self.response.headers.add_header("Set-Cookie", "item_id=%s" % id)
			item = Item.get_by_id(int(id))
			shipdate = item.shipdate.strftime("%b  %d")
			expdate = item.expires.strftime("%b  %d  %T")
			self.write(user=user, shipdate=shipdate, expdate=expdate, item=item)
		else:
			self.cookie_error()
	def post(self, id):
		buyer = self.get_user()
		if not buyer:
			self.response.out.write("you are not logged in")

		id = self.request.cookies.get("item_id")
		i = Item.get_by_id(int(id))
		shipdate = i.shipdate.strftime("%b  %d")
		expdate = i.expires.strftime("%b  %d  %T")

		price = self.request.get("price")

		if buyer.name == i.seller:
			self.write(user=buyer, item=i, shipdate=shipdate, expdate=expdate,
					error="You cannot bid on items you sell")
			return

		try:
			price = float(price)
		except ValueError:
			self.write(user=buyer, item=i, shipdate=shipdate,
					expdate=expdate, error = "Invalid price")
			return
		if not price >= (i.current_price + i.bid_margin):
			self.write(user=buyer, item=i, shipdate=shipdate,
					expdate=expdate,
					error="Bid must be at least $%0.2f over price" % i.bid_margin)
			return
		i.bid(buyer.name, price)
		self.redirect("/home")

class EditItem( Handler ):
	def write(self, **format_args):
		self.render("templates/edit_list_page.html", **format_args)

	def get(self, id):
		user = self.get_user()
		if not user:
			self.response.out.write("You are not logged in")
			return

		id = int(id)
		item = Item.get_by_id(id)
		if item.seller != user.name:
			self.write(error="This is not your item.  You do not have permission to edit this item.")
			return

		if item.num_bids:
			self.write(error = "There are bids on this item, you may only edit the image.", user=user, item=item)
			return
		conditions = ["New; Unopen unused", "Used; still in perfect condition", "Used; has some wear", "Old; still good as new"]
		shipping_opts = ["on", "off", "pickup"]
		self.write( user=user, title=item.title, description=item.description, price=item.current_price, shipprice=item.shipprice,\
				cond=conditions.index(item.condition), ship=shipping_opts.index(item.local_pickup), item=item)

	def post(self, id):
		user = self.get_user()
		if not user:
			self.response.out.write("You are not logged in")
			return

		id = int(id)
		item = Item.get_by_id(id)
		if item.seller != user.name:
			self.write(error="This is not your item.  You do not have permission to edit this item.")
			return

		# if the user clicked the delete button
		should_delete = self.request.get("delete")
		if should_delete:
			Item.delete(item)
			if item.current_buyer:
				Message.send_mond_msg(item.current_buyer, "Sorry, %s just deleted %s." % (item.seller, item.title))  
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

		t_error = p_error = s_error = ""
		try:
			price = float(price)
		except ValueError:
			p_error = "Price must be a valid amount"
		try:
			shipprice = float(shipprice)
		except ValueError:
			s_error = "Shipping price must be a valid amount"

		if not title: t_error = "Must have a title"
		if not price: p_error = "Must have price"

		if t_error or p_error or s_error:
			self.write(title=cgi.escape(title), description=cgi.escape(description), price=cgi.escape(str(price)), t_error=t_error, p_error=p_error, \
					s_error=s_error, shipprice=shipprice, localpickup='checked="checked"' if localpickup=="on" else "", item=item) 
			return
		if not item.num_bids:
			item.title = title
			item.description = description
			item.price = price
			item.shipprice = shipprice
			item.local_pickup = localpickup
			item.condition = condition
		if image: item.image = create_image(image, 400, 400)

		item.put()
		self.redirect("/item/%d" % id)

class Archive( Handler ):
	def write(self, **format_args):
		self.render("templates/archive_page.html", **format_args)
	def get(self):
		cookie = self.get_user_cookie()
		if User.valid_user_cookie(cookie):
			user = User.get_by_id(int(cookie.split("|")[0]))
			self.write(user=user, items=Item.all(order="listed"))
		else: self.cookie_error()

class RequestMsg( Handler ):
	def write(self, **format_args):
		self.render("templates/request_page.html", **format_args)
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

class ItemImage( Handler ):
	def get(self, id):
		item = Item.get_by_id( int(id) )
		if item.image:
			self.response.headers['Content-Type'] = "image/jpg"
			self.response.out.write(item.image)
		else:
			self.error(404)
class MsgImage(Handler):
	def get(self):
		msg = Message.get_by_id(int(self.request.get("id")))
		if msg.image:
			self.response.headers['Content-Type'] = "image/jpg"
			self.response.out.write(msg.image)
		else:
			self.error(404)

class Activate(Handler):
	def write(self, **format_args):
		self.render("templates/activation_page.html", **format_args)
	def get(self):
		cookie = self.get_user_cookie()
		if not User.valid_user_cookie(cookie):
			self.cookie_error()
			return
		user = User.get_by_id(int(cookie.split("|")[0]))
		self.write(user=user)
	def post(self):
		did_enter_email = False

		cookie = self.get_user_cookie()
		if not User.valid_user_cookie(cookie):
			self.cookie_error()
			return
		user = User.get_by_id(int(cookie.split("|")[0]))
		input_dict = {}
		input_dict["email"] = self.request.get("email")
		if hasattr(user, "email") and user.email and user.email != input_dict["email"]:
			self.write(user=user, email=input_dict["email"], email_e="Email does not match your registration email")
			return
		did_enter_email = True
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
		if not user.address:
			if not self.request.get("address1"):
				input_dict["address_e"] = "Must have an address"
			input_dict["address"] = "%s\n%s\n%s %s %s" % (self.request.get("address1"), 
					self.request.get("address2"), input_dict.get("city", None) or user.city, input_dict.get("state", None) or user.state,
					input_dict.get("zip", None) or user.zip )

		error_dict = {}
		for attribute in input_dict:
			if getattr(user, attribute):
				continue
			elif not input_dict[attribute]:
				error_dict[attribute + "_e"] = "Invalid input for %s" % attribute
		if len(error_dict):
			self.write(user=user, **error_dict)
			return


		if did_enter_email:
			content = """ Please visit this page to activate your user: www.shopmondays.com/activate/%d
				Copy and paste this code into the "Activate code" box: %s"""
			content = content % (user.key().id(), hash_str(user.name + "1j2h3@$#klasd"))
			
#			send_email_to_user(user, "Mondays user activation", content)
			mail.send_mail(sender="harrison@shopmondays.com",
				to=input_dict["email"],
				subject="Mondays user activation",
				body=content)
	
			self.response.out.write("You have been sent an email containing instructions for what to do next.  Thank you.<br><br>"
					"Note: please don't close your browser until you have activated your user or have failed to do so.")
		
			self.response.headers.add_header("Set-Cookie", "activation_info=%s; Path=/;" % (input_dict["email"],) )
#				datetime.strftime("%a, %d-%b-%Y %X %Z"))
			for attr in input_dict:
				if attr == "email":
					continue
				setattr(user, attr, input_dict[attr])
			user.put()
			return
		user.activate( **input_dict )
		user.put()
		logging.info("user: %s just activated his or her account" % user.name)
		self.redirect("/home")

class ActivateUser(Handler):
	def write(self, **format_args):
		self.render("templates/activate_page.html", **format_args)
	def get(self, id):
		user = User.get_by_id(int(id))
		self.response.headers.add_header("Set-Cookie", "user_id=%s|%s Path=/;")
		self.write(user=user)
	def post(self, id):
		user = User.get_by_id(int(id))
		if not user:
			self.response.out.write("<b>Sorry,</b> this user does not exist.  You cannot activate.")
			return
		pw = self.request.get('password')
		if pw == hash_str(user.name + "1j2h3@$#klasd"):
			activation_email = self.request.cookies.get("activation_info")
			user.activate(email=activation_email)
			user.put()
			self.redirect("/home")
		else:
			self.write(user=user, error="Invalid activation code.")
		
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

		self.response.headers.add_header("Set-Cookie", "user_id=%d|%s; Path=/;" % (user.key().id(), user.password))
		self.redirect("/home")


class UserProfile(Handler):
	def write(self, **format_args):
		self.render("templates/user_profile_page.html", **format_args)
	def get(self, id):
		user = self.get_user()
		if not user:
			self.response.out.write("You are not logged in")
			return

		pageuser = User.get_by_id(int(id))
		if not pageuser:
			self.response.out.write("No such user, go back and try again")
			return
		if user.name == pageuser.name:
			self.write(user=user, pageuser=pageuser, history=user.get_history())
		else:
			self.write(user=user, pageuser=pageuser)

class EditUserProfile(Handler):
	def write(self, **format_args):
		self.render("templates/user_profile_editpage.html", **format_args)
	def get(self, id):
		user = self.get_user()
		if not user:
			self.response.out.write("you are not logged in")
			return

		pageuser = User.get_by_id(int(id))
		if not pageuser:
			self.response.out.write("No such user, go back and try again")
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
		
		self.write(**val_dict)
	
	def post(self, id):
		u = self.get_user()
		if not u:
			self.response.out.write("You are not logged in")
			return

		first_name = self.request.get("name1")
		last_name = self.request.get("name2")
		state = self.request.get("state")
		city = self.request.get("city")
		zip = self.request.get("zip")
		address1 = self.request.get("address1")
		address2 = self.request.get("address2")

		fn_error = "First name required" if not first_name else ""
		ln_error = "Last name required" if not last_name else ""
		s_error = "State does not exist in USA" if not state in STATE_LIST else ""
		c_error = "Must specify city" if not city else ""
		z_error = "Invalid zip code" if not zip.isdigit() else ""
		a_error = "Invalid Address (line 1)" if not address1 else ""
		
		if fn_error or ln_error or s_error or c_error or z_error or a_error:
			first_name = cgi.escape(first_name)
			last_name = cgi.escape(last_name)
			state = cgi.escape(state)
			city = cgi.escape(city)
			zip = cgi.escape(zip)
			address1 = cgi.escape(address1)
			address2 = cgi.escape(address2)
			update_user = object()
			
			self.write(fn_error=fn_error, ln_error=ln_error, s_error=s_error, c_error=c_error, \
					z_error=z_error, a_error=a_error, \
					first_name=first_name, last_name=last_name, state=state, \
					zip=zip, city=city, address1=address1, address2=address2)

			return
		else:
			# edit and store user
			u.first_name = first_name
			u.last_name = last_name
			u.state = state
			u.city = city
			u.zip = int(zip)
			u.address = "%s<br>%s<br>%s %s %s" % (address1, address2, city, state, zip)
			u.address1 = address1
			u.address2 = address2
			u.put()

			logging.info("user: %s just edited his or her profile" % u.name)

			self.redirect("/user/%s" % id)

class AllUsers( Handler ):
	def write(self, **format_args):
		self.render("templates/user_all_page.html", **format_args)
	def get(self):
		self.write(users=User.all(order="name"))

		
class Logout( Handler ):
	def get(self):
		self.response.headers.add_header("Set-Cookie", "user-id=; Path=/")
		self.redirect("/")
