from setuptools import setup

import athumb

long_description = open("README.md").read()

setup(
    name="django-athumb",
    version=athumb.VERSION,
    packages=[
        "athumb",
        "athumb.management",
        "athumb.management.commands",
        "athumb.templatetags",
    ],
    description="A simple, S3-backed thumbnailer field.",
    long_description=long_description,
    author="Gregory Taylor",
    author_email="gtaylor@duointeractive.com",
    license="BSD License",
    url="https://github.com/duointeractive/django-athumb",
    platforms=["any"],
    install_requires=["django", "django-storages[s3]", "pillow"],
    classifiers=[
        "Development Status :: 5 - Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: BSD License",
        "Natural Language :: English",
        "Operating System :: OS Independent",
        "Programming Language :: Python",
        "Environment :: Web Environment",
    ],
)
