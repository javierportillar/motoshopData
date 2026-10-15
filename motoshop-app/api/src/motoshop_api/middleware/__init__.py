"""Middlewares para la API de MotoShop."""

from motoshop_api.middleware.etag import ETagMiddleware

__all__ = ["ETagMiddleware"]
