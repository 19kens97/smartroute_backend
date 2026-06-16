from rest_framework.renderers import JSONRenderer


class StandardizedJSONRenderer(JSONRenderer):
    def render(self, data, accepted_media_type=None, renderer_context=None):
        if renderer_context is None:
            return super().render(data, accepted_media_type, renderer_context)
        response = renderer_context.get("response")
        if response is None:
            return super().render(data, accepted_media_type, renderer_context)
        if isinstance(data, dict) and {"success", "message", "data", "errors"}.issubset(data.keys()):
            return super().render(data, accepted_media_type, renderer_context)
        success = response.status_code < 400
        payload = {
            "success": success,
            "message": "OK" if success else "Request failed",
            "data": data if success else {},
            "errors": {} if success else data,
        }
        return super().render(payload, accepted_media_type, renderer_context)
