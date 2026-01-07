import json
import requests
from .models import PlanContext

class Optimizer():

    def __init__(self, host: str, port: int, auth: str = None):
        self.host = host
        self.port = port
        self.auth = auth

    def send_route_plan(self, plan: PlanContext) -> str:
        payload = plan.model_dump(serialize_as_any=True)
        payload = json.dumps(payload)
        url = f"{self.host}:{self.port}/route-optimizer-app/routes"
        headers = {'api-key': self.auth} if self.auth else {}
        r = requests.post(url, data=payload, headers=headers)
        rbody = json.loads(r.text)
        return rbody['session_id']
