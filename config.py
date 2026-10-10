# app/config.py
import json, os, boto3
from functools import lru_cache

@lru_cache(maxsize=1)
def load_secrets():
    secret_name = os.getenv("DB_SECRET_ID")
    if not secret_name:
        return    
    region = os.getenv("AWS_REGION", "ap-southeast-1")
    sm = boto3.client("secretsmanager", region_name=region)
    for k, v in json.loads(sm.get_secret_value(SecretId=secret_name)["SecretString"]).items():
        os.environ.setdefault(k, str(v))