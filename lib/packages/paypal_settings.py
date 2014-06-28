# settings for app

#PAYPAL_ENDPOINT = 'https://svcs.sandbox.paypal.com/AdaptivePayments/' # sandbox
PAYPAL_ENDPOINT = 'https://svcs.paypal.com/AdaptivePayments/' # production

#PAYPAL_PAYMENT_HOST = 'https://www.sandbox.paypal.com/au/cgi-bin/webscr' # sandbox
PAYPAL_PAYMENT_HOST = 'https://www.paypal.com/webscr' # production

PAYPAL_USERID = 'harrison_api1.hunterhayven.com'
PAYPAL_PASSWORD = 'Z4XAFY4428FQJSWQ'
PAYPAL_SIGNATURE = 'AFcWxV21C7fd0v3bYYYRCpSSRl31AX3B0kZKoPMQjGvpb14fIL84pAXE'
PAYPAL_APPLICATION_ID = 'APP-40W00710PJ825993E' # live id
PAYPAL_EMAIL = 'harrison@hunterhayven.com'

PAYPAL_COMMISSION = 0.2 # 20%

USE_CHAIN = False
USE_IPN = False
USE_EMBEDDED = False
SHIPPING = False # not yet working properly; PayPal bug

# EMBEDDED_ENDPOINT = 'https://paypal.com/webapps/adaptivepayment/flow/pay'
EMBEDDED_ENDPOINT = 'https://www.sandbox.paypal.com/webapps/adaptivepayment/flow/pay'

# url for sending NVP method calls
NVP_ADDRESS = "https://api-3t.sandbox.paypal.com/nvp"

# API access info
API_USERID = "harrison_api1.hunterhayven.com"
API_PWD = "Z4XAFY4428FQJSWQ"
API_SIGNATURE = "AFcWxV21C7fd0v3bYYYRCpSSRl31AX3B0kZKoPMQjGvpb14fIL84pAXE"
