from google.appengine.ext import webapp
register = webapp.template.create_template_register()

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

def user_link( username ):
	""" Returns a string containing a link to the
	user's profile page """
	return '<a href="www.shopmondays.com/user/%s">%s</a>' % (username, username)
	

register.simple_tag(balance)
register.filter(getkey)
register.filter(dollars)
register.filter(mdtime)
register.filter(user_link)
