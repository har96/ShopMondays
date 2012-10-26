
function delete_msg() {
	var httpRequest;
	if (window.XMLHttpRequest) { // Mozilla, Safari, ...
	        httpRequest = new XMLHttpRequest();
	} else if (window.ActiveXObject) { // IE 8 and older
  	        httpRequest = new ActiveXObject("Microsoft.XMLHTTP");
	}
	httpRequest.onreadystatechange = processServerResponse;
	httpRequest.open("POST", "www.shopmondays.com/delete_msg/###", true);
	httpRequest.send(null);
}

function processServerResponse() {
	;
}

