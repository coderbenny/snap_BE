from marshmallow import Schema, fields, validate


class ClipboardItemSchema(Schema):
    id = fields.Str(required=True, validate=validate.Length(min=1, max=36))
    ciphertext = fields.Str(required=True, validate=validate.Length(min=1))
    iv = fields.Str(required=True, validate=validate.Length(min=1, max=24))
    content_type = fields.Str(
        required=True,
        validate=validate.OneOf(
            ['text', 'image', 'url', 'file'],
            error='content_type must be one of: text, image, url, file',
        ),
    )
    tags = fields.List(fields.Str(), load_default=None, allow_none=True)
    pinned = fields.Bool(load_default=False)
    device_id = fields.Str(load_default=None, allow_none=True)
    client_created_at = fields.Integer(required=True, strict=True)


class SyncPushSchema(Schema):
    items = fields.List(
        fields.Nested(ClipboardItemSchema),
        required=True,
        validate=validate.Length(min=1, max=500, error='Batch must contain 1–500 items'),
    )


class SyncDeleteSchema(Schema):
    ids = fields.List(
        fields.Str(validate=validate.Length(min=1, max=36)),
        required=True,
        validate=validate.Length(min=1, max=500, error='IDs list must contain 1–500 entries'),
    )
