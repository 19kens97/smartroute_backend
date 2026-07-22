from rest_framework.renderers import JSONRenderer


class StandardizedJSONRenderer(JSONRenderer):
    envelope_keys = {"success", "message", "data", "errors"}

    def render(
        self,
        data,
        accepted_media_type=None,
        renderer_context=None,
    ):
        if renderer_context is None:
            return super().render(
                data,
                accepted_media_type,
                renderer_context,
            )

        response = renderer_context.get("response")
        if response is None:
            return super().render(
                data,
                accepted_media_type,
                renderer_context,
            )

        if response.status_code == 204:
            return b""

        if (
            isinstance(data, dict)
            and self.envelope_keys.issubset(data.keys())
        ):
            payload = data
        else:
            success = response.status_code < 400
            payload = {
                "success": success,
                "message": (
                    "OK"
                    if success
                    else "La requête n'a pas pu être traitée."
                ),
                "data": data if success and data is not None else {},
                "errors": data if not success and data is not None else {},
            }

        return super().render(
            payload,
            accepted_media_type,
            renderer_context,
        )
