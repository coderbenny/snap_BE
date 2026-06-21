from marshmallow import Schema, fields, validate


class RegisterDeviceSchema(Schema):
    name = fields.Str(required=True, validate=validate.Length(min=1, max=100))
    platform = fields.Str(
        required=True,
        validate=validate.OneOf(
            ['macos', 'windows', 'android', 'ios', 'web'],
            error='platform must be one of: macos, windows, android, ios, web',
        ),
    )
