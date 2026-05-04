import redis

class RedisBackend:
    def __init__(self, host='localhost', port=6379, db=0):
        self.client = redis.Redis(host=host, port=port, db=db, decode_responses=True)

    def eval(self, script: str, keys: list, args: list):
        return self.client.eval(script, len(keys), *keys, *args)

    def ping(self):
        return self.client.ping()
