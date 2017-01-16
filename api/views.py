from django.shortcuts import render
from datasets.models import Dataset, Document
from django.http import HttpResponse
import json
import os
from django.conf import settings

def _acao_response(response):
	response['Access-Control-Allow-Origin'] = '*'
	response['Access-Control-Allow-Methods'] = 'GET'

def get_documents(request):
	ids = request.GET["ids"].split(',')
	full = "full" in request.GET
	result = []
	
	for document in Document.objects.filter(id__in = ids): 
		doc = {
			"id": document.id,
			"title": document.title,
			"url": document.url,
			"snippet": document.snippet,
		}
		
		time = document.time
		if not time is None:
			doc["date"] = time.strftime("%x");
			doc["time"] = time.strftime("%X");
		
		if full:
			document = Document.objects.filter(id = int(id))[0]
			file_name = os.path.join(settings.DATA_DIR, "datasets", document.dataset.text_id, "documents", str(document.model_id) + ".txt")
			with open(file_name, encoding = "utf-8") as f:
				doc["text"] = f.read()
		
		result.append(doc)
			
	response =  HttpResponse(json.dumps(result), content_type='application/json')  
	_acao_response(response)
	return response
	 
	
