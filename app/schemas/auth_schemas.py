from marshmallow import Schema, fields, validate


class RegisterSchema(Schema):
    email = fields.Email(required=True)
    password = fields.Str(
        required=True,
        validate=validate.Length(min=8, error='Password must be at least 8 characters'),
    )


class LoginSchema(Schema):
    email = fields.Email(required=True)
    password = fields.Str(required=True)


class RefreshSchema(Schema):
    refresh_token = fields.Str(required=True)


class LogoutSchema(Schema):
    refresh_token = fields.Str(required=True)


class ForgotPasswordSchema(Schema):
    email = fields.Email(required=True)


class ResetPasswordSchema(Schema):
    token = fields.Str(required=True)
    password = fields.Str(
        required=True,
        validate=validate.Length(min=8, error='Password must be at least 8 characters'),
    )


class VerifyEmailSchema(Schema):
    token = fields.Str(required=True)
