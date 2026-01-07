import json
import requests
from .models import (
    DraftSet,
    PlanContext,
    ResultSet,
)

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

    def get_plan_result(self, task_id: str) -> ResultSet:
        url = f"{self.host}:{self.port}/route-optimizer-app/routes/{task_id}"
        headers = {'api-key': self.auth} if self.auth else {}
        r = requests.get(url, headers=headers)
        rbody = {"status": "processing"}
        if 200 == r.status_code:
            rbody = json.loads(r.text)
            rbody['status'] = "completed"
        result_set = ResultSet.model_validate(rbody)
        return result_set

    def send_route_draft(self, draft: DraftSet):
        payload = draft.model_dump(serialize_as_any=True)
        payload = json.dumps(payload)
        url = f"{self.host}:{self.port}/route-optimizer-app/routes/optimize"
        headers = {'api-key': self.auth} if self.auth else {}
        r = requests.post(url, data=payload, headers=headers)
        rbody = json.loads(r.text)
        return rbody['session_id']
