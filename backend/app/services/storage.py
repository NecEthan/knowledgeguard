import io
import logging
from urllib.parse import urlparse

from minio import Minio
from minio.commonconfig import ENABLED, Filter, Tag, Tags
from minio.error import S3Error
from minio.lifecycleconfig import Expiration, LifecycleConfig, Rule

from app.config import settings

logger = logging.getLogger(__name__)

_ORPHAN_TAG_KEY = "kg-orphan"
_ORPHAN_TAG_VALUE = "true"

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


def tag_as_orphan(key: str) -> None:
    """Tag a freshly-uploaded object as a potential orphan.

    If the DB commit that follows never completes (process crash, rollback),
    the lifecycle rule will auto-expire this object after 1 day.
    Best-effort: a tagging failure is logged but not raised.
    """
    try:
        tags = Tags.new_object_tags()
        tags[_ORPHAN_TAG_KEY] = _ORPHAN_TAG_VALUE
        _client().set_object_tags(settings.storage_bucket, key, tags)
    except Exception:
        logger.warning("tag_as_orphan failed for key=%s", key, exc_info=True)


def confirm_object(key: str) -> None:
    """Remove the orphan tag once the DB record has been committed.

    Best-effort: if removal fails, the lifecycle rule will auto-expire the
    object after 1 day, which will cause the processing job to fail.
    """
    try:
        _client().delete_object_tags(settings.storage_bucket, key)
    except Exception:
        logger.warning("confirm_object failed for key=%s", key, exc_info=True)


def configure_bucket_lifecycle() -> None:
    """Idempotently set a lifecycle rule that auto-expires orphaned uploads.

    Called once at application startup. Best-effort: failure is logged but
    does not prevent the application from starting.
    """
    try:
        config = LifecycleConfig(
            [
                Rule(
                    ENABLED,
                    rule_filter=Filter(tag=Tag(_ORPHAN_TAG_KEY, _ORPHAN_TAG_VALUE)),
                    rule_id="expire-orphan-uploads",
                    expiration=Expiration(days=1),
                )
            ]
        )
        _client().set_bucket_lifecycle(settings.storage_bucket, config)
        logger.info("MinIO lifecycle rule configured for bucket %s", settings.storage_bucket)
    except Exception:
        logger.warning("configure_bucket_lifecycle failed", exc_info=True)
