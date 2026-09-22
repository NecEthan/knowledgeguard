import io
from urllib.parse import urlparse

from minio import Minio
from minio.error import S3Error

from app.config import settings


def _client() -> Minio:
    parsed = urlparse(settings.storage_endpoint)
    return Minio(
        parsed.netloc,
        access_key=settings.storage_access_key,
        secret_key=settings.storage_secret_key,
        secure=parsed.scheme == "https",
    )


def upload_bytes(key: str, data: bytes, content_type: str) -> None:
    _client().put_object(
        settings.storage_bucket,
        key,
        io.BytesIO(data),
        length=len(data),
        content_type=content_type,
    )


def download_bytes(key: str) -> bytes:
    response = _client().get_object(settings.storage_bucket, key)
    try:
        return response.read()
    finally:
        response.close()
        response.release_conn()


def delete_object(key: str) -> None:
    try:
        _client().remove_object(settings.storage_bucket, key)
    except S3Error:
        pass
