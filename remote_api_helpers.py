import sys
sys.path.append("./pytz")

from models import *

def assign_comments_to_id():
	for item in Item.query():
	     print item.title+":"
  	     for msg in Message.get_user_messages(item.title):
      	 	     print msg.content
        	     try:
                	     msg.references.remove(item.title)
          	     except:
        	             print "removed"
    	             print "---------",
       	     	     msg.references.append(str(item.key.id()))
       	     	     print "---------",
        	     msg.put()
          	     print "---------"

