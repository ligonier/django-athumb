"""
A lot of the logic here was extracted from https://github.com/ligonier/pial to remove the extra
abstraction layers.
"""

from PIL import Image
import re

from athumb.exceptions import ThumbnailParseError

_CROP_PERCENT_PATTERN = re.compile(r"^(?P<value>\d+)(?P<unit>%|px)$")

# The following two alias dicts put percentage values on some common
# X, Y cropping names. For example, center cropping is 50%.
_X_ALIAS_PERCENT = {
    "left": "0%",
    "center": "50%",
    "right": "100%",
}
_Y_ALIAS_PERCENT = {
    "top": "0%",
    "center": "50%",
    "bottom": "100%",
}


def get_cropping_offset(crop_option, epsilon):
    """
    Calculates the cropping offset for the cropped image. This only calculates
    the offset for one dimension (X or Y). This should be called twice to get
    the offsets for the X and Y dimensions.

    :param str crop_option: A percentage cropping value for the plane. This is in the
        form of something like '50%'.
    :param float epsilon: The difference between the original image's dimension
        (X or Y) and the desired crop window.
    :rtype: int
    :returns: The cropping offset for the given dimension.
    """
    m = _CROP_PERCENT_PATTERN.match(crop_option)
    if not m:
        raise ThumbnailParseError("Unrecognized crop option: %s" % crop_option)
    value = int(m.group("value"))  # we only take ints in the regexp
    unit = m.group("unit")
    if unit == "%":
        value = epsilon * value / 100.0
        # return ∈ [0, epsilon]
    return int(max(0, min(value, epsilon)))


def parse_crop(crop_option, xy_image, xy_window):
    """
    Returns x, y offsets for cropping. The window area should fit inside
    image, but it works out anyway

    :param str crop_option: A cropping offset string. This is either one or two
        space-separated values. If only one value is specified, the cropping
        amount (pixels or percentage) for both X and Y dimensions is the
        amount given. If two values are specified, X and Y dimension cropping
        may be set independently. Some examples: '50% 50%', '50px 20px',
        '50%', '50px'.
    :param tuple xy_image: The (x,y) dimensions of the image.
    :param tuple xy_window: The desired dimensions (x,y) of the cropped image.
    :raises: ThumbnailParseError in the event of invalid input.
    :rtype: tuple of ints
    :returns: A tuple of offsets for cropping, in (x,y) format.
    """
    # Cropping percentages are space-separated by axis. For example:
    # '50% 75%' would be a 50% cropping ratio for X, and 75% for Y.
    xy_crop = crop_option.split(" ")
    if len(xy_crop) == 1:
        # Only one dimension was specified, use the same for both planes.
        if crop_option in _X_ALIAS_PERCENT:
            x_crop = _X_ALIAS_PERCENT[crop_option]
            y_crop = "50%"
        elif crop_option in _Y_ALIAS_PERCENT:
            y_crop = _Y_ALIAS_PERCENT[crop_option]
            x_crop = "50%"
        else:
            x_crop, y_crop = crop_option, crop_option
    elif len(xy_crop) == 2:
        # Separate X and Y cropping percentages specified.
        x_crop, y_crop = xy_crop
        x_crop = _X_ALIAS_PERCENT.get(x_crop, x_crop)
        y_crop = _Y_ALIAS_PERCENT.get(y_crop, y_crop)
    else:
        raise ThumbnailParseError("Unrecognized crop option: %s" % crop_option)

    # We now have cropping percentages for the X and Y planes.
    # Calculate the cropping offsets (in pixels) for each plane.
    offset_x = get_cropping_offset(x_crop, xy_image[0] - xy_window[0])
    offset_y = get_cropping_offset(y_crop, xy_image[1] - xy_window[1])
    return offset_x, offset_y


def round_to_int(number) -> int:
    if isinstance(number, float):
        return int(round(number, 0))
    return int(number)


def convert_colorspace(image, colorspace):
    if colorspace == "RGB":
        if image.mode == "RGBA":
            return image
        if image.mode == "P" and "transparency" in image.info:
            return image.convert("RGBA")
        return image.convert("RGB")
    if colorspace == "GRAY":
        return image.convert("L")
    return image


def crop(image, target_size, crop_option="center"):
    x_image, y_image = map(float, image.size)
    x_offset, y_offset = parse_crop(crop_option, (x_image, y_image), target_size)
    return image.crop(
        (x_offset, y_offset, target_size[0] + x_offset, target_size[1] + y_offset)
    )


def scale(image, target_size, crop_option=None, upscale=False):
    x_image, y_image = map(float, image.size)
    factors = (target_size[0] / x_image, target_size[1] / y_image)
    factor = max(factors) if crop_option else min(factors)
    if factor < 1 or upscale:
        width = round_to_int(x_image * factor)
        height = round_to_int(y_image * factor)
        image = image.resize((width, height), resample=Image.Resampling.LANCZOS)
    return image
