from models import User
from datetime import datetime

def user_link( username ):
	""" Returns a string containing a link to the
	user's profile page """
        user = User.get_by_name(username)
        if user and user.last_seen:
            cls = ""
            delta = (datetime.now() - user.last_seen).seconds
            if delta < 300: # 5 minutes
                cls = 'class=recent'
            if delta < 60:  # 1 minute
                cls = 'class=veryrecent'
            return '<a %s href="/user/%s">%s</a>' % (cls, username, username)
        elif user:
            return '<a href="/user/%s">%s</a>' % (username, username)
        else:
            return username
