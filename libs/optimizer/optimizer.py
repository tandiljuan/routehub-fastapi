class Optimizer():

    def __init__(self, host: str, port: int, auth: str = None):
        self.host = host
        self.port = port
        self.auth = auth
