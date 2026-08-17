from imagekitio import ImageKit

from app.config import settings

imagekit = ImageKit(
    private_key=settings.imagekit_private_key,
    public_key=settings.imagekit_public_key,
    url_endpoint=settings.imagekit_url,
)
