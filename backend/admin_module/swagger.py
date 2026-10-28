"""Swagger 2.0 contract consumed by Flasgger and exportable for the team."""
def schema(properties, required=None):
    return {'type': 'object', 'properties': properties, 'required': required or list(properties)}

def string(example):
    return {'type': 'string', 'example': example}

def specification():
    reason = string('Updated after operations review')
    version = {'type': 'integer', 'example': 1}
    fare = schema({**{k: string(v) for k,v in {'base_fare':'40.00','per_km_rate':'12.00',
        'per_minute_rate':'2.00','minimum_fare':'60.00','max_multiplier':'3.00'}.items()},
        'surge_enabled': {'type':'boolean','example':True}, 'version': version, 'reason':reason})
    share = schema({'driver_pct':string('85.00'),'company_pct':string('15.00'),'version':version,'reason':reason})
    zone = schema({'name':string('Evening peak'),'latitude':{'type':'number','example':28.6139},
        'longitude':{'type':'number','example':77.209},'radius_m':{'type':'integer','example':4000},
        'multiplier':string('1.50'),'timezone':string('Asia/Kolkata'),'start_time':string('17:00'),
        'end_time':string('21:00'),'days':{'type':'array','items':{'type':'integer'},'example':[0,1,2,3,4]},
        'enabled':{'type':'boolean','example':True},'reason':reason})
    definitions = {'FareWrite':fare, 'ShareWrite':share, 'ZoneCreate':zone,
        'ZoneWrite':schema({**zone['properties'],'version':version}),
        'Preview':schema({'distance_m':string('5000'),'duration_seconds':string('900'),
            'latitude':{'type':'number','example':28.6139},'longitude':{'type':'number','example':77.209}})}
    paths = {}
    endpoints = [('/dashboard','get','Operations overview',None),('/drivers','get','Driver monitoring',None),
        ('/rides','get','Ride monitoring',None),('/fare-rules','get','Current fare rules',None),
        ('/fare-rules','put','Replace fare policy','FareWrite'),('/surge-zones','get','List surge zones',None),
        ('/surge-zones','post','Create circular surge zone','ZoneCreate'),('/surge-zones/{zone_id}','put','Replace surge zone','ZoneWrite'),
        ('/revenue-share','get','Current revenue split',None),('/revenue-share','put','Create effective revenue split','ShareWrite'),
        ('/audit','get','Paginated settings audit',None),('/ledger','get','Paginated allocation ledger',None),
        ('/quote-preview','post','Admin-only fare calculator; not a route estimate','Preview')]
    for path,method,title,body in endpoints:
        params = []
        if '{zone_id}' in path:
            params.append({'in':'path','name':'zone_id','required':True,'type':'string'})
        if path in ('/audit','/ledger'):
            params += [{'in':'query','name':'page','type':'integer','default':1},
                {'in':'query','name':'page_size','type':'integer','default':25,'maximum':100}]
        if body:
            params.append({'in':'body','name':'body','required':True,'schema':{'$ref':'#/definitions/'+body}})
        paths.setdefault('/api/admin'+path,{})[method]={'summary':title,'tags':['Admin'],
            'security':[{'Bearer':[]}],'parameters':params,'responses':{
                '200':{'description':'Success: {data: result, request_id: UUID}'},
                '400':{'description':'Invalid input'},'401':{'description':'Invalid/expired token'},
                '403':{'description':'Admin role required'},'409':{'description':'Concurrent edit: reload current version'},
                '503':{'description':'Monitoring adapter not configured'}}}
    return {'swagger':'2.0','info':{'title':'GenZ@Work Admin API','version':'1.0.0',
        'description':'Use Authorization: Bearer <token>. Enter the full Bearer prefix in Authorize. Money and percentages are decimal strings. All writes require a reason; updates require the current version.'},
        'basePath':'/','schemes':['http','https'],'consumes':['application/json'],'produces':['application/json'],
        'securityDefinitions':{'Bearer':{'type':'apiKey','name':'Authorization','in':'header'}},
        'definitions':definitions,'paths':paths}
