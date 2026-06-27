from marshmallow import Schema, fields, validate


class RegisterDeviceSchema(Schema):
    device_id = fields.Str(required=True, validate=validate.Length(min=1, max=36))
    name = fields.Str(required=True, validate=validate.Length(min=1, max=100))
    platform = fields.Str(
        required=True,
        validate=validate.OneOf(
            ['macos', 'windows', 'android', 'ios', 'web'],
            error='platform must be one of: macos, windows, android, ios, web',
        ),
    )
    app_version = fields.Str(load_default=None, validate=validate.Length(max=20))
