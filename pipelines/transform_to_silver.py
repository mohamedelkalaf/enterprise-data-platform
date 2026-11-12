import os
import json
import io
from datetime import datetime
from minio import Minio

MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "127.0.0.1:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "admin")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "edp_password_2026")
BRONZE_BUCKET = "bronze"
SILVER_BUCKET = "silver"

client = Minio(MINIO_ENDPOINT, access_key=MINIO_ACCESS_KEY, secret_key=MINIO_SECRET_KEY, secure=False)

if not client.bucket_exists(SILVER_BUCKET):
    client.make_bucket(SILVER_BUCKET)
    print(f"Bucket '{SILVER_BUCKET}' created successfully in MinIO.")

def transform_all():
    print("--- Starting Silver Layer Transformation & Cleansing ---")
    objects = client.list_objects(BRONZE_BUCKET, recursive=True)
    for obj in objects:
        if obj.object_name.endswith(".json"):
            resp = client.get_object(BRONZE_BUCKET, obj.object_name)
            raw_rows = json.loads(resp.read().decode('utf-8'))
            resp.close()
            
            cleaned_rows = []
            seen = set()
            for r in raw_rows:
                clean_r = {}
                for k, v in r.items():
                    clean_r[k.strip().lower()] = v.strip() if isinstance(v, str) else v
                row_sig = json.dumps(clean_r, sort_keys=True, default=str)
                if row_sig not in seen:
                    seen.add(row_sig)
                    clean_r["_silver_processed_at"] = datetime.utcnow().isoformat()
                    cleaned_rows.append(clean_r)
            
            out_bytes = json.dumps(cleaned_rows, default=str, ensure_ascii=False, indent=2).encode('utf-8')
            silver_path = f"cleaned/{obj.object_name}"
            client.put_object(SILVER_BUCKET, silver_path, io.BytesIO(out_bytes), length=len(out_bytes), content_type="application/json")
            print(f"[SILVER SUCCESS] Cleaned & Transformed -> s3://{SILVER_BUCKET}/{silver_path} ({len(cleaned_rows)} rows)")

if __name__ == "__main__":
    transform_all()
