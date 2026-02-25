from marshmallow import Schema, fields, validate

class DiscoverSchema(Schema):
    query = fields.Str(required=True, validate=validate.Length(min=1))
    client_id = fields.Str(required= True)
    agent_id = fields.Str(required=True)
    part_filter = fields.Str(load_default=None)


class GenerateSchema(Schema):
    query = fields.Str(required=True, validate=validate.Length(min=1))
    section_ids = fields.List(fields.Str(), required=True, validate=validate.Length(min=1))
    client_id = fields.Str(required= True)
    agent_id = fields.Str(required=True)
    session_id = fields.Str(load_default=None)

class CreateKeySchema(Schema):
    client_id = fields.Str(required=True)
    agent_id = fields.Str(required=True)
    allowed_domains = fields.List(fields.Str(), load_default=None)


class RotateKeySchema(Schema):
    client_id = fields.Str(required=True)
    client_id = fields.Str(required=True)
