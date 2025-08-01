# -*- encoding: utf-8 -*-
"""
Fields, FieldFiles, and Validators.
"""

import os
import io

from PIL import Image
from django.db.models import ImageField
from django.db.models.fields.files import ImageFieldFile
from django.conf import settings
from django.core.cache import cache
from django.core.files.base import ContentFile
from .exceptions import UploadedImageIsUnreadableError

from .validators import ImageUploadExtensionValidator


# Cache URLs for thumbnails so we don't have to keep re-generating them.
THUMBNAIL_URL_CACHE_TIME = getattr(settings, "THUMBNAIL_URL_CACHE_TIME", 3600 * 24)
# Optional cache-buster string to append to end of thumbnail URLs.
MEDIA_CACHE_BUSTER = getattr(settings, "MEDIA_CACHE_BUSTER", "")

# Models want this instantiated ahead of time.
IMAGE_EXTENSION_VALIDATOR = ImageUploadExtensionValidator()


class ImageWithThumbsFieldFile(ImageFieldFile):
    """
    Serves as the file-level storage object for thumbnails.
    """

    def generate_url(
        self, thumb_name, ssl_mode=False, check_cache=True, cache_bust=True
    ):
        # This is tacked on to the end of the cache key to make sure SSL
        # URLs are stored separate from plain http.
        ssl_postfix = "_ssl" if ssl_mode else ""

        # Try to see if we can hit the cache instead of asking the storage
        # backend for the URL. This is particularly important for S3 backends.

        cache_key = None

        if check_cache:
            cache_key = "Thumbcache_%s_%s%s" % (self.url, thumb_name, ssl_postfix)
            cache_key = cache_key.strip()

            cached_val = cache.get(cache_key)
            if cached_val:
                return cached_val

        # Determine what the filename would be for a thumb with these
        # dimensions, regardless of whether it actually exists.
        new_filename = self._calc_thumb_filename(thumb_name)

        # Split URL from GET attribs.
        url_get_split = self.url.rsplit("?", 1)
        # Just the URL string (no GET attribs).
        url_str = url_get_split[0]
        # Get the URL string without the original's filename at the end.
        url_minus_filename = url_str.rsplit("/", 1)[0]

        # Slap the new thumbnail filename on the end of the old URL, in place
        # of the orignal image's filename.
        new_url = "%s/%s" % (url_minus_filename, os.path.basename(new_filename))

        if cache_bust and MEDIA_CACHE_BUSTER:
            new_url = "%s?cbust=%s" % (new_url, MEDIA_CACHE_BUSTER)

        if ssl_mode:
            new_url = new_url.replace("http://", "https://")

        if cache_key:
            # Cache this so we don't have to hit the storage backend for a while.
            cache.set(cache_key, new_url, THUMBNAIL_URL_CACHE_TIME)

        return new_url

    def get_thumbnail_format(self):
        """
        Determines the target thumbnail type either by looking for a format
        override specified at the model level, or by using the format the
        user uploaded.
        """
        if self.field.thumbnail_format:
            # Over-ride was given, use that instead.
            return self.field.thumbnail_format.lower()
        else:
            # Use the existing extension from the file.
            filename_split = self.name.rsplit(".", 1)
            return filename_split[-1]

    def save(self, name, content, save=True):
        """
        Handles some extra logic to generate the thumbnails when the original
        file is uploaded.
        """
        super(ImageWithThumbsFieldFile, self).save(name, content, save)
        try:
            self.generate_thumbs(name, content)
        except IOError as exc:
            if "cannot identify" in exc.message or "bad EPS header" in exc.message:
                raise UploadedImageIsUnreadableError(
                    "We were unable to read the uploaded image. "
                    "Please make sure you are uploading a valid image file."
                )
            else:
                raise

    def generate_thumbs(self, name, content):
        # see http://code.djangoproject.com/ticket/8222 for details
        content.seek(0)
        with Image.open(content) as image:
            for thumb in self.field.thumbs:
                thumb_name, thumb_options = thumb
                with image.copy() as image_copy:
                    self.create_and_store_thumb(image_copy, thumb_name, thumb_options)

    def _calc_thumb_filename(self, thumb_name):
        """
        Calculates the correct filename for a would-be (or potentially
        existing) thumbnail of the given size.

        NOTE: This includes the path leading up to the thumbnail. IE:
        uploads/cbid_images/photo.png

        size: (tuple) In the format of (width, height)

        Returns a string filename.
        """
        filename_split = self.name.rsplit(".", 1)
        file_name = filename_split[0]
        file_extension = self.get_thumbnail_format()

        return "%s_%s.%s" % (file_name, thumb_name, file_extension)

    def create_and_store_thumb(self, image, thumb_name, thumb_options):
        """
        Given that 'image' is a PIL Image object, create a thumbnail for the
        given size tuple and store it via the storage backend.

        image: (Image) PIL Image object.
        size: (tuple) Tuple in form of (width, height). Image will be
            thumbnailed to this size.
        """
        size = thumb_options["size"]

        if not isinstance(size, tuple):
            raise UploadedImageIsUnreadableError(
                f"incorrect size specifications ${size}"
            )

        upscale = thumb_options.get("upscale", True)
        crop = thumb_options.get("crop")
        crop_option = "center" if crop else None

        thumb_filename = self._calc_thumb_filename(thumb_name)
        file_extension = self.get_thumbnail_format()

        image = self._create_thumbnail(
            image, size, crop_option=crop_option, upscale=upscale
        )

        with io.BytesIO() as thumbnail:
            image.save(thumbnail, format=file_extension)
            thumb_content = ContentFile(thumbnail.getvalue())
            self.storage.save(thumb_filename, thumb_content)

    @staticmethod
    def _create_thumbnail(image, size, crop_option=None, upscale=False):
        from .utils import scale, crop, convert_colorspace

        image = convert_colorspace(image, colorspace="RGB")
        image = scale(image, size, crop_option=crop_option, upscale=upscale)
        if crop_option:
            image = crop(image, size, crop_option=crop_option)
        return image

    def delete(self, save=True):
        """
        Deletes the original, plus any thumbnails. Fails silently if there
        are errors deleting the thumbnails.
        """
        for thumb in self.field.thumbs:
            thumb_name, thumb_options = thumb
            thumb_filename = self._calc_thumb_filename(thumb_name)
            self.storage.delete(thumb_filename)

        super(ImageWithThumbsFieldFile, self).delete(save)


class ImageWithThumbsField(ImageField):
    """
    Usage example:
    ==============
    photo = ImageWithThumbsField(upload_to='images', thumbs=((125,125),(300,200))

    Note: The 'thumbs' attribute is not required. If you don't provide it,
    ImageWithThumbsField will act as a normal ImageField
    """

    attr_class = ImageWithThumbsFieldFile

    def __init__(self, *args, **kwargs):
        self.thumbs = kwargs.pop("thumbs", ())
        self.thumbnail_format = kwargs.pop("thumbnail_format", "JPEG")

        if "validators" not in kwargs:
            kwargs["validators"] = [IMAGE_EXTENSION_VALIDATOR]

        if "max_length" not in kwargs:
            kwargs["max_length"] = 255

        super(ImageWithThumbsField, self).__init__(*args, **kwargs)

    def deconstruct(self):
        name, path, args, kwargs = super(ImageWithThumbsField, self).deconstruct()
        kwargs["thumbs"] = self.thumbs
        kwargs["thumbnail_format"] = self.thumbnail_format
        return name, path, args, kwargs
