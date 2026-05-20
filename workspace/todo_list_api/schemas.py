from marshmallow import Schema, fields, validate
from marshmallow.exceptions import ValidationError


class TodoSchema(Schema):
    id = fields.Int(dump_only=True)
    title = fields.Str(required=True, validate=validate.Length(min=1, max=100))
    description = fields.Str(required=True, validate=validate.Length(min=1, max=200))
    completed = fields.Bool(default=False)

    def load(self, data, many=None, partial=None, unknown=None, post_load=None):
        try:
            return super().load(data, many, partial, unknown, post_load)
        except ValidationError as err:
            raise ValueError(f"Invalid data: {err}") from err

    def dump(self, obj, many=None, update_fields=None, partial=None):
        try:
            return super().dump(obj, many, update_fields, partial)
        except Exception as err:
            raise ValueError(f"Failed to serialize data: {err}") from err