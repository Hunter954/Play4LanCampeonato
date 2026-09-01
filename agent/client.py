import requests
class PlatformClient:
    def __init__(self,url,token): self.url=url.rstrip('/'); self.headers={'Authorization':'Bearer '+token}
    def heartbeat(self,body): return requests.post(self.url+'/api/v1/agent/heartbeat',json=body,headers=self.headers,timeout=8).raise_for_status()
    def commands(self,host): return requests.get(self.url+'/api/v1/agent/commands/'+host,headers=self.headers,timeout=8).json().get('commands',[])
    def ack(self,cid,status='DONE'): return requests.post(f'{self.url}/api/v1/agent/commands/{cid}/ack',json={'status':status},headers=self.headers,timeout=8).raise_for_status()
    def send_events(self,events): return requests.post(self.url+'/api/v1/agent/events',json={'events':events},headers=self.headers,timeout=8).raise_for_status()
    def upload_demo(self,path,match_id=None,map_name=None,part_number=1):
        with open(path,'rb') as f: return requests.post(self.url+'/api/v1/agent/demos',headers=self.headers,files={'file':(path.split('/')[-1],f)},data={'match_id':match_id or '','map_name':map_name or '','part_number':part_number},timeout=300).raise_for_status()
