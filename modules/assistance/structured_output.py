"""Provider structured-output schema preparation, independent of assistant policy."""

def strict_schema(model):
    """Responses strict schemas require every property, including nullable defaults."""
    schema = model.model_json_schema()
    def visit(value):
        if isinstance(value, dict):
            value.pop('default', None)
            if value.get('type') == 'object':
                value['required'] = list(value.get('properties', {}))
                value['additionalProperties'] = False
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)
    visit(schema)
    return schema
