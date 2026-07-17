from marshmallow import Schema, fields, validate


class SubscribeSchema(Schema):
    tier = fields.Str(
        required=True,
        validate=validate.OneOf(
            ['pro', 'pro_ai', 'team'],
            error='tier must be one of: pro, pro_ai, team',
        ),
    )
    callback_url = fields.Str(load_default=None, allow_none=True)
    coupon_code = fields.Str(load_default=None, allow_none=True)
