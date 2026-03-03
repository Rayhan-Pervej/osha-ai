from marshmallow import Schema, fields


class CreateKeySchema(Schema):
    client_id = fields.Str(required=True)
    agent_id = fields.Str(required=True)
    allowed_domains = fields.List(fields.Str(), load_default=None)


class RotateKeySchema(Schema):
    client_id = fields.Str(required=True)
    agent_id = fields.Str(required=True)
