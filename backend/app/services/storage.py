import io
from urllib.parse import urlparse

from minio import Minio
from minio.error import S3Error

from app.config import settings


_client_instance: Minio | None = None


def _client() -> Minio:
    global _client_instance
    if _client_instance is None:
        parsed = urlparse(settings.storage_endpoint)
        _client_instance = Minio(
            parsed.netloc,
            access_key=settings.storage_access_key,
            secret_key=settings.storage_secret_key,
            secure=parsed.scheme == "https",
        )
    return _client_instance


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
