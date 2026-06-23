from marshmallow import Schema, fields, validate


class CreateTeamSchema(Schema):
    name = fields.Str(required=True, validate=validate.Length(min=1, max=100))


class InviteSchema(Schema):
    email = fields.Email(required=True)


class AcceptInviteSchema(Schema):
    token = fields.Str(required=True, validate=validate.Length(min=1))


class SharedSnippetSchema(Schema):
    title = fields.Str(required=True, validate=validate.Length(min=1, max=255))
    ciphertext = fields.Str(required=True, validate=validate.Length(min=1))
    iv = fields.Str(required=True, validate=validate.Length(min=16, max=24))
    tags = fields.List(fields.Str(), load_default=None, allow_none=True)
