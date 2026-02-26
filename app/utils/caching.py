import json
from app.extensions import redis_client

def cache_providers(providers_table):
    #Get available providers from the database
    providers = providers_table.query.all()
    providers = [p.to_dict() for p in providers]

    #serailize the list
    json_data = json.dumps(providers)

    redis_client.set("providers:json", json_data)


