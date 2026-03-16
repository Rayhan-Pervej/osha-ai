from marshmallow import Schema, fields, validate


class CreateKeySchema(Schema):
    client_id = fields.Str(required=True)
    agent_id = fields.Str(required=True)
    allowed_domains = fields.List(fields.Str(), load_default=None)


class RotateKeySchema(Schema):
    client_id = fields.Str(required=True)
    agent_id = fields.Str(required=True)

class ChatRequestSchema(Schema):
    query = fields.Str(required=True, validate=validate.Length(min=1, max=2000))
    session_id = fields.Str(load_default=None, validate=validate.Length(max=128))