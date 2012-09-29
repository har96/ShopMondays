from google.appengine.ext import webapp
register = webapp.template.create_template_register()


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

register.simple_tag(balance)
register.filter(getkey)
register.filter(dollars)
