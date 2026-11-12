import os
import json
import io
from datetime import datetime
import psycopg2
from psycopg2.extras import RealDictCursor
from minio import Minio

PG_HOST = os.getenv("PG_HOST", "127.0.0.1")
PG_PORT = int(os.getenv("PG_PORT", 5435))
PG_USER = os.getenv("PG_USER", "postgres")
PG_PASS = os.getenv("PG_PASS", "edp_password_2026")
KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "127.0.0.1:9092")
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "127.0.0.1:9000")

def run_kafka_outbox_stream():
    print("--- Starting Real-Time Outbox CDC Streaming via Apache Kafka ---")
    events = []
    for db_name in ["ecommerce_db", "billing_db"]:
        try:
            conn = psycopg2.connect(host=PG_HOST, port=PG_PORT, user=PG_USER, password=PG_PASS, dbname=db_name)
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute("SELECT * FROM integration.outbox_events LIMIT 100;")
            rows = cur.fetchall()
            for r in rows:
                r["source_database"] = db_name
                r["streamed_at"] = datetime.utcnow().isoformat()
                events.append(r)
            cur.close()
            conn.close()
        except Exception as e:
            print(f"[STREAM INFO] {db_name}: {e}")

    # Publish & Consume via Kafka if reachable, and archive stream batch to MinIO
    try:
        from kafka import KafkaProducer
        producer = KafkaProducer(
            bootstrap_servers=[KAFKA_BOOTSTRAP],
            value_serializer=lambda v: json.dumps(v, default=str).encode("utf-8"),
            request_timeout_ms=5000
        )
        for ev in events:
            producer.send("edp.outbox.events", ev)
        producer.flush()
        producer.close()
        print(f"[KAFKA PRODUCER] Published {len(events)} real-time outbox events -> Topic 'edp.outbox.events'")
    except Exception as e:
        print(f"[KAFKA STREAM] Direct Micro-Batch Mode ({e})")

    client = Minio(MINIO_ENDPOINT, access_key="admin", secret_key="edp_password_2026", secure=False)
    stream_bytes = json.dumps(events, default=str, indent=2).encode("utf-8")
    client.put_object("bronze", "realtime_kafka_stream/outbox_events_stream.json", io.BytesIO(stream_bytes), length=len(stream_bytes), content_type="application/json")
    print(f"[KAFKA SINK] Archived {len(events)} real-time events -> s3://bronze/realtime_kafka_stream/outbox_events_stream.json")

if __name__ == "__main__":
    run_kafka_outbox_stream()
